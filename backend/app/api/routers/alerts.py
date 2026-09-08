"""Alert endpoints: recommendation review, composition, approval, lifecycle."""
from __future__ import annotations

import datetime as dt
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.alerts.engine import (
    ACTIVE_STATUSES,
    compose_alert_content,
    dedup_key,
    estimate_exposed_population,
    evaluate_triggers,
    record_transition,
    validate_geofence,
)
from app.core.risk_config import ACTION_LIBRARY, ALERTS, HAZARDS
from app.db.models import Alert, Incident, Location, User, new_id
from app.db.session import get_db
from app.schemas.api import (
    AcknowledgeRequest,
    AlertCreate,
    AlertPatch,
    AlertPreviewRequest,
)
from app.security.auth import (
    get_current_user,
    get_current_user_optional,
    record_audit,
    require_authority,
    sanitize_text,
)
from app.services.alerts import (
    acknowledge_alert,
    alert_to_dict,
    cancel_alert,
    deliver_alert,
    incident_to_dict,
    issue_alert,
    resolve_alert,
)
from app.services.clock import get_state
from app.services.prediction import compute_prediction

router = APIRouter(tags=["alerts"])


def _get_alert(db: Session, alert_id: str) -> Alert:
    alert = db.get(Alert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail={"error": "alert_not_found",
                                                     "message": f"No alert with id '{alert_id}'."})
    return alert


