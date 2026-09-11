"""Database session management."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.db.models import Base

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    echo=False,
    future=True,
)


@event.listens_for(engine, "connect")
def _sqlite_pragmas(dbapi_connection, _record):  # pragma: no cover - driver level
    if settings.database_url.startswith("sqlite"):
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def _migrate() -> None:
    """Additive, idempotent column migrations for existing SQLite files.

    ``create_all`` only creates missing tables — it never adds columns to an
    existing one, so each column introduced after first deploy needs a small
    guard like the one below.
    """
    if not settings.database_url.startswith("sqlite"):
        return
    with engine.begin() as conn:
        cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(infrastructure)")}
        for col, ddl in (
            ("address", "ALTER TABLE infrastructure ADD COLUMN address VARCHAR(200)"),
            ("phone", "ALTER TABLE infrastructure ADD COLUMN phone VARCHAR(40)"),
        ):
            if col not in cols:
                conn.exec_driver_sql(ddl)
        lcols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(locations)")}
        for col, ddl in (
            ("slope_deg", "ALTER TABLE locations ADD COLUMN slope_deg FLOAT DEFAULT 0"),
            ("coastal_exposure", "ALTER TABLE locations ADD COLUMN coastal_exposure FLOAT DEFAULT 0"),
        ):
            if col not in lcols:
                conn.exec_driver_sql(ddl)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _migrate()


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
