"""Alert service: creation from predictions, lifecycle, delivery, incidents.

Implements Sections 21, 22, 29, 30, 48, 49, 50, 69, 76.
"""
from __future__ import annotations

import datetime as dt
from typing import List, Optional

from sqlalchemy.orm import Session

from app.alerts.channels import get_channels
from app.alerts.engine import (
    ACTIVE_STATUSES,
    LEVEL_ORDER,
    TriggerEvaluation,
    compose_alert_content,
    decide_dedup,
    dedup_key,
    estimate_exposed_population,
    evaluate_triggers,
    record_transition,
    should_resolve,
)
from app.core.risk_config import ALERTS, HAZARDS
from app.db.models import (
    Alert,
    AlertAcknowledgement,
    AlertDelivery,
    AlertTransition,
    Incident,
    Location,
    User,
    new_id,
)
from app.security.auth import record_audit, sanitize_text
from app.services.observability import log_event


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# Recommendation pipeline (AI proposes)
# ---------------------------------------------------------------------------
def evaluate_and_recommend(
    db: Session, *, location: Location, prediction: dict, threat_cell_id: Optional[str] = None,
    threat_cell_entering: bool = False, tick: Optional[int] = None,
) -> dict:
    """Run the alert decision engine for one location and reconcile with the
    currently active alert. Returns a description of what happened."""
    if not prediction.get("available"):
        return {"action": "skipped", "reason": "No prediction available for this location."}

    now = utcnow()
    risk = prediction["risk"]["overall"]
    conf = prediction["risk"]["confidence"]["value"]
    momentum_rate = prediction["risk"]["momentum"]["rate_per_hour"]
    hazard_key = prediction["hazard"]["dominant"]

    river = (prediction.get("inputs") or {}).get("river_level_ratio") or {}
    river_crossed = bool(river.get("value") is not None and river["value"] >= 1.0)

    triggers = evaluate_triggers(
        risk=risk,
        momentum_rate=momentum_rate,
        confidence=conf,
        prediction=prediction,
        threat_cell_entering=threat_cell_entering,
        river_threshold_crossed=river_crossed,
    )

    # ---- resolve / de-escalate existing alerts first ----
    active = (
        db.query(Alert)
        .filter(Alert.location_id == location.id, Alert.status.in_(ACTIVE_STATUSES))
        .all()
    )
    resolved_info = []
    for al in active:
        reason = should_resolve(al, risk, now)
        if reason:
            record_transition(db, al, to_status="resolved", actor="PEHRA alert engine",
                              reason=reason, at=now)
            al.resolved_at = now
            resolved_info.append({"alert_id": al.id, "reason": reason})
            _close_incident(db, al, now, risk)
    if resolved_info:
        db.commit()

    if not triggers.should_alert:
        return {
            "action": "no_alert",
            "triggers": triggers.to_dict(),
            "resolved": resolved_info,
            "reason": triggers.blocked_reason or "No trigger condition is met.",
        }

    level = triggers.level or "WATCH"

    # Alert grouping (Section 48): if this location already carries an active
    # alert at a HIGHER level for a different hazard, do not add a second,
    # weaker notification -- group it under the stronger one.
    stronger = [
        a for a in db.query(Alert).filter(
            Alert.location_id == location.id, Alert.status.in_(ACTIVE_STATUSES)
        ).all()
        if a.hazard != hazard_key and LEVEL_ORDER[a.level] > LEVEL_ORDER[level]
    ]
    if stronger:
        return {
            "action": "grouped",
            "alert_id": stronger[0].id,
            "reason": (
                f"A {stronger[0].level} alert is already active for {location.name}. "
                f"This {level}-level {hazard_key} signal is grouped under it instead of "
                "sending a second, weaker notification."
            ),
            "triggers": triggers.to_dict(),
            "resolved": resolved_info,
        }

    decision = decide_dedup(
        db, location_id=location.id, hazard=hazard_key, level=level, risk=risk, now=now
    )

    if decision.action == "suppress":
        log_event(db, level="info", component="alerts", event="alert_suppressed",
                  message=decision.reason, context={"location": location.id}, commit=True)
        return {
            "action": "suppressed",
            "reason": decision.reason,
            "alert_id": decision.existing.id if decision.existing else None,
            "triggers": triggers.to_dict(),
            "resolved": resolved_info,
        }

    content = compose_alert_content(
        location=location, prediction=prediction, level=level, hazard_key=hazard_key, triggers=triggers
    )
    geofence = {
        "lat": location.latitude,
        "lng": location.longitude,
        "radius_km": ALERTS["geofence_default_radius_km"],
    }
    exposed, covered_ids = estimate_exposed_population(
        db, location=location, geofence_kind="radius", geofence=geofence
    )
    lead = prediction.get("lead_time") or {}

    if decision.action == "create":
        alert = Alert(
            id=new_id("alt"),
            location_id=location.id,
            hazard=hazard_key,
            level=level,
            status="recommended",
            title=content["title"],
            message=content["message"],
            message_hi=content["message_hi"],
            recommended_actions=content["recommended_actions"],
            what=content["what"],
            where=content["where"],
            when=content["when"],
            why=content["why"],
            what_to_do=content["what_to_do"],
            risk_score=round(risk, 1),
            confidence=round(conf, 1),
            prediction_id=prediction.get("prediction_id"),
            threat_cell_id=threat_cell_id,
            geofence_kind="radius",
            geofence={**geofence, "covered_location_ids": covered_ids},
            estimated_exposed_population=exposed,
            target_audience=["citizen", "authority"],
            trigger_reason=" ".join(triggers.reasons),
            trigger_kinds=triggers.kinds,
            is_ai_generated=True,
            dedup_key=dedup_key(location.id, hazard_key),
            lead_time_seconds=lead.get("seconds"),
            scenario_tick=tick,
        )
        db.add(alert)
        db.flush()
        record_transition(db, alert, to_status="recommended", to_level=level,
                          actor="PEHRA alert engine",
                          reason="AI-assisted recommendation generated from the risk engine.", at=now)
        # absorb weaker active alerts at the same location so citizens see one
        # coherent warning rather than a stack of overlapping ones
        for weaker in db.query(Alert).filter(
            Alert.location_id == location.id, Alert.status.in_(ACTIVE_STATUSES),
            Alert.id != alert.id,
        ).all():
            if LEVEL_ORDER[weaker.level] < LEVEL_ORDER[level]:
                record_transition(
                    db, weaker, to_status="resolved", actor="PEHRA alert engine",
                    reason=f"Superseded by the {level} alert {alert.id} for the same area.", at=now,
                )
                weaker.resolved_at = now
                weaker.supersedes_id = alert.id
        incident = _open_or_get_incident(db, location, hazard_key, prediction, now)
        alert.incident_id = incident.id
        _append_story(db, incident, now, f"PEHRA recommended a {level} alert. {triggers.reasons[0]}", "recommendation")
        db.commit()
        log_event(db, level="info", component="alerts", event="alert_recommended",
                  message=f"{level} recommended for {location.name}",
                  context={"alert": alert.id, "risk": risk}, commit=True)
        return {"action": "created", "alert_id": alert.id, "level": level,
                "triggers": triggers.to_dict(), "reason": decision.reason, "resolved": resolved_info}

    # update / escalate an existing alert
    alert = decision.existing
    assert alert is not None
    old_level = alert.level
    alert.title = content["title"]
    alert.message = content["message"]
    alert.message_hi = content["message_hi"]
    alert.recommended_actions = content["recommended_actions"]
    alert.what, alert.where = content["what"], content["where"]
    alert.when, alert.why = content["when"], content["why"]
    alert.what_to_do = content["what_to_do"]
    alert.risk_score = round(risk, 1)
    alert.confidence = round(conf, 1)
    alert.prediction_id = prediction.get("prediction_id")
    alert.estimated_exposed_population = exposed
    alert.trigger_reason = " ".join(triggers.reasons)
    alert.trigger_kinds = triggers.kinds
    alert.update_count += 1
    alert.scenario_tick = tick
    if lead.get("seconds") and not alert.lead_time_seconds:
        alert.lead_time_seconds = lead["seconds"]

    if decision.action == "escalate":
        escalated_up = LEVEL_ORDER[level] > LEVEL_ORDER[old_level]
        new_status = "escalated" if alert.status in ("issued", "delivered", "acknowledged", "updated", "escalated") else alert.status
        record_transition(db, alert, to_status=new_status, to_level=level,
                          actor="PEHRA alert engine", reason=decision.reason, at=now)
        if alert.incident_id:
            inc = db.get(Incident, alert.incident_id)
            if inc:
                _append_story(db, inc, now,
                              f"Alert {'escalated' if escalated_up else 'de-escalated'} {old_level} → {level}. {decision.reason}",
                              "escalation")
    else:
        new_status = "updated" if alert.status in ("issued", "delivered", "acknowledged") else alert.status
        record_transition(db, alert, to_status=new_status, actor="PEHRA alert engine",
                          reason=decision.reason, at=now)

    _update_incident_peak(db, alert, risk, now)
    db.commit()
    return {
        "action": decision.action,
        "alert_id": alert.id,
        "level": alert.level,
        "previous_level": old_level,
        "triggers": triggers.to_dict(),
        "reason": decision.reason,
        "resolved": resolved_info,
    }