@router.get(
    "/alerts",
    summary="List alerts",
    description=(
        "Filterable alert list. `status=active` returns everything still in play "
        "(recommended, issued, delivered, acknowledged, updated, escalated).\n\n"
        "Alerts with `is_ai_generated: true` and status `recommended` are AI-assisted "
        "*proposals* — they have not been issued by any authority (Section 30)."
    ),
)
def list_alerts(
    status: str = Query(default="all", description="all | active | recommended | issued | resolved"),
    location_id: Optional[str] = None,
    level: Optional[str] = Query(default=None, pattern="^(WATCH|WARNING|CRITICAL)$"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    q = db.query(Alert)
    if status == "active":
        q = q.filter(Alert.status.in_(ACTIVE_STATUSES))
    elif status != "all":
        q = q.filter(Alert.status == status)
    if location_id:
        q = q.filter(Alert.location_id == location_id)
    if level:
        q = q.filter(Alert.level == level)
    total = q.count()
    rows = q.order_by(Alert.created_at.desc()).offset(offset).limit(limit).all()
    return {
        "total": total,
        "count": len(rows),
        "offset": offset,
        "alerts": [alert_to_dict(db, a, include_timeline=False) for a in rows],
        "note": "Recommended alerts are AI-assisted proposals awaiting authority approval.",
    }


@router.get(
    "/alerts/{alert_id}",
    summary="Alert detail with full lifecycle timeline",
    responses={404: {"description": "Unknown alert"}},
)
def get_alert(alert_id: str, db: Session = Depends(get_db)) -> dict:
    return alert_to_dict(db, _get_alert(db, alert_id))


@router.post(
    "/alerts",
    status_code=201,
    summary="Create an alert (authority only)",
    description=(
        "Authority alert composer. Citizens receive 403 — they can never issue an official "
        "warning (Section 52). Set `issue_immediately` to publish on creation; otherwise the "
        "alert is created in `recommended` state for review."
    ),
    responses={
        201: {"description": "Alert created"},
        400: {"description": "Validation failed"},
        403: {"description": "Role not permitted"},
        404: {"description": "Unknown location or hazard"},
    },
)
def create_alert(
    payload: AlertCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_authority),
) -> dict:
    loc = db.get(Location, payload.location_id)
    if not loc:
        raise HTTPException(status_code=404, detail={"error": "location_not_found",
                                                     "message": f"No location '{payload.location_id}'."})
    if payload.hazard not in HAZARDS:
        raise HTTPException(
            status_code=404,
            detail={"error": "unknown_hazard", "message": f"Unknown hazard '{payload.hazard}'.",
                    "valid": list(HAZARDS.keys())},
        )
    gf = payload.geofence
    geofence = {"lat": gf.lat if gf.lat is not None else loc.latitude,
                "lng": gf.lng if gf.lng is not None else loc.longitude,
                "radius_km": gf.radius_km or ALERTS["geofence_default_radius_km"],
                "points": gf.points}
    err = validate_geofence(gf.kind, geofence)
    if err:
        raise HTTPException(status_code=400, detail={"error": "invalid_geofence", "message": err})

    exposed, covered = estimate_exposed_population(
        db, location=loc, geofence_kind=gf.kind, geofence=geofence
    )
    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    hz = HAZARDS[payload.hazard]
    alert = Alert(
        id=new_id("alt"),
        location_id=loc.id,
        hazard=payload.hazard,
        level=payload.level,
        status="recommended",
        title=sanitize_text(payload.title or f"{payload.level} — {hz.label} risk in {loc.name}", max_length=200),
        message=sanitize_text(payload.message),
        message_hi=sanitize_text(payload.message_hi or ""),
        recommended_actions=[sanitize_text(a, max_length=200) for a in payload.recommended_actions]
        or ACTION_LIBRARY.get(payload.hazard, {}).get(payload.level, []),
        what=sanitize_text(payload.what or f"{hz.label} risk", max_length=300),
        where=f"{loc.name}, {loc.district}, {loc.state}",
        when=sanitize_text(payload.when or "See message", max_length=300),
        why=sanitize_text(payload.why or "Issued by authority", max_length=1000),
        what_to_do=sanitize_text(payload.what_to_do or "", max_length=1000),
        risk_score=0.0,
        confidence=0.0,
        geofence_kind=gf.kind,
        geofence={**geofence, "covered_location_ids": covered},
        estimated_exposed_population=exposed,
        target_audience=payload.target_audience,
        trigger_reason="Manually composed by an authorised officer.",
        trigger_kinds=["manual"],
        is_ai_generated=False,
        dedup_key=dedup_key(loc.id, payload.hazard),
        expires_at=now + dt.timedelta(hours=payload.expires_in_hours),
        scenario_tick=get_state(db).tick,
    )
    # attach the current engine numbers for context, if a prediction is possible
    pred = compute_prediction(db, loc, detail=True, persist=False)
    if pred.get("available"):
        alert.risk_score = pred["risk"]["overall"]
        alert.confidence = pred["risk"]["confidence"]["value"]
        alert.prediction_id = pred.get("prediction_id")
    db.add(alert)
    db.flush()
    record_transition(db, alert, to_status="recommended", to_level=payload.level,
                      actor=user.full_name, actor_role=user.role,
                      reason="Composed manually in the alert composer.", at=now)
    record_audit(db, actor=user, action="create_alert", entity_type="alert", entity_id=alert.id,
                 to_state="recommended", detail={"level": payload.level, "location": loc.id},
                 request=request)
    db.commit()

    if payload.issue_immediately:
        issue_alert(db, alert, user, note="Issued on creation.", request=request)
    db.refresh(alert)
    return alert_to_dict(db, alert)


@router.post(
    "/alerts/preview",
    summary="Preview the citizen-facing message before issuing",
    description=(
        "Generates the exact card a citizen would see, from the live risk engine (Section 32). "
        "Nothing is stored and nothing is sent."
    ),
)
def preview_alert(payload: AlertPreviewRequest, db: Session = Depends(get_db),
                  _user: User = Depends(require_authority)) -> dict:
    loc = db.get(Location, payload.location_id)
    if not loc:
        raise HTTPException(status_code=404, detail={"error": "location_not_found",
                                                     "message": "Unknown location."})
    pred = compute_prediction(db, loc, detail=True, persist=False, lang=payload.language)
    if not pred.get("available"):
        return {"available": False, "reason": pred.get("detail")}
    hazard = payload.hazard or pred["hazard"]["dominant"]
    trig = evaluate_triggers(
        risk=pred["risk"]["overall"],
        momentum_rate=pred["risk"]["momentum"]["rate_per_hour"],
        confidence=pred["risk"]["confidence"]["value"],
        prediction=pred,
    )
    level = payload.level or trig.level or "WATCH"
    content = compose_alert_content(location=loc, prediction=pred, level=level,
                                    hazard_key=hazard, triggers=trig)
    geofence = {"lat": loc.latitude, "lng": loc.longitude,
                "radius_km": ALERTS["geofence_default_radius_km"]}
    exposed, covered = estimate_exposed_population(db, location=loc, geofence_kind="radius",
                                                   geofence=geofence)
    return {
        "available": True,
        "suggested": {
            "level": level,
            "hazard": hazard,
            "hazard_label": HAZARDS[hazard].label if hazard in HAZARDS else hazard,
            **content,
            "geofence": {"kind": "radius", **geofence},
            "estimated_exposed_population": exposed,
            "covered_location_ids": covered,
        },
        "engine": {
            "risk": pred["risk"]["overall"],
            "hazard_score": pred["risk"]["hazard_score"],
            "exposure_score": pred["risk"]["exposure_score"],
            "confidence": pred["risk"]["confidence"]["value"],
            "severity": pred["risk"]["severity"],
            "momentum": pred["risk"]["momentum"],
            "triggers": trig.to_dict(),
        },
        "citizen_view": {
            "what": content["what"],
            "where": content["where"],
            "when": content["when"],
            "why": content["why"],
            "what_to_do": content["what_to_do"],
            "confidence": content["confidence"],
            "level": level,
            "message": content["message"] if payload.language == "en" else content["message_hi"],
        },
        "disclaimer": "AI-assisted draft. An authorised officer must review and approve before issue.",
    }


@router.post(
    "/alerts/{alert_id}/issue",
    summary="Approve and issue an alert (authority only)",
    description=(
        "The human-in-the-loop gate. Moves the alert to `issued`, records who approved it and "
        "when, then runs the simulated multi-channel delivery. An AI recommendation only becomes "
        "an official warning through this endpoint (Section 30)."
    ),
    responses={403: {"description": "Role not permitted"}, 404: {"description": "Unknown alert"},
               409: {"description": "Alert is not in an issuable state"}},
)
def issue(alert_id: str, request: Request, note: str = "",
          db: Session = Depends(get_db), user: User = Depends(require_authority)) -> dict:
    alert = _get_alert(db, alert_id)
    if alert.status in ("resolved", "cancelled", "expired"):
        raise HTTPException(
            status_code=409,
            detail={"error": "invalid_state",
                    "message": f"Alert is {alert.status} and cannot be issued."},
        )
    issue_alert(db, alert, user, note=note, request=request)
    return alert_to_dict(db, alert)


@router.patch(
    "/alerts/{alert_id}",
    summary="Modify an alert (authority only)",
    description="Edit wording, actions, level, expiry or status. Every change is recorded as a "
                "transition and in the audit log.",
    responses={403: {"description": "Role not permitted"}, 404: {"description": "Unknown alert"}},
)
def patch_alert(alert_id: str, payload: AlertPatch, request: Request,
                db: Session = Depends(get_db), user: User = Depends(require_authority)) -> dict:
    alert = _get_alert(db, alert_id)
    changes = {}
    if payload.message is not None:
        alert.message = sanitize_text(payload.message)
        changes["message"] = True
    if payload.message_hi is not None:
        alert.message_hi = sanitize_text(payload.message_hi)
        changes["message_hi"] = True
    if payload.recommended_actions is not None:
        alert.recommended_actions = [sanitize_text(a, max_length=200) for a in payload.recommended_actions]
        changes["recommended_actions"] = True
    if payload.what_to_do is not None:
        alert.what_to_do = sanitize_text(payload.what_to_do)
        changes["what_to_do"] = True
    if payload.expires_in_hours is not None:
        alert.expires_at = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) + dt.timedelta(
            hours=payload.expires_in_hours
        )
        changes["expires_at"] = True
    if payload.level is not None and payload.level != alert.level:
        record_transition(db, alert, to_status=alert.status, to_level=payload.level,
                          actor=user.full_name, actor_role=user.role,
                          reason=sanitize_text(payload.reason) or "Level changed by authority.")
        changes["level"] = payload.level
    if payload.status == "resolved":
        resolve_alert(db, alert, user, reason=payload.reason or "Resolved by authority.")
        changes["status"] = "resolved"
    elif payload.status == "cancelled":
        cancel_alert(db, alert, user, reason=payload.reason or "Cancelled by authority.",
                     request=request)
        changes["status"] = "cancelled"
    elif payload.status == "issued" and alert.status not in ("issued", "delivered", "acknowledged"):
        issue_alert(db, alert, user, note=payload.reason, request=request)
        changes["status"] = "issued"
    else:
        alert.update_count += 1
    record_audit(db, actor=user, action="update_alert", entity_type="alert", entity_id=alert.id,
                 detail=changes, request=request)
    db.commit()
    db.refresh(alert)
    return alert_to_dict(db, alert)


