"""Rate limiting & production-guard tests."""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.core.config import settings
from app.security.ratelimit import _client_key, check_rate_limit, reset_rate_limits


def _req(client_meta: tuple | None = None, xff: str | None = None, method: str = "GET") -> Request:
    scope = {
        "type": "http",
        "method": method,
        "path": "/x",
        "headers": ([(b"x-forwarded-for", xff.encode())] if xff else []),
        "query_string": b"",
        "client": tuple(client_meta) if client_meta else ("127.0.0.1", 1234),
        "server": ("testserver", 80),
        "scheme": "http",
    }
    return Request(scope)


def test_default_client_key_uses_peer_ip():
    assert _client_key(_req(("10.0.0.1", 5))) == "10.0.0.1"


def test_client_key_does_not_trust_xff_by_default():
    assert _client_key(_req(("10.0.0.1", 5), xff="203.0.113.9")) == "10.0.0.1"


def test_client_key_uses_xff_when_configured(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_trust_forwarded_for", True)
    try:
        assert _client_key(_req(("10.0.0.1", 5), xff="203.0.113.9")) == "203.0.113.9"
        assert (
            _client_key(_req(("10.0.0.1", 5), xff="203.0.113.9, 10.0.0.1")) == "203.0.113.9"
        )
    finally:
        monkeypatch.undo()


def test_rate_limit_triggers_429(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_requests", 2)
    monkeypatch.setattr(settings, "rate_limit_write_requests", 2)
    reset_rate_limits()
    try:
        check_rate_limit(_req())
        check_rate_limit(_req())
        with pytest.raises(HTTPException) as ei:
            check_rate_limit(_req())
        assert ei.value.status_code == 429
        assert "Retry-After" in ei.value.headers
    finally:
        reset_rate_limits()
        monkeypatch.undo()


def test_rate_limit_disabled_passes(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", False)
    reset_rate_limits()
    try:
        # limit of 1 but feature off: still no error
        monkeypatch.setattr(settings, "rate_limit_requests", 1)
        check_rate_limit(_req())
        check_rate_limit(_req())
    finally:
        reset_rate_limits()
        monkeypatch.undo()


def test_write_and_read_buckets_are_separate(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_requests", 1)
    monkeypatch.setattr(settings, "rate_limit_write_requests", 1)
    reset_rate_limits()
    try:
        check_rate_limit(_req(method="GET"))
        # GET bucket full, but a POST still fits its own write bucket
        check_rate_limit(_req(method="POST"))
        with pytest.raises(HTTPException):
            check_rate_limit(_req(method="GET"))
    finally:
        reset_rate_limits()
        monkeypatch.undo()


def test_production_refuses_insecure_default(monkeypatch):
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "jwt_secret", "dev-only-insecure-secret-change-me")
    from app.main import create_app

    with pytest.raises(RuntimeError, match="Refusing to start in production"):
        with TestClient(create_app()):
            pass
    monkeypatch.undo()