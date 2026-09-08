"""In-process sliding-window rate limiter (Section 52).

Deliberately simple and dependency-free. A production deployment would move
this to Redis; the interface would not change.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict

from fastapi import HTTPException, Request, status

from app.core.config import settings

_lock = threading.Lock()
_buckets: Dict[str, Deque[float]] = defaultdict(deque)

WRITE_METHODS = {"POST", "PATCH", "PUT", "DELETE"}


def _prune(bucket: Deque[float], window: float, now: float) -> None:
    while bucket and now - bucket[0] > window:
        bucket.popleft()


def check_rate_limit(request: Request) -> None:
    if not settings.rate_limit_enabled:
        return
    client = request.client.host if request.client else "unknown"
    is_write = request.method in WRITE_METHODS
    key = f"{client}:{'w' if is_write else 'r'}"
    limit = settings.rate_limit_write_requests if is_write else settings.rate_limit_requests
    window = float(settings.rate_limit_window_seconds)
    now = time.time()
    with _lock:
        bucket = _buckets[key]
        _prune(bucket, window, now)
        if len(bucket) >= limit:
            retry = int(window - (now - bucket[0])) + 1
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": "rate_limited",
                    "message": f"Too many requests. Try again in {retry}s.",
                    "limit": limit,
                    "window_seconds": window,
                },
                headers={"Retry-After": str(retry)},
            )
        bucket.append(now)


def reset_rate_limits() -> None:
    with _lock:
        _buckets.clear()