@router.post(
    "/alerts/{alert_id}/acknowledge",
    summary="Acknowledge an alert",
    description="Citizens tap 'I understand'; authorities acknowledge operationally. The "
                "acknowledgement time feeds the delivery funnel (Section 50).",
    responses={404: {"description": "Unknown alert"}},
)
def acknowledge(alert_id: str, payload: AcknowledgeRequest, request: Request,
                db: Session = Depends(get_db),
                user: Optional[User] = Depends(get_current_user_optional)) -> dict:
    alert = _get_alert(db, alert_id)
    acknowledge_alert(db, alert, user, note=payload.note, request=request)
    db.refresh(alert)
    return alert_to_dict(db, alert)


@router.post(
    "/alerts/{alert_id}/deliver",
    summary="Re-run simulated delivery (authority only)",
    description="Fans the alert out again across enabled channels. Every delivery record is "
                "marked SIMULATED — nothing leaves this machine (Section 49).",
)
def redeliver(alert_id: str, db: Session = Depends(get_db),
              user: User = Depends(require_authority)) -> dict:
    alert = _get_alert(db, alert_id)
    rows = deliver_alert(db, alert)
    return {
        "alert_id": alert.id,
        "deliveries": [
            {"channel": r.channel, "status": r.status, "recipient_count": r.recipient_count,
             "provider": r.provider, "is_simulated": r.is_simulated, "detail": r.detail}
            for r in rows
        ],
        "warning": "SIMULATED DELIVERY — no push, SMS or email was actually transmitted.",
    }


