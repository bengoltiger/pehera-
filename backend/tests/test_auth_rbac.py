"""Authentication, JWT and RBAC tests.

Mirrors the claim in `security/auth.py` that role restrictions are "enforced
here, in one place, and asserted by the test-suite".
"""
from __future__ import annotations

import datetime as dt

from app.db.models import User
from app.security.auth import create_access_token, decode_token

AUTHORITY = {"username": "authority", "password": "authority123"}
ADMIN = {"username": "admin", "password": "admin12345"}
CITIZEN = {"username": "citizen", "password": "citizen123"}


def _login(client, creds):
    r = client.post("/api/auth/login", json=creds)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def test_login_success_and_naive_expires(client):
    r = client.post("/api/auth/login", json=AUTHORITY)
    assert r.status_code == 200
    body = r.json()
    assert body["access_token"]
    assert body["user"]["role"] == "authority"
    # must be naive UTC to match the rest of the API's "…Z" convention
    expires = dt.datetime.fromisoformat(body["expires_at"])
    assert expires.tzinfo is None


def test_login_wrong_password_401(client):
    r = client.post("/api/auth/login", json={"username": "authority", "password": "wrongpass"})
    assert r.status_code == 401


def test_citizen_cannot_list_users(client):
    tok = _login(client, CITIZEN)
    r = client.get("/api/auth/users", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 403


def test_authority_cannot_list_users(client):
    tok = _login(client, AUTHORITY)
    r = client.get("/api/auth/users", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 403


def test_admin_can_list_users(client):
    tok = _login(client, ADMIN)
    r = client.get("/api/auth/users", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    assert r.json()["count"] >= 1


def test_citizen_cannot_run_scenarios(client):
    tok = _login(client, CITIZEN)
    r = client.post(
        "/api/scenarios/river_flood/run",
        json={"reset_tick": True},
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 403


def test_me_requires_auth(client):
    assert client.get("/api/auth/me").status_code == 401


def test_token_roundtrip_and_role_claim():
    user = User(id="u_test", username="tester", role="authority")
    token, _ = create_access_token(user)
    payload = decode_token(token)
    assert payload["sub"] == "u_test"
    assert payload["role"] == "authority"
    assert payload["username"] == "tester"