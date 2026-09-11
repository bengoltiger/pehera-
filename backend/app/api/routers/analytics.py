"""Analytics, model performance, audit log and command-centre aggregates."""
from __future__ import annotations

import datetime as dt
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models import (
    Alert,
    AlertAcknowledgement,
    AlertDelivery,
    AlertTransition,
    AuditLog,
    EarlySignal,
    Incident,
    Location,
    PredictionVerification,
    RiskPrediction,
    ThreatCell,
    User,
)
from app.db.session import get_db
from app.riskmodels.registry import model_registry
from app.security.auth import require_authority, require_admin
from app.services.alerts import ACTIVE_STATUSES
from app.services.clock import scenario_clock
from app.services.orchestrator import last_sweep, refresh_region
from app.simulation import nowcast_error

router = APIRouter(tags=["analytics"])


@router.get(
    "/overview",
    summary="Command-centre headline metrics",
    description=(
        "Active threats, critical zones, people potentially exposed, alerts issued, average "
        "warning lead time and data health (Section 25). Values are computed from stored state; "
        "any metric that has no measured basis is returned as null with a reason."
    ),
)
def overview(db: Session = Depends(get_db)) -> dict:
    sweep = last_sweep()
    if not sweep:
        sweep = refresh_region(db, persist_predictions=False)
    summary = sweep["summary"]
    queue = summary["priority_queue"]

    critical = [q for q in queue if q["severity"]["key"] == "CRITICAL"]
    high = [q for q in queue if q["severity"]["key"] == "HIGH"]
    exposed = sum(q["exposed_population"] for q in queue if q["risk"] >= 61)

    active_alerts = db.query(Alert).filter(Alert.status.in_(ACTIVE_STATUSES)).all()
    issued = [a for a in active_alerts if a.status in ("issued", "delivered", "acknowledged",
                                                       "updated", "escalated")]
    recommended = [a for a in active_alerts if a.status == "recommended"]

    leads = [a.lead_time_seconds for a in db.query(Alert).all() if a.lead_time_seconds]
    avg_lead = sum(leads) / len(leads) if leads else None

    from app.api.routers.risk import data_health as _dh

    health = _dh(db)

    return {
        "generated_at": summary["generated_at"],
        "clock": scenario_clock(db),
        "metrics": {
            "active_threats": len([c for c in summary["threat_cells"] if c["status"] == "active"]),
            "critical_zones": len(critical),
            "high_zones": len(high),
            "people_potentially_exposed": exposed,
            "alerts_issued": len(issued),
            "alerts_awaiting_approval": len(recommended),
            "average_lead_time_seconds": round(avg_lead) if avg_lead else None,
            "average_lead_time_note": None if avg_lead else
                "No lead time measured yet — it is recorded when an alert is raised before a peak.",
            "data_health": health["score"],
            "data_health_grade": health["grade"],
            "monitored_locations": summary["locations"],
        },
        "priority_queue": queue,
        "threat_cells": summary["threat_cells"],
        "risk_field_points": summary.get("risk_field", {}).get("count", 0),
        "changes": summary.get("changes", []),
        "data_mode": {"is_simulated": True, "label": "DEMO / SIMULATED DATA"},
    }


