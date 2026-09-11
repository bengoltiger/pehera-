"""Citizen mobile app API (prototype CD-08, CD-12).

The authority's People screen reads the same registry the citizen app writes:

  * ``POST /api/citizens/heartbeat`` -- the citizen app reports its live fix,
    battery, bluetooth state; may declare itself ``offline`` or ``relay`` when a
    nearby peer is forwarding its fix over Bluetooth (SIMULATED);
  * ``POST /api/citizens/{persona}/help`` -- a citizen asks for help; the
    authority sees it on the People screen immediately (SSE ``citizen.help``);
  * ``GET  /api/citizens`` -- authority-only registry view: live *or* last-known
    location for every persona, with connectivity state and relay metadata.

Privacy honesty: fix history is kept in memory only, is capped, and is never
persisted. All of it is demo data labelled ``is_simulated: true``.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.security.auth import get_current_user, require_role
from app.services.citizens import PERSONAS, get_registry

router = APIRouter(prefix="/citizens", tags=["people", "citizens"])

_reg = get_registry()


class FixBody(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)
    accuracy: float = Field(default=25, ge=0, le=20000)


class HeartbeatBody(BaseModel):
    persona_id: Optional[str] = None
    codename: Optional[str] = None
    fix: Optional[FixBody] = None
    announced: str = Field(default="online", pattern="^(online|offline|relay)$")
    via_relay: Optional[str] = None
    ble_enabled: bool = True
    bt_mode: str = Field(default="simulated", pattern="^(native|web|simulated|off)$")
    battery: Optional[float] = Field(default=None, ge=0, le=100)
    heading_deg: Optional[float] = Field(default=None, ge=0, le=360)
    speed_kmh: Optional[float] = Field(default=None, ge=0)
    note: Optional[str] = None


class HelpBody(BaseModel):
    message: str = Field(default="", max_length=300)


class AckBody(BaseModel):
    acknowledged_by: str = Field(default="", max_length=80)


@router.get("/personas", summary="Demo citizen personas")
def list_personas(user=Depends(get_current_user)) -> dict:
    return {
        "count": len(PERSONAS),
        "personas": _reg.personas(),
        "is_simulated": True,
        "note": "These personas are fictional demo records used to exercise the "
                "citizen ↔ authority coordination screens.",
    }


@router.post("/heartbeat", summary="Citizen app location heartbeat (direct or BLE-relay)")
def heartbeat(body: HeartbeatBody, user=Depends(get_current_user)) -> dict:
    payload = body.model_dump()
    fix = payload.pop("fix", None)
    if fix:
        payload["fix"] = fix  # already a plain dict after model_dump()
    try:
        result = _reg.heartbeat(payload.get("persona_id") or payload.get("codename"), payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail={
            "error": "persona_not_found",
            "message": str(exc),
        }) from exc
    result["is_simulated"] = True
    return result


@router.post("/{persona_id}/help", summary="Citizen asks for help at their location")
def request_help(persona_id: str, body: HelpBody, user=Depends(get_current_user)) -> dict:
    try:
        snap = _reg.request_help(persona_id, body.message)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail={
            "error": "persona_not_found",
            "message": str(exc),
        }) from exc
    snap["is_simulated"] = True
    return snap


@router.post("/{persona_id}/help/ack",
             summary="Authority acknowledges a citizen's help request",
             dependencies=[Depends(require_role("authority", "administrator"))])
def ack_help(persona_id: str, body: AckBody, user=Depends(get_current_user)) -> dict:
    ack_by = body.acknowledged_by or (user.full_name if user else "Authority")
    try:
        snap = _reg.ack_help(persona_id, ack_by)
    except ValueError as exc:
        raise HTTPException(status_code=404 if "unknown" in str(exc).lower() else 409, detail={
            "error": "help_not_acknowledged",
            "message": str(exc),
        }) from exc
    snap["is_simulated"] = True
    return snap


@router.post("/{persona_id}/help/resolve",
             summary="Authority marks a citizen's help request resolved",
             dependencies=[Depends(require_role("authority", "administrator"))])
def resolve_help(persona_id: str, body: Optional[AckBody] = None,
                 user=Depends(get_current_user)) -> dict:
    resolved_by = (body.acknowledged_by if body else None) or (user.full_name if user else "Authority")
    try:
        snap = _reg.resolve_help(persona_id, resolved_by)
    except ValueError as exc:
        raise HTTPException(status_code=404 if "unknown" in str(exc).lower() else 409, detail={
            "error": "help_not_resolved",
            "message": str(exc),
        }) from exc
    snap["is_simulated"] = True
    return snap


@router.get("", summary="Authority: live registry of citizen personas",
            dependencies=[Depends(require_role("authority", "administrator"))])
def list_citizens(history: bool = False, user=Depends(get_current_user)) -> dict:
    people = _reg.snapshot(include_history=history)
    return {
        "count": len(people),
        "citizens": people,
        "is_simulated": True,
        "note": "Demo personas only. A 'relay' state means the fix was forwarded "
                "by a nearby PEHRA phone over Bluetooth because the citizen lost "
                "their network (SIMULATED for the prototype).",
    }


@router.post("/reset", summary="Authority: reset citizen registry to pristine state",
             dependencies=[Depends(require_role("authority", "administrator"))])
def reset_citizens(user=Depends(get_current_user)) -> dict:
    _reg.reset()
    return {"count": len(PERSONAS), "reset": True,
            "note": "Citizen registry reset to its pristine demo state."}