# ---------------------------------------------------------------------------
# Human-in-the-loop actions (Section 30)
# ---------------------------------------------------------------------------
def issue_alert(db: Session, alert: Alert, user: User, *, note: str = "", request=None) -> Alert:
    now = utcnow()
    record_transition(
        db, alert, to_status="issued", actor=user.full_name, actor_role=user.role,
        reason=sanitize_text(note) or "Approved and issued by an authorised officer.", at=now,
    )
    alert.approved_by = user.id
    alert.approved_at = now
    alert.issued_at = now
    alert.is_ai_generated = alert.is_ai_generated  # provenance preserved
    if not alert.expires_at:
        alert.expires_at = now + dt.timedelta(hours=6)
    record_audit(db, actor=user, action="issue_alert", entity_type="alert", entity_id=alert.id,
                 from_state="recommended", to_state="issued",
                 detail={"level": alert.level, "location": alert.location_id}, request=request)
    if alert.incident_id:
        inc = db.get(Incident, alert.incident_id)
        if inc:
            if not inc.first_warning_at:
                inc.first_warning_at = now
            _append_story(db, inc, now,
                          f"{alert.level} warning issued by {user.full_name}.", "warning_issued")
    db.commit()
    deliver_alert(db, alert)
    db.refresh(alert)
    return alert


