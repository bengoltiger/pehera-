"""Authentication & user endpoints."""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.models import Location, User
from app.db.session import get_db
from app.schemas.api import LoginRequest, TokenResponse, UserOut
from app.security.auth import (
    create_access_token,
    get_current_user,
    record_audit,
    require_admin,
)
from app.security.passwords import verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Sign in and receive a bearer token",
    description=(
        "Exchanges username/password for a signed JWT. Demo accounts: "
        "`citizen`/`citizen123`, `authority`/`authority123`, `admin`/`admin12345`. "
        "The token carries the role that the RBAC layer enforces on every protected endpoint."
    ),
    responses={401: {"description": "Invalid credentials"}},
)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.query(User).filter(User.username == payload.username.strip().lower()).first()
    if not user or not verify_password(payload.password, user.password_hash):
        # identical response for unknown user and wrong password
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_credentials", "message": "Username or password is incorrect."},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "inactive", "message": "This account has been deactivated."},
        )
    token, expires = create_access_token(user)
    user.last_login_at = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    record_audit(db, actor=user, action="login", entity_type="user", entity_id=user.id,
                 to_state="authenticated", request=request)
    db.commit()
    return TokenResponse(
        access_token=token,
        expires_at=expires,
        user=UserOut(
            id=user.id, username=user.username, full_name=user.full_name, role=user.role,
            organisation=user.organisation, home_location_id=user.home_location_id,
            language=user.language,
        ),
    )


@router.get(
    "/me",
    response_model=UserOut,
    summary="Current authenticated user",
    responses={401: {"description": "Not authenticated"}},
)
def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut(
        id=user.id, username=user.username, full_name=user.full_name, role=user.role,
        organisation=user.organisation, home_location_id=user.home_location_id,
        language=user.language,
    )


@router.patch(
    "/me/location",
    response_model=UserOut,
    summary="Set the signed-in citizen's home area",
    description="Stores only a coarse reference to a monitored ward or village — never a precise "
                "GPS coordinate (Section 67).",
    responses={404: {"description": "Unknown location"}},
)
def set_home(location_id: str, user: User = Depends(get_current_user),
             db: Session = Depends(get_db)) -> UserOut:
    loc = db.get(Location, location_id)
    if not loc:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": f"No monitored location with id '{location_id}'."},
        )
    user.home_location_id = loc.id
    db.commit()
    return UserOut(
        id=user.id, username=user.username, full_name=user.full_name, role=user.role,
        organisation=user.organisation, home_location_id=user.home_location_id,
        language=user.language,
    )


@router.get(
    "/users",
    summary="List users (administrator only)",
    description="Administrative user list. Password hashes are never returned.",
)
def list_users(db: Session = Depends(get_db), _admin: User = Depends(require_admin)) -> dict:
    users = db.query(User).order_by(User.role, User.username).all()
    return {
        "count": len(users),
        "users": [
            {
                "id": u.id, "username": u.username, "full_name": u.full_name, "role": u.role,
                "organisation": u.organisation, "home_location_id": u.home_location_id,
                "language": u.language, "is_active": u.is_active,
                "last_login_at": u.last_login_at.isoformat() + "Z" if u.last_login_at else None,
            }
            for u in users
        ],
    }


@router.get(
    "/demo-accounts",
    summary="Demo credentials",
    description="Prototype convenience endpoint listing the seeded demo accounts so judges can "
                "sign in quickly. It exposes no real user data.",
)
def demo_accounts() -> dict:
    return {
        "note": "Seeded prototype accounts only. Real deployments create users through the admin API.",
        "accounts": [
            {"username": "meera", "password": "citizen123", "role": "citizen", "persona_id": "persona_1",
             "description": "Meera Nair — Kurla Ward (Person 1)"},
            {"username": "arjun", "password": "citizen123", "role": "citizen", "persona_id": "persona_2",
             "description": "Arjun Deshpande — Colaba Ward (Person 2)"},
            {"username": "farhan", "password": "citizen123", "role": "citizen", "persona_id": "persona_3",
             "description": "Farhan Shaikh — Mahim Ward (Person 3)"},
            {"username": "citizen", "password": "citizen123", "role": "citizen",
             "description": "Legacy Demo Citizen — Colaba Ward"},
            {"username": "nagrik", "password": "citizen123", "role": "citizen",
             "description": "Legacy Hindi-language citizen — Kurla–Mithi River Ward"},
            {"username": "authority", "password": "authority123", "role": "authority",
             "description": "BMC disaster management cell — command centre, alert approval"},
            {"username": "admin", "password": "admin12345", "role": "administrator",
             "description": "Administrator — audit log, system controls, user management"},
        ],
    }