@router.get(
    "/analytics",
    summary="System, alert and geographic analytics",
    description=(
        "Aggregate analytics across predictions, alerts and areas (Section 68). Model "
        "performance is reported separately by /api/analytics/model so that unmeasured "
        "metrics are never mixed with measured ones."
    ),
)
def analytics(db: Session = Depends(get_db)) -> dict:
    total_predictions = db.query(RiskPrediction).count()
    alerts = db.query(Alert).all()
    by_status: dict = {}
    by_level: dict = {}
    for a in alerts:
        by_status[a.status] = by_status.get(a.status, 0) + 1
        by_level[a.level] = by_level.get(a.level, 0) + 1

    acks = db.query(AlertAcknowledgement).count()
    escalations = db.query(AlertTransition).filter(AlertTransition.to_status == "escalated").count()
    resolved = db.query(Alert).filter(Alert.status == "resolved").count()
    deliveries = db.query(AlertDelivery).all()

    leads = [a.lead_time_seconds for a in alerts if a.lead_time_seconds]
    incidents = db.query(Incident).all()
    inc_leads = [i.lead_time_seconds for i in incidents if i.lead_time_seconds]

    # geographic performance
    geo = []
    for loc in db.query(Location).all():
        preds = db.query(RiskPrediction).filter(RiskPrediction.location_id == loc.id).all()
        if not preds:
            continue
        risks = [p.overall_risk for p in preds]
        alert_count = db.query(Alert).filter(Alert.location_id == loc.id).count()
        vers = db.query(PredictionVerification).filter(
            PredictionVerification.location_id == loc.id
        ).all()
        correct = sum(1 for v in vers if v.outcome == "CORRECT")
        geo.append({
            "location_id": loc.id,
            "location_name": loc.name,
            "predictions": len(preds),
            "mean_risk": round(sum(risks) / len(risks), 1),
            "max_risk": round(max(risks), 1),
            "alerts": alert_count,
            "verified_samples": len(vers),
            "accuracy_within_tolerance": round(100.0 * correct / len(vers), 1) if vers else None,
            "accuracy_note": None if vers else "Not enough evaluation data for this area.",
        })
    geo.sort(key=lambda g: g["max_risk"], reverse=True)

    signals = db.query(EarlySignal).all()
    signal_kinds: dict = {}
    for s in signals:
        signal_kinds[s.kind] = signal_kinds.get(s.kind, 0) + 1

    return {
        "system_overview": {
            "total_predictions": total_predictions,
            "prediction_snapshots": db.query(RiskPrediction).count(),
            "active_alerts": len([a for a in alerts if a.status in ACTIVE_STATUSES]),
            "total_alerts": len(alerts),
            "threat_cells_tracked": db.query(ThreatCell).count(),
            "early_signals_detected": len(signals),
            "early_signal_kinds": signal_kinds,
            "average_warning_lead_time_seconds": round(sum(leads) / len(leads)) if leads else None,
            "average_incident_lead_time_seconds": round(sum(inc_leads) / len(inc_leads)) if inc_leads else None,
            "prediction_coverage": {
                "locations_with_predictions": len({p.location_id for p in db.query(RiskPrediction).all()}),
                "total_locations": db.query(Location).count(),
            },
        },
        "alert_performance": {
            "by_status": by_status,
            "by_level": by_level,
            "issued": by_status.get("issued", 0) + by_status.get("delivered", 0)
                      + by_status.get("acknowledged", 0) + by_status.get("updated", 0)
                      + by_status.get("escalated", 0),
            "acknowledged": acks,
            "escalated": escalations,
            "resolved": resolved,
            "delivery_funnel": {
                "channels": len({d.channel for d in deliveries}),
                "total_simulated_recipients": sum(d.recipient_count for d in deliveries),
                "total_simulated_opens": sum(d.opened_count for d in deliveries),
                "acknowledgements": acks,
                "note": "All delivery figures are SIMULATED.",
            },
        },
        "geographic_performance": geo,
        "incidents": {
            "open": len([i for i in incidents if i.status == "open"]),
            "resolved": len([i for i in incidents if i.status == "resolved"]),
            "archived": len([i for i in incidents if i.status == "archived"]),
        },
    }


@router.get(
    "/analytics/model",
    summary="Model performance dashboard",
    description=(
        "Precision, recall, F1, false-positive and false-negative rates, error by horizon and "
        "calibration — computed ONLY from verification records that were actually produced by "
        "running the verification service. If none exist the response says "
        "'Not enough evaluation data' rather than inventing numbers (Section 42)."
    ),
)
def model_performance(db: Session = Depends(get_db)) -> dict:
    rows: List[PredictionVerification] = db.query(PredictionVerification).all()
    models = [m.describe() for m in model_registry.all()]

    if len(rows) < 10:
        return {
            "available": False,
            "reason": "Not enough evaluation data",
            "detail": (
                f"Only {len(rows)} verified prediction(s) are stored. Run a verification "
                "(POST /api/verify, or 'Run evaluation' in the Analytics screen) to measure "
                "performance against a replayed scenario."
            ),
            "sample_size": len(rows),
            "models": models,
            "active_model": model_registry.preferred,
        }

    tp = sum(1 for r in rows if r.predicted_risk >= 61 and r.actual_event_occurred)
    fp = sum(1 for r in rows if r.predicted_risk >= 61 and not r.actual_event_occurred)
    fn = sum(1 for r in rows if r.predicted_risk < 61 and r.actual_event_occurred)
    tn = sum(1 for r in rows if r.predicted_risk < 61 and not r.actual_event_occurred)

    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    f1 = (2 * precision * recall / (precision + recall)) if (precision and recall) else None
    errors = [r.error for r in rows if r.error is not None]

    by_horizon: dict = {}
    for r in rows:
        e = by_horizon.setdefault(r.horizon_minutes, {"n": 0, "abs": 0.0, "sum": 0.0})
        e["n"] += 1
        e["abs"] += abs(r.error or 0)
        e["sum"] += r.error or 0

    outcomes: dict = {}
    for r in rows:
        outcomes[r.outcome] = outcomes.get(r.outcome, 0) + 1

    # calibration: predicted-risk decile vs observed event rate
    buckets = []
    for lo in range(0, 100, 20):
        hi = lo + 20
        sub = [r for r in rows if lo <= r.predicted_risk < hi]
        if sub:
            buckets.append({
                "bucket": f"{lo}-{hi}",
                "count": len(sub),
                "mean_predicted": round(sum(r.predicted_risk for r in sub) / len(sub), 1),
                "mean_actual": round(sum(r.actual_risk or 0 for r in sub) / len(sub), 1),
                "event_rate": round(100.0 * sum(1 for r in sub if r.actual_event_occurred) / len(sub), 1),
            })

    lead_times = [r.lead_time_seconds for r in rows if r.lead_time_seconds]

    return {
        "available": True,
        "sample_size": len(rows),
        "active_model": model_registry.preferred,
        "models": models,
        "confusion": {"true_positive": tp, "false_positive": fp,
                      "false_negative": fn, "true_negative": tn},
        "metrics": {
            "precision": round(precision, 3) if precision is not None else None,
            "recall": round(recall, 3) if recall is not None else None,
            "f1": round(f1, 3) if f1 is not None else None,
            "false_positive_rate": round(fp / (fp + tn), 3) if (fp + tn) else None,
            "false_negative_rate": round(fn / (fn + tp), 3) if (fn + tp) else None,
            "mae": round(sum(abs(e) for e in errors) / len(errors), 2) if errors else None,
            "bias": round(sum(errors) / len(errors), 2) if errors else None,
            "mean_lead_time_seconds": round(sum(lead_times) / len(lead_times)) if lead_times else None,
        },
        "outcomes": outcomes,
        "by_horizon": [
            {"horizon_minutes": h, "count": v["n"], "mae": round(v["abs"] / v["n"], 2),
             "bias": round(v["sum"] / v["n"], 2)}
            for h, v in sorted(by_horizon.items())
        ],
        "calibration": buckets,
        "sources": sorted({r.source for r in rows}),
        "error_model": nowcast_error.describe(),
        "caveat": (
            "Measured by replaying DETERMINISTIC SIMULATED scenarios and comparing each forecast "
            "against the risk the engine later computed from the observations that actually "
            "arrived. This measures forecast consistency on simulated ground truth. It is NOT "
            "real-world disaster-prediction accuracy and must not be quoted as such."
        ),
    }


