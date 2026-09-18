"""Shared test fixtures + isolation.

The whole suite runs against a throwaway SQLite file so tests never touch
`pehra.db`. Environment is patched BEFORE any `app.*` import, because the
settings singleton and the engine are bound at import time.
"""
from __future__ import annotations

import os
import tempfile

_tmpdir = tempfile.mkdtemp(prefix="pehra_tests_")
os.environ["PEHRA_DATABASE_URL"] = f"sqlite:///{os.path.join(_tmpdir, 'test.db')}"
os.environ["PEHRA_RATE_LIMIT_ENABLED"] = "false"
os.environ["PEHRA_JWT_SECRET"] = "test-secret-not-for-production-0123456789abcdef"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.seed import seed_all
from app.db.session import SessionLocal, init_db


@pytest.fixture(scope="session", autouse=True)
def _db_ready():
    """Create schema + seed once, before any test (client or db) runs."""
    init_db()
    with SessionLocal() as session:
        seed_all(session)
        session.commit()
    yield


@pytest.fixture(scope="session")
def client():
    """FastAPI TestClient with the lifespan run (schema + seed)."""
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture()
def db():
    session: Session = SessionLocal()
    try:
        yield session
    finally:
        session.close()