def deliver_alert(db: Session, alert: Alert, channels: Optional[List[str]] = None) -> List[AlertDelivery]:
    """Simulated multi-channel fan-out (Section 49)."""
    recipients = max(1, int(alert.estimated_exposed_population * 0.62))  # notional reachable share
    rows: List[AlertDelivery] = []
    for ch in get_channels(channels):
        res = ch.send(alert=alert, recipients=recipients, message=alert.message)
        row = AlertDelivery(
            id=new_id("dlv"),
            alert_id=alert.id,
            channel=res.channel,
            recipient_kind="citizen",
            recipient_count=res.recipient_count,
            status=res.status,
            is_simulated=res.is_simulated,
            provider=res.provider,
            detail=res.detail,
            opened_count=int(res.recipient_count * 0.48),
            sent_at=res.sent_at,
            delivered_at=res.delivered_at,
        )
        db.add(row)
        rows.append(row)
    if alert.status == "issued":
        record_transition(db, alert, to_status="delivered", actor="PEHRA notification service",
                          reason="Simulated delivery completed on all enabled channels.")
    db.commit()
    log_event(db, level="info", component="alerts", event="alert_delivered",
              message=f"Simulated delivery for {alert.id} on {len(rows)} channels", commit=True)
    return rows


def acknowledge_alert(db: Session, alert: Alert, user: Optional[User], *, note: str = "",
                      role: str = "citizen", request=None) -> AlertAcknowledgement:
    now = utcnow()
    existing = (
        db.query(AlertAcknowledgement)
        .filter(AlertAcknowledgement.alert_id == alert.id,
                AlertAcknowledgement.user_id == (user.id if user else None))
        .first()
    )
    if existing:
        return existing
    ack = AlertAcknowledgement(
        alert_id=alert.id,
        user_id=user.id if user else None,
        actor_role=user.role if user else role,
        note=sanitize_text(note),
        acknowledged_at=now,
    )
    db.add(ack)
    if alert.status in ("issued", "delivered", "updated", "escalated"):
        record_transition(db, alert, to_status="acknowledged",
                          actor=user.full_name if user else "citizen",
                          actor_role=user.role if user else role,
                          reason="Recipient acknowledged the alert.", at=now)
    record_audit(db, actor=user, action="acknowledge_alert", entity_type="alert",
                 entity_id=alert.id, to_state="acknowledged", request=request)
    db.commit()
    return ack


def cancel_alert(db: Session, alert: Alert, user: User, *, reason: str, request=None) -> Alert:
    now = utcnow()
    record_transition(db, alert, to_status="cancelled", actor=user.full_name,
                      actor_role=user.role, reason=sanitize_text(reason), at=now)
    alert.resolved_at = now
    record_audit(db, actor=user, action="cancel_alert", entity_type="alert", entity_id=alert.id,
                 to_state="cancelled", detail={"reason": reason}, request=request)
    _close_incident(db, alert, now, alert.risk_score)
    db.commit()
    return alert