@router.get(
    "/alerts/for-location/{location_id}",
    summary="Alerts relevant to a citizen at a location",
    description="Active alerts whose geofence covers this location, newest first.",
)
def alerts_for_location(location_id: str, db: Session = Depends(get_db)) -> dict:
    rows = (
        db.query(Alert)
        .filter(Alert.status.in_(ACTIVE_STATUSES))
        .order_by(Alert.created_at.desc())
        .all()
    )
    mine = [
        a for a in rows
        if a.location_id == location_id
        or location_id in ((a.geofence or {}).get("covered_location_ids") or [])
    ]
    issued = [a for a in mine if a.status in ("issued", "delivered", "acknowledged",
                                              "updated", "escalated")]
    return {
        "count": len(mine),
        "issued": [alert_to_dict(db, a, include_timeline=False) for a in issued],
        "pending_recommendations": [
            alert_to_dict(db, a, include_timeline=False) for a in mine if a.status == "recommended"
        ],
        "note": "Only 'issued' alerts are official. Recommendations are shown separately and are "
                "clearly labelled as awaiting authority approval.",
    }


@router.get("/incidents", summary="Incident records with risk story and lifecycle timeline")
def list_incidents(
    status: Optional[str] = Query(default=None, pattern="^(open|resolved|archived|evaluated)$"),
    location_id: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict:
    q = db.query(Incident)
    if status:
        q = q.filter(Incident.status == status)
    if location_id:
        q = q.filter(Incident.location_id == location_id)
    rows = q.order_by(Incident.detected_at.desc()).limit(limit).all()
    return {"count": len(rows), "incidents": [incident_to_dict(db, i) for i in rows]}


@router.get("/incidents/{incident_id}", summary="Incident detail",
            responses={404: {"description": "Unknown incident"}})
def get_incident(incident_id: str, db: Session = Depends(get_db)) -> dict:
    inc = db.get(Incident, incident_id)
    if not inc:
        raise HTTPException(status_code=404, detail={"error": "not_found",
                                                     "message": f"No incident '{incident_id}'."})
    return incident_to_dict(db, inc)


@router.get(
    "/actions/{hazard}/{level}",
    summary="Recommended operational actions",
    description="AI-assisted action suggestions for a hazard/severity pair (Section 29). "
                "These are recommendations, not instructions — authorities decide.",
)
def get_actions(hazard: str, level: str) -> dict:
    if hazard not in ACTION_LIBRARY:
        raise HTTPException(status_code=404, detail={"error": "unknown_hazard",
                                                     "message": f"No action library for '{hazard}'.",
                                                     "valid": list(ACTION_LIBRARY.keys())})
    lvl = level.upper()
    if lvl not in ("WATCH", "WARNING", "CRITICAL"):
        raise HTTPException(status_code=400, detail={"error": "invalid_level",
                                                     "message": "Level must be WATCH, WARNING or CRITICAL."})
    return {
        "hazard": hazard,
        "level": lvl,
        "actions": ACTION_LIBRARY[hazard][lvl],
        "label": "AI-assisted recommendations",
        "disclaimer": "PEHRA supports emergency authorities; it does not replace them.",
    }
