"""Authentication, RBAC and audit (Sections 51, 52).

Roles
-----
citizen        read own risk, acknowledge alerts
authority      everything a citizen can do + issue/modify/resolve alerts,
               run scenarios, view the command centre
administrator  everything + user management, system controls, audit access

A citizen can NEVER issue an official alert. That is enforced here, in one
place, and asserted by the test-suite.
"""
from __future__ import annotations

import datetime as dt
from typing import Callable, Iterable, Optional

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import AuditLog, User
from app.db.session import get_db

ROLES = ("citizen", "authority", "administrator")
ROLE_RANK = {"citizen": 1, "authority": 2, "administrator": 3}

bearer = HTTPBearer(auto_error=False)


def create_access_token(user: User) -> tuple[str, dt.datetime]:
    expires = dt.datetime.now(dt.timezone.utc) + dt.timedelta(
        minutes=settings.access_token_ttl_minutes
    )
    payload = {
        "sub": user.id,
        "username": user.username,
        "role": user.role,
        "iat": int(dt.datetime.now(dt.timezone.utc).timestamp()),
        "exp": int(expires.timestamp()),
        "iss": "pehra",
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, expires


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm], issuer="pehra"
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "token_expired", "message": "Your session has expired. Please sign in again."},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_token", "message": "Authentication token is not valid."},
        )


def get_current_user_optional(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
    db: Session = Depends(get_db),
) -> Optional[User]:
    if not creds:
        return None
    payload = decode_token(creds.credentials)
    user = db.get(User, payload.get("sub"))
    if not user or not user.is_active:
        return None
    return user


def get_current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if not creds:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "not_authenticated", "message": "Sign in to continue."},
        )
    payload = decode_token(creds.credentials)
    user = db.get(User, payload.get("sub"))
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "user_inactive", "message": "This account is not active."},
        )
    return user


def require_role(*allowed: str) -> Callable:
    """Dependency factory enforcing a minimum role set."""

    def _dep(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "forbidden",
                    "message": (
                        f"Role '{user.role}' is not permitted to perform this action. "
                        f"Required: {', '.join(allowed)}."
                    ),
                    "required_roles": list(allowed),
                    "your_role": user.role,
                },
            )
        return user

    return _dep


require_authority = require_role("authority", "administrator")
require_admin = require_role("administrator")


def record_audit(
    db: Session,
    *,
    actor: Optional[User],
    action: str,
    entity_type: str,
    entity_id: Optional[str] = None,
    from_state: Optional[str] = None,
    to_state: Optional[str] = None,
    detail: Optional[dict] = None,
    request: Optional[Request] = None,
) -> AuditLog:
    entry = AuditLog(
        actor_id=actor.id if actor else None,
        actor_name=actor.full_name if actor else "system",
        actor_role=actor.role if actor else "system",
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        from_state=from_state,
        to_state=to_state,
        detail=detail,
        ip_address=(request.client.host if request and request.client else None),
    )
    db.add(entry)
    return entry


def roles_at_least(role: str, minimum: str) -> bool:
    return ROLE_RANK.get(role, 0) >= ROLE_RANK.get(minimum, 99)


def sanitize_text(value: str, *, max_length: int = 2000) -> str:
    """Defensive input sanitisation for free-text fields that are rendered.

    React escapes by default, but alerts are also emitted to SMS/push adapters
    where markup would be meaningless noise. Strip control characters and tags.
    """
    if value is None:
        return ""
    cleaned = str(value).replace("\x00", "")
    cleaned = "".join(ch for ch in cleaned if ch == "\n" or ch == "\t" or ord(ch) >= 32)
    for bad in ("<script", "</script", "<iframe", "javascript:", "onerror=", "onload="):
        cleaned = cleaned.replace(bad, "")
        cleaned = cleaned.replace(bad.upper(), "")
    return cleaned.strip()[:max_length]


def check_roles(allowed: Iterable[str], role: str) -> bool:
    return role in set(allowed)
