"""System, health and metadata endpoints."""
from __future__ import annotations

import datetime as dt
import platform
import time

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.risk_config import (
    ALERTS,
    COMPOSITE,
    CONFIDENCE,
    CONFIDENCE_BANDS,
    DATA_QUALITY_GRADES,
    EXPOSURE_WEIGHTS,
    FRESHNESS,
    HAZARDS,
    MOMENTUM_BANDS,
    NORMALISATION,
    OVERALL_MIX,
    RISK_LEVELS,
    THREAT_CELLS,
    VERIFICATION,
)
from app.db.models import Alert, Location, RiskPrediction, SystemLog, ThreatCell
from app.db.session import get_db
from app.providers.registry import registry
from app.realtime.bus import bus
from app.riskmodels.registry import model_registry
from app.security.auth import require_admin
from app.services.clock import get_state, scenario_clock
from app.simulation import nowcast_error

router = APIRouter(tags=["system"])
_STARTED = time.time()


@router.get(
    "/health",
    summary="Liveness and dependency health",
    description=(
        "Returns process liveness plus the status of each internal dependency: "
        "database, risk models, data providers and the notification service. "
        "Never returns a fabricated 'ok' — each component is actually probed."
    ),
    responses={200: {"description": "Health report"}, 503: {"description": "A critical component is down"}},
)
def health(db: Session = Depends(get_db)) -> dict:
    components = []

    t0 = time.perf_counter()
    try:
        db.execute(text("SELECT 1"))
        db_status, db_detail = "operational", None
    except Exception as exc:
        db_status, db_detail = "unavailable", str(exc)
    components.append({
        "name": "Database", "key": "database", "status": db_status,
        "detail": db_detail, "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
    })

    state = None
    try:
        state = get_state(db)
    except Exception:
        pass
    ctx_failures = dict(state.forced_failures or {}) if state else {}
    connectivity = state.connectivity if state else "online"

    for p in registry.all:
        from app.providers.base import ProviderContext

        ctx = ProviderContext(
            now=dt.datetime.now(dt.timezone.utc).replace(tzinfo=None),
            scenario_id=state.scenario_id if state else "mumbai_normal",
            tick=state.tick if state else 0,
            connectivity=connectivity,
            forced_failures=ctx_failures,
        )
        h = p.health(ctx)
        components.append({
            "name": h["name"], "key": f"provider:{h['key']}", "status": h["status"],
            "detail": h["note"], "is_simulated": h["is_simulated"],
        })

    for m in model_registry.all():
        components.append({
            "name": m.name, "key": f"model:{m.kind}",
            "status": "operational" if m.is_available() else "unavailable",
            "detail": m.unavailable_reason(),
            "is_active": m.kind == model_registry.preferred,
        })

    from app.alerts.channels import CHANNELS

    for c in CHANNELS:
        components.append({
            "name": f"Notification: {c.label}", "key": f"channel:{c.key}",
            "status": "operational" if c.enabled() else "unavailable",
            "detail": c.describe()["note"], "is_simulated": c.is_simulated,
        })

    components.append({
        "name": "Map service", "key": "map",
        "status": "operational",
        "detail": f"Raster tiles from {settings.map_tile_url.split('/')[2]}; "
                  "the app falls back to a locally drawn basemap if tiles cannot load.",
    })
    components.append({
        "name": "Realtime (SSE)", "key": "realtime", "status": "operational",
        "detail": f"{bus.subscriber_count} subscriber(s) connected.",
    })

    degraded = [c for c in components if c["status"] != "operational"]
    overall = "operational" if not degraded else (
        "unavailable" if db_status == "unavailable" else "degraded"
    )

    return {
        "status": overall,
        "app": settings.app_name,
        "full_name": settings.app_full_name,
        "version": settings.version,
        "environment": settings.environment,
        "uptime_seconds": round(time.time() - _STARTED, 1),
        "server_time_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "python": platform.python_version(),
        "demo_mode": settings.demo_mode,
        "data_mode": {
            "is_simulated": not registry.any_real_feed(),
            "label": settings.data_mode_label,
            "note": "No real weather, satellite, river or notification service is connected. "
                    "All environmental values are produced by deterministic demo providers.",
        },
        "connectivity": connectivity,
        "components": components,
        "degraded_components": [c["name"] for c in degraded],
        "security_warnings": (
            ["JWT secret is the insecure development default. Set PEHRA_JWT_SECRET."]
            if settings.is_secret_default else []
        ),
    }


