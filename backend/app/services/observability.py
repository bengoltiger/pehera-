"""Internal observability (Section 87)."""
from __future__ import annotations

import datetime as dt
import logging
import time
from contextlib import contextmanager
from typing import Optional

from sqlalchemy.orm import Session

from app.db.models import SystemLog

logger = logging.getLogger("pehra")

_MAX_ROWS = 2000


def log_event(
    db: Session,
    *,
    level: str,
    component: str,
    event: str,
    message: str,
    context: Optional[dict] = None,
    duration_ms: Optional[float] = None,
    commit: bool = False,
) -> None:
    entry = SystemLog(
        level=level,
        component=component,
        event=event,
        message=message,
        context=context,
        duration_ms=duration_ms,
    )
    db.add(entry)
    getattr(logger, level if level in ("info", "warning", "error") else "info")(
        "[%s] %s — %s", component, event, message
    )
    if commit:
        db.commit()


def trim_logs(db: Session) -> None:
    count = db.query(SystemLog).count()
    if count > _MAX_ROWS:
        oldest = (
            db.query(SystemLog.id)
            .order_by(SystemLog.id.asc())
            .limit(count - _MAX_ROWS)
            .all()
        )
        ids = [o[0] for o in oldest]
        if ids:
            db.query(SystemLog).filter(SystemLog.id.in_(ids)).delete(synchronize_session=False)


@contextmanager
def timed(db: Session, *, component: str, event: str, message: str, context: Optional[dict] = None):
    start = time.perf_counter()
    try:
        yield
    except Exception as exc:
        log_event(
            db,
            level="error",
            component=component,
            event=f"{event}_failed",
            message=f"{message}: {type(exc).__name__}: {exc}",
            context=context,
            duration_ms=(time.perf_counter() - start) * 1000,
        )
        raise
    else:
        log_event(
            db,
            level="info",
            component=component,
            event=event,
            message=message,
            context=context,
            duration_ms=(time.perf_counter() - start) * 1000,
        )


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
