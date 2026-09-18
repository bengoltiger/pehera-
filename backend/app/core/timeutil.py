"""Shared UTC time helpers.

Single source of truth for "now" and ISO-8601 serialisation so the whole
stack emits naive-UTC ISO strings suffixed with `Z` (Section 97). Keep this
module dependency-free to avoid import cycles.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional


def utcnow() -> dt.datetime:
    """Naive UTC wall-clock, matching what SQLAlchemy stores in the DB."""
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def iso_utc(value: Optional[dt.datetime]) -> Optional[str]:
    """Naive-UTC datetime -> ISO-8601 with explicit `Z` suffix."""
    if value is None:
        return None
    return value.isoformat() + "Z"