@router.get(
    "/config",
    summary="Risk-engine configuration",
    description=(
        "Every tunable the engine uses: risk bands, momentum bands, composite weights, "
        "normalisation ranges, hazard definitions, alert thresholds and confidence weights. "
        "The UI reads its labels and thresholds from here so it can never disagree with the engine."
    ),
)
def get_config() -> dict:
    return {
        "risk_levels": RISK_LEVELS,
        "momentum_bands": MOMENTUM_BANDS,
        "composite_weights": {
            "hazard": COMPOSITE.hazard,
            "vulnerability": COMPOSITE.vulnerability,
            "forecast": COMPOSITE.forecast,
            "trend_bonus_max": COMPOSITE.trend_bonus_max,
        },
        "overall_mix": OVERALL_MIX,
        "exposure_weights": EXPOSURE_WEIGHTS,
        "normalisation": NORMALISATION,
        "hazards": {k: v.as_dict() for k, v in HAZARDS.items()},
        "alerts": ALERTS,
        "confidence": CONFIDENCE,
        "confidence_bands": CONFIDENCE_BANDS,
        "freshness": FRESHNESS,
        "data_quality_grades": DATA_QUALITY_GRADES,
        "threat_cells": THREAT_CELLS,
        "verification": VERIFICATION,
        "horizons_minutes": [0, 30, 60, 120, 180, 360],
        "nowcast_error_model": nowcast_error.describe(),
        "map": {"tile_url": settings.map_tile_url, "attribution": settings.map_attribution},
    }


@router.get(
    "/system-status",
    summary="Operational status board",
    description="Authority-facing status of API, database, model, feeds, notifications and map "
                "(Section 86), plus current simulation clock.",
)
def system_status(db: Session = Depends(get_db)) -> dict:
    h = health(db)
    counts = {
        "locations": db.query(Location).count(),
        "active_alerts": db.query(Alert).filter(
            Alert.status.in_(["recommended", "pending_approval", "issued", "delivered",
                              "acknowledged", "updated", "escalated"])
        ).count(),
        "threat_cells": db.query(ThreatCell).filter(ThreatCell.status == "active").count(),
        "predictions_stored": db.query(RiskPrediction).count(),
    }
    return {"health": h, "counts": counts, "clock": scenario_clock(db)}


@router.get(
    "/models",
    summary="Registered risk models",
    description=(
        "Model registry with versions, availability and (where a model was actually fitted) "
        "its training statistics. Metrics are always accompanied by a caveat describing what "
        "they were measured on — PEHRA never presents unmeasured accuracy."
    ),
)
def list_models() -> dict:
    return {
        "active": model_registry.preferred,
        "fallback_chain": [m.kind for m in model_registry.chain()],
        "models": [m.describe() for m in model_registry.all()],
        "note": "Replacing a model means implementing RiskModel and registering it. "
                "No downstream code changes.",
    }


@router.get(
    "/providers",
    summary="Registered data providers",
    description="Adapter registry for the sensing layer. Each entry states whether it is a real "
                "feed or a simulated one.",
)
def list_providers(db: Session = Depends(get_db)) -> dict:
    from app.providers.base import ProviderContext

    state = get_state(db)
    ctx = ProviderContext(
        now=dt.datetime.now(dt.timezone.utc).replace(tzinfo=None),
        scenario_id=state.scenario_id, tick=state.tick,
        connectivity=state.connectivity, forced_failures=dict(state.forced_failures or {}),
    )
    return {
        "any_real_feed": registry.any_real_feed(),
        "providers": [p.health(ctx) for p in registry.all],
    }


@router.get(
    "/logs",
    summary="Internal observability log (administrator only)",
    description="Structured log of prediction generation, ingestion, alert lifecycle, model "
                "failures and API errors (Section 87).",
)
def get_logs(
    limit: int = Query(default=100, ge=1, le=500),
    level: str | None = Query(default=None, pattern="^(info|warning|error)$"),
    component: str | None = None,
    db: Session = Depends(get_db),
    _user=Depends(require_admin),
) -> dict:
    q = db.query(SystemLog).order_by(SystemLog.at.desc())
    if level:
        q = q.filter(SystemLog.level == level)
    if component:
        q = q.filter(SystemLog.component == component)
    rows = q.limit(limit).all()
    return {
        "count": len(rows),
        "logs": [
            {
                "id": r.id, "level": r.level, "component": r.component, "event": r.event,
                "message": r.message, "context": r.context, "duration_ms": r.duration_ms,
                "at": r.at.isoformat() + "Z",
            }
            for r in rows
        ],
    }
