"""Password hashing. bcrypt via the reference implementation."""
from __future__ import annotations

import bcrypt

from app.core.config import settings


class WeakPassword(ValueError):
    pass


def hash_password(plain: str) -> str:
    if len(plain) < settings.password_min_length:
        raise WeakPassword(
            f"Password must be at least {settings.password_min_length} characters"
        )
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=10)).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False