def resolve_alert(db: Session, alert: Alert, user: Optional[User], *, reason: str) -> Alert:
    now = utcnow()
    record_transition(db, alert, to_status="resolved",
                      actor=user.full_name if user else "PEHRA alert engine",
                      actor_role=user.role if user else "system",
                      reason=sanitize_text(reason), at=now)
    alert.resolved_at = now
    _close_incident(db, alert, now, alert.risk_score)
    db.commit()
    return alert


# ---------------------------------------------------------------------------
# Incidents & risk story (Sections 69, 76)
# ---------------------------------------------------------------------------
INCIDENT_STAGES = [
    "Detection", "Prediction", "Verification", "Warning",
    "Escalation", "Peak", "Resolution", "Evaluation",
]


def _open_or_get_incident(db: Session, location: Location, hazard: str,
                          prediction: dict, now: dt.datetime) -> Incident:
    inc = (
        db.query(Incident)
        .filter(Incident.location_id == location.id, Incident.hazard == hazard,
                Incident.status == "open")
        .order_by(Incident.detected_at.desc())
        .first()
    )
    if inc:
        return inc
    hz = HAZARDS.get(hazard)
    inc = Incident(
        id=new_id("inc"),
        location_id=location.id,
        hazard=hazard,
        title=f"{hz.label if hz else hazard} event — {location.name}",
        status="open",
        peak_risk=prediction["risk"]["overall"],
        peak_at=now,
        detected_at=now,
        story=[],
        timeline=[{"stage": "Detection", "at": now.isoformat() + "Z",
                   "detail": "Risk engine first exceeded the alert threshold."}],
        scenario_id=prediction.get("scenario", {}).get("id"),
    )
    db.add(inc)
    db.flush()
    _append_story(db, inc, now,
                  f"Incident opened. Risk {prediction['risk']['overall']:.0f}/100 "
                  f"({prediction['risk']['severity']['label']}).", "detection")
    for sig in prediction.get("early_signals", [])[:4]:
        _append_story(db, inc, now, f"Early signal — {sig['label']}. {sig['detail']}", "early_signal")
    return inc


def _append_story(db: Session, incident: Incident, at: dt.datetime, text: str, kind: str) -> None:
    story = list(incident.story or [])
    story.append({"at": at.isoformat() + "Z", "text": text, "kind": kind})
    incident.story = story[-80:]


def _update_incident_peak(db: Session, alert: Alert, risk: float, now: dt.datetime) -> None:
    if not alert.incident_id:
        return
    inc = db.get(Incident, alert.incident_id)
    if not inc:
        return
    if risk > (inc.peak_risk or 0):
        inc.peak_risk = risk
        inc.peak_at = now
        tl = list(inc.timeline or [])
        if not any(t["stage"] == "Peak" for t in tl):
            tl.append({"stage": "Peak", "at": now.isoformat() + "Z",
                       "detail": f"New maximum risk {risk:.0f}/100."})
            inc.timeline = tl
        _append_story(db, inc, now, f"Risk reached a new maximum of {risk:.0f}/100.", "peak")


def _close_incident(db: Session, alert: Alert, now: dt.datetime, risk: float) -> None:
    if not alert.incident_id:
        return
    inc = db.get(Incident, alert.incident_id)
    if not inc or inc.status != "open":
        return
    others = (
        db.query(Alert)
        .filter(Alert.incident_id == inc.id, Alert.status.in_(ACTIVE_STATUSES),
                Alert.id != alert.id)
        .count()
    )
    if others:
        return
    inc.status = "resolved"
    inc.resolved_at = now
    if inc.first_warning_at and inc.peak_at and inc.peak_at > inc.first_warning_at:
        inc.lead_time_seconds = int((inc.peak_at - inc.first_warning_at).total_seconds())
    tl = list(inc.timeline or [])
    tl.append({"stage": "Resolution", "at": now.isoformat() + "Z",
               "detail": f"All alerts closed; risk back to {risk:.0f}/100."})
    inc.timeline = tl
    _append_story(db, inc, now, f"Incident resolved. Risk has returned to {risk:.0f}/100.", "resolution")