@router.get(
    "/analytics/compare",
    summary="Compare areas side by side",
    description="Sortable comparison of risk, trend, exposure and confidence across locations "
                "(Section 75).",
)
def compare_areas(
    sort_by: str = Query(default="risk", pattern="^(risk|exposure|confidence|momentum|priority|name)$"),
    db: Session = Depends(get_db),
) -> dict:
    sweep = last_sweep()
    if not sweep:
        sweep = refresh_region(db, persist_predictions=False)
    rows = []
    for loc_id, pred in sweep["predictions"].items():
        if not pred.get("available"):
            rows.append({"location_id": loc_id, "available": False,
                         "reason": pred.get("detail")})
            continue
        rows.append({
            "available": True,
            "location_id": loc_id,
            "name": pred["location"]["name"],
            "district": pred["location"]["district"],
            "risk": pred["risk"]["overall"],
            "hazard_score": pred["risk"]["hazard_score"],
            "exposure_score": pred["risk"]["exposure_score"],
            "severity": pred["risk"]["severity"]["key"],
            "severity_label": pred["risk"]["severity"]["label"],
            "momentum": pred["risk"]["momentum"]["label"],
            "momentum_arrow": pred["risk"]["momentum"]["arrow"],
            "momentum_rate": pred["risk"]["momentum"]["rate_per_hour"],
            "confidence": pred["risk"]["confidence"]["value"],
            "population": pred["location"]["population"],
            "hazard": pred["hazard"]["label"],
            "peak": (pred.get("peak") or {}).get("risk"),
        })
    keymap = {
        "risk": lambda r: r.get("risk", -1),
        "exposure": lambda r: r.get("exposure_score", -1),
        "confidence": lambda r: r.get("confidence", -1),
        "momentum": lambda r: r.get("momentum_rate", -999),
        "priority": lambda r: r.get("risk", -1),
        "name": lambda r: r.get("name", ""),
    }
    reverse = sort_by != "name"
    rows.sort(key=keymap[sort_by], reverse=reverse)
    return {"count": len(rows), "sort_by": sort_by, "areas": rows}


@router.get(
    "/audit",
    summary="Administrative audit log",
    description="Who did what, when, to which entity, and between which states (Section 51). "
                "Authority and administrator roles may read it.",
)
def audit_log(
    limit: int = Query(default=100, ge=1, le=500),
    action: Optional[str] = None,
    entity_type: Optional[str] = None,
    db: Session = Depends(get_db),
    _user: User = Depends(require_authority),
) -> dict:
    q = db.query(AuditLog).order_by(AuditLog.at.desc())
    if action:
        q = q.filter(AuditLog.action == action)
    if entity_type:
        q = q.filter(AuditLog.entity_type == entity_type)
    rows = q.limit(limit).all()
    return {
        "count": len(rows),
        "entries": [
            {
                "id": r.id, "actor_id": r.actor_id, "actor_name": r.actor_name,
                "actor_role": r.actor_role, "action": r.action, "entity_type": r.entity_type,
                "entity_id": r.entity_id, "from_state": r.from_state, "to_state": r.to_state,
                "detail": r.detail, "ip_address": r.ip_address, "at": r.at.isoformat() + "Z",
                "summary": (
                    f"{r.actor_name} ({r.actor_role}) performed {r.action.replace('_', ' ')}"
                    + (f" on {r.entity_type} {r.entity_id}" if r.entity_id else "")
                    + (f", {r.from_state} → {r.to_state}" if r.to_state else "")
                ),
            }
            for r in rows
        ],
    }