def alert_to_dict(db: Session, alert: Alert, *, include_timeline: bool = True) -> dict:
    loc = db.get(Location, alert.location_id)
    deliveries = db.query(AlertDelivery).filter(AlertDelivery.alert_id == alert.id).all()
    acks = db.query(AlertAcknowledgement).filter(AlertAcknowledgement.alert_id == alert.id).all()
    transitions = []
    if include_timeline:
        transitions = (
            db.query(AlertTransition)
            .filter(AlertTransition.alert_id == alert.id)
            .order_by(AlertTransition.at.asc())
            .all()
        )
    issued = sum(d.recipient_count for d in deliveries)
    delivered = sum(d.recipient_count for d in deliveries if d.status == "delivered")
    opened = sum(d.opened_count for d in deliveries)
    hz = HAZARDS.get(alert.hazard)
    return {
        "id": alert.id,
        "location": {"id": loc.id, "name": loc.name, "name_hi": loc.name_hi,
                     "district": loc.district, "latitude": loc.latitude,
                     "longitude": loc.longitude} if loc else None,
        "incident_id": alert.incident_id,
        "hazard": alert.hazard,
        "hazard_label": hz.label if hz else alert.hazard,
        "hazard_icon": hz.icon if hz else "alert-triangle",
        "level": alert.level,
        "status": alert.status,
        "title": alert.title,
        "message": alert.message,
        "message_hi": alert.message_hi,
        "recommended_actions": alert.recommended_actions,
        "recommendation_label": "AI-assisted recommendations — an authorised officer decides.",
        "what": alert.what,
        "where": alert.where,
        "when": alert.when,
        "why": alert.why,
        "what_to_do": alert.what_to_do,
        "risk_score": alert.risk_score,
        "confidence": alert.confidence,
        "prediction_id": alert.prediction_id,
        "threat_cell_id": alert.threat_cell_id,
        "geofence": {"kind": alert.geofence_kind, **(alert.geofence or {})},
        "estimated_exposed_population": alert.estimated_exposed_population,
        "exposure_note": "Estimate derived from demo population figures, not a census count.",
        "target_audience": alert.target_audience,
        "trigger_reason": alert.trigger_reason,
        "trigger_kinds": alert.trigger_kinds,
        "is_ai_generated": alert.is_ai_generated,
        "approved_by": alert.approved_by,
        "approved_at": _iso(alert.approved_at),
        "created_at": _iso(alert.created_at),
        "issued_at": _iso(alert.issued_at),
        "expires_at": _iso(alert.expires_at),
        "resolved_at": _iso(alert.resolved_at),
        "update_count": alert.update_count,
        "lead_time_seconds": alert.lead_time_seconds,
        "is_active": alert.status in ACTIVE_STATUSES,
        "funnel": {
            "issued": issued,
            "delivered": delivered,
            "opened": opened,
            "acknowledged": len(acks),
            "note": "Delivery counts are SIMULATED — no message was actually transmitted.",
        },
        "deliveries": [
            {
                "id": d.id, "channel": d.channel, "status": d.status,
                "recipient_count": d.recipient_count, "opened_count": d.opened_count,
                "is_simulated": d.is_simulated, "provider": d.provider,
                "detail": d.detail, "sent_at": _iso(d.sent_at),
                "delivered_at": _iso(d.delivered_at),
            }
            for d in deliveries
        ],
        "acknowledgements": [
            {"user_id": a.user_id, "role": a.actor_role, "note": a.note,
             "at": _iso(a.acknowledged_at)}
            for a in acks
        ],
        "timeline": [
            {
                "from_status": t.from_status, "to_status": t.to_status,
                "from_level": t.from_level, "to_level": t.to_level,
                "actor": t.actor, "actor_role": t.actor_role,
                "reason": t.reason, "at": _iso(t.at),
            }
            for t in transitions
        ],
    }


def _iso(value: Optional[dt.datetime]) -> Optional[str]:
    return value.isoformat() + "Z" if value else None


def incident_to_dict(db: Session, inc: Incident) -> dict:
    loc = db.get(Location, inc.location_id)
    alerts = db.query(Alert).filter(Alert.incident_id == inc.id).all()
    hz = HAZARDS.get(inc.hazard)
    stages = {t["stage"]: t for t in (inc.timeline or [])}
    return {
        "id": inc.id,
        "location": {"id": loc.id, "name": loc.name} if loc else None,
        "hazard": inc.hazard,
        "hazard_label": hz.label if hz else inc.hazard,
        "title": inc.title,
        "status": inc.status,
        "peak_risk": inc.peak_risk,
        "peak_at": _iso(inc.peak_at),
        "detected_at": _iso(inc.detected_at),
        "first_warning_at": _iso(inc.first_warning_at),
        "resolved_at": _iso(inc.resolved_at),
        "lead_time_seconds": inc.lead_time_seconds,
        "story": inc.story or [],
        "timeline": inc.timeline or [],
        "stages": [
            {
                "stage": s,
                "complete": s in stages,
                "at": stages.get(s, {}).get("at"),
                "detail": stages.get(s, {}).get("detail"),
            }
            for s in INCIDENT_STAGES
        ],
        "alerts": [{"id": a.id, "level": a.level, "status": a.status} for a in alerts],
        "scenario_id": inc.scenario_id,
    }
