"""Locations, observations, forecasts, risk, threats and map data."""
from __future__ import annotations

import datetime as dt
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.risk_config import HAZARDS
from app.db.models import EarlySignal, Infrastructure, Location, RiskPrediction, ThreatCell
from app.db.session import get_db
from app.engine.risk_field import build_sites, hazard_at_point, sample_grid
from app.engine.threat_cells import cell_to_dict
from app.services.clock import build_context, scenario_clock
from app.services.prediction import compute_prediction, _location_dict
from app.simulation.scenarios import haversine_km

router = APIRouter(tags=["risk"])


def _get_location(db: Session, location_id: str) -> Location:
    loc = db.get(Location, location_id)
    if not loc:
        raise HTTPException(
            status_code=404,
            detail={"error": "location_not_found",
                    "message": f"No monitored location with id '{location_id}'.",
                    "hint": "Call GET /api/locations for valid ids."},
        )
    return loc


@router.get(
    "/locations",
    summary="List monitored locations",
    description=(
        "All hyper-local zones PEHRA monitors, with their static vulnerability and exposure "
        "attributes. Every record is a labelled demo dataset (`data_origin: demo_seed`); "
        "place names and coordinates are real, populations and terrain indices are fictional."
    ),
)
def list_locations(
    q: Optional[str] = Query(default=None, description="Case-insensitive name/district search"),
    district: Optional[str] = None,
    db: Session = Depends(get_db),
) -> dict:
    query = db.query(Location)
    if district:
        query = query.filter(Location.district == district)
    rows = query.order_by(Location.name).all()
    if q:
        needle = q.strip().lower()
        rows = [
            r for r in rows
            if needle in r.name.lower()
            or needle in (r.name_hi or "")
            or needle in r.district.lower()
        ]
    return {
        "count": len(rows),
        "data_origin": "demo_seed",
        "locations": [_location_dict(r) for r in rows],
    }


@router.get(
    "/locations/nearest",
    summary="Nearest monitored location to a coordinate",
    description="Used by the citizen app when GPS returns a position that is not exactly a "
                "seeded ward. Validates the coordinate before searching (Section 98).",
)
def nearest_location(
    lat: float = Query(ge=-90, le=90),
    lng: float = Query(ge=-180, le=180),
    db: Session = Depends(get_db),
) -> dict:
    rows = db.query(Location).all()
    if not rows:
        raise HTTPException(status_code=404, detail={"error": "no_locations",
                                                     "message": "No locations are configured."})
    scored = sorted(((haversine_km(lat, lng, r.latitude, r.longitude), r) for r in rows),
                    key=lambda t: t[0])
    d, best = scored[0]
    return {
        "location": _location_dict(best),
        "distance_km": round(d, 2),
        "within_coverage": d <= 25.0,
        "note": "PEHRA's demo coverage is Pune district. Outside it, pick a location manually."
        if d > 25.0 else None,
    }

@router.get(
    "/locations/{location_id}",
    summary="Location detail with infrastructure",
    responses={404: {"description": "Unknown location"}},
)
def get_location(location_id: str, db: Session = Depends(get_db)) -> dict:
    loc = _get_location(db, location_id)
    infra = db.query(Infrastructure).filter(Infrastructure.location_id == loc.id).all()
    return {
        **_location_dict(loc),
        "infrastructure": [
            {
                "id": i.id, "name": i.name, "kind": i.kind, "latitude": i.latitude,
                "longitude": i.longitude, "capacity": i.capacity,
                "criticality": i.criticality, "data_origin": i.data_origin,
            }
            for i in infra
        ],
        "infrastructure_note": "Demo infrastructure dataset — positions are illustrative.",
    }



@router.get(
    "/observations/{location_id}",
    summary="Current observations with provenance",
    description=(
        "Every environmental input for a location with its source, timestamp, age, freshness "
        "verdict, sensor quality and whether it is observed or predicted (Section 3). "
        "Inputs that are unavailable are returned explicitly with a reason rather than omitted."
    ),
    responses={404: {"description": "Unknown location"}},
)
def get_observations(location_id: str, db: Session = Depends(get_db)) -> dict:
    from app.engine.features import assemble_features

    loc = _get_location(db, location_id)
    ctx = build_context(db)
    bundle = assemble_features(loc, ctx)
    return {
        "location_id": loc.id,
        "generated_at": ctx.now.isoformat() + "Z",
        "connectivity": ctx.connectivity,
        "observations": bundle.metadata_dict(),
        "data_health": bundle.data_health.to_dict(),
        "data_mode": {"is_simulated": True, "label": "DEMO / SIMULATED DATA"},
    }


@router.get(
    "/forecast/{location_id}",
    summary="Forecast feed for a location",
    description=(
        "Forward-looking values with the ensemble agreement the nowcaster reports at each "
        "horizon. All values are model output, never observations.\n\n"
        "These are deliberately **not** the scenario's ground truth: every projection passes "
        "through a nowcast skill-decay model (persistence drag + deterministic spread) so the "
        "forecast can be, and regularly is, wrong. See `nowcast_error_model` in /api/config."
    ),
    responses={404: {"description": "Unknown location"}},
)
def get_forecast(location_id: str, db: Session = Depends(get_db)) -> dict:
    from app.engine.features import assemble_features

    loc = _get_location(db, location_id)
    ctx = build_context(db)
    bundle = assemble_features(loc, ctx)
    return {
        "location_id": loc.id,
        "issued_at": ctx.now.isoformat() + "Z",
        "source": "PEHRA Demo Nowcaster",
        "is_simulated": True,
        "mean_agreement": bundle.forecast_agreement(),
        "forecasts": [f.to_dict() for f in bundle.forecasts],
    }


@router.get(
    "/risk/point",
    summary="Hazard estimate at an arbitrary coordinate",
    description=(
        "Evaluates the hazard model at any WGS84 point by interpolating static terrain and "
        "exposure properties from the nearest seeded wards. The response states that the "
        "static inputs are interpolated."
    ),
)
def risk_at_point(
    lat: float = Query(ge=-90, le=90),
    lng: float = Query(ge=-180, le=180),
    db: Session = Depends(get_db),
) -> dict:
    ctx = build_context(db)
    locations = db.query(Location).all()
    sites = build_sites(locations)
    point = hazard_at_point(ctx, lat, lng, sites)
    from app.engine.risk_engine import severity_label

    return {
        **point,
        "severity_band": severity_label(point["severity"]),
        "note": "Hazard-only estimate (exposure not applied). Static properties interpolated "
                "from the nearest monitored wards.",
    }

@router.get(
    "/risk/{location_id}",
    summary="Full risk assessment for a location",
    description=(
        "The complete OBSERVE → PREDICT → EXPLAIN result: hazard score, exposure score, overall "
        "risk, severity band, confidence breakdown, uncertainty range, momentum, ranked "
        "contributors, plain-language explanation, early signals, projected peak, decision "
        "window, warning lead time, prediction timeline and the citizen narrative.\n\n"
        "If the models cannot produce a prediction, `available` is false and `detail` explains "
        "why — a risk number is never invented (Section 63)."
    ),
    responses={404: {"description": "Unknown location"}},
)
def get_risk(
    location_id: str,
    detail: bool = Query(default=True, description="Include explanation, timeline and windows"),
    persist: bool = Query(default=False, description="Store the prediction and its input snapshot"),
    model: Optional[str] = Query(default=None, pattern="^(demo|statistical|ml)$"),
    lang: str = Query(default="en", pattern="^(en|hi)$"),
    db: Session = Depends(get_db),
) -> dict:
    loc = _get_location(db, location_id)
    return compute_prediction(db, loc, detail=detail, persist=persist,
                              preferred_model=model, lang=lang)


@router.get(
    "/risk/{location_id}/timeline",
    summary="Prediction timeline (NOW → +6h)",
    description="Risk, severity, confidence, uncertainty band, main hazard and expected intensity "
                "at each configured horizon (Section 10).",
    responses={404: {"description": "Unknown location"}},
)
def get_timeline(location_id: str, db: Session = Depends(get_db)) -> dict:
    loc = _get_location(db, location_id)
    pred = compute_prediction(db, loc, detail=True, persist=False)
    if not pred.get("available"):
        return {"available": False, "reason": pred.get("detail")}
    return {
        "available": True,
        "location_id": loc.id,
        "generated_at": pred["generated_at"],
        "timeline": pred["timeline"],
        "peak": pred["peak"],
        "decision_window": pred["decision_window"],
        "comparison": pred["comparison"],
        "trajectory": pred.get("trajectory", []),
    }


@router.get(
    "/risk/{location_id}/history",
    summary="Stored prediction history",
    description="Previously persisted predictions for this location, newest first. This is the "
                "audit trail that makes verification possible (Sections 39, 40).",
)
def get_history(
    location_id: str,
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
) -> dict:
    _get_location(db, location_id)
    rows = (
        db.query(RiskPrediction)
        .filter(RiskPrediction.location_id == location_id)
        .order_by(RiskPrediction.created_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "count": len(rows),
        "predictions": [
            {
                "id": r.id, "hazard": r.hazard, "overall_risk": r.overall_risk,
                "hazard_score": r.hazard_score, "exposure_score": r.exposure_score,
                "severity": r.severity, "confidence": r.confidence,
                "uncertainty": r.uncertainty, "range": [r.range_low, r.range_high],
                "momentum_band": r.momentum_band, "momentum_rate": r.momentum_rate,
                "model": {"name": r.model_name, "version": r.model_version,
                          "is_fallback": r.is_fallback},
                "created_at": r.created_at.isoformat() + "Z",
                "scenario_tick": r.scenario_tick,
            }
            for r in rows
        ],
    }



@router.get(
    "/map/field",
    summary="Gridded hazard field for the map heat-map",
    description=(
        "Samples the hazard model on a regular grid over the monitored region. This is the same "
        "field the threat-cell tracker clusters, so the heat-map and the cells can never "
        "disagree (Sections 15, 17)."
    ),
)
def map_field(
    step_deg: float = Query(default=0.035, ge=0.01, le=0.2),
    min_severity: float = Query(default=12.0, ge=0, le=100),
    db: Session = Depends(get_db),
) -> dict:
    ctx = build_context(db)
    locations = db.query(Location).all()
    return sample_grid(ctx, locations, step_deg=step_deg, min_severity=min_severity)


@router.get(
    "/map/layers",
    summary="All map layer data in one call",
    description=(
        "Bundles zones, infrastructure, rivers, threat cells and active alerts so the map can "
        "render every toggleable layer without a request per layer (Section 16)."
    ),
)
def map_layers(db: Session = Depends(get_db)) -> dict:
    from app.db.models import Alert

    locations = db.query(Location).all()
    infra = db.query(Infrastructure).all()
    cells = db.query(ThreatCell).filter(ThreatCell.status.in_(["active", "dissipating"])).all()
    alerts = (
        db.query(Alert)
        .filter(Alert.status.in_(["recommended", "issued", "delivered", "acknowledged",
                                  "updated", "escalated"]))
        .all()
    )
    rivers: dict = {}
    for l in locations:
        if l.river_id:
            rivers.setdefault(l.river_id, []).append(
                {"location_id": l.id, "lat": l.latitude, "lng": l.longitude, "name": l.name}
            )
    return {
        "zones": [
            {
                "id": l.id, "name": l.name, "name_hi": l.name_hi, "polygon": l.polygon,
                "latitude": l.latitude, "longitude": l.longitude, "population": l.population,
                "terrain_vulnerability": l.terrain_vulnerability,
                "drainage_deficiency": l.drainage_deficiency,
                "elevation_m": l.elevation_m, "primary_hazards": l.primary_hazards,
                "admin_type": l.admin_type, "district": l.district,
            }
            for l in locations
        ],
        "infrastructure": [
            {"id": i.id, "name": i.name, "kind": i.kind, "lat": i.latitude, "lng": i.longitude,
             "criticality": i.criticality, "capacity": i.capacity, "location_id": i.location_id}
            for i in infra
        ],
        "rivers": [{"id": k, "points": v} for k, v in rivers.items()],
        "threat_cells": [cell_to_dict(c) for c in cells],
        "alerts": [
            {"id": a.id, "level": a.level, "status": a.status, "hazard": a.hazard,
             "location_id": a.location_id, "geofence": {"kind": a.geofence_kind, **(a.geofence or {})},
             "title": a.title, "risk_score": a.risk_score}
            for a in alerts
        ],
        "data_origin": "demo_seed",
    }


@router.get(
    "/threats",
    summary="Active threat cells",
    description="Tracked concentrations of risk with measured movement vectors and position "
                "history (Sections 17, 18).",
)
def list_threats(
    status: str = Query(default="active", pattern="^(active|dissipating|resolved|all)$"),
    db: Session = Depends(get_db),
) -> dict:
    q = db.query(ThreatCell)
    if status != "all":
        q = q.filter(ThreatCell.status == status)
    cells = q.order_by(ThreatCell.current_severity.desc()).all()
    return {"count": len(cells), "threat_cells": [cell_to_dict(c) for c in cells]}


@router.get(
    "/threats/{cell_id}",
    summary="Threat cell detail",
    responses={404: {"description": "Unknown threat cell"}},
)
def get_threat(cell_id: str, db: Session = Depends(get_db)) -> dict:
    cell = db.get(ThreatCell, cell_id)
    if not cell:
        raise HTTPException(status_code=404, detail={"error": "not_found",
                                                     "message": f"No threat cell '{cell_id}'."})
    locs = db.query(Location).filter(Location.id.in_(cell.location_ids or [])).all()
    return {
        **cell_to_dict(cell),
        "affected_locations": [
            {"id": l.id, "name": l.name, "population": l.population} for l in locs
        ],
        "estimated_population_in_cell": sum(l.population for l in locs),
    }


@router.get(
    "/early-signals",
    summary="Detected early-warning precursors",
    description="Subtle patterns the engine flagged before severity developed (Section 70).",
)
def early_signals(
    location_id: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict:
    q = db.query(EarlySignal).order_by(EarlySignal.detected_at.desc())
    if location_id:
        q = q.filter(EarlySignal.location_id == location_id)
    rows = q.limit(limit).all()
    return {
        "count": len(rows),
        "signals": [
            {
                "id": r.id, "location_id": r.location_id, "kind": r.kind, "label": r.label,
                "detail": r.detail, "magnitude": r.magnitude,
                "risk_at_detection": r.risk_at_detection,
                "detected_at": r.detected_at.isoformat() + "Z", "tick": r.scenario_tick,
            }
            for r in rows
        ],
    }


@router.get(
    "/data-health",
    summary="Regional data health",
    description="Per-source quality, freshness and availability across the whole region "
                "(Section 14). Authorities use it to judge whether predictions can be trusted.",
)
def data_health(db: Session = Depends(get_db)) -> dict:
    from app.engine.features import assemble_features

    ctx = build_context(db)
    locations = db.query(Location).all()
    per_source: dict = {}
    scores: List[float] = []
    all_stale: set = set()
    all_missing: set = set()
    failures: List[dict] = []
    for loc in locations[:6]:  # representative sample keeps this endpoint fast
        bundle = assemble_features(loc, ctx)
        scores.append(bundle.data_health.score)
        all_stale.update(bundle.data_health.stale_features)
        all_missing.update(bundle.data_health.missing_features)
        for f in bundle.data_health.failed_providers:
            if f not in failures:
                failures.append(f)
        for s in bundle.data_health.by_source:
            e = per_source.setdefault(s["key"], {**s, "_n": 0, "_sum": 0.0})
            e["_n"] += 1
            e["_sum"] += s["score"]
    for e in per_source.values():
        e["score"] = round(e["_sum"] / max(e["_n"], 1), 1)
        from app.engine.features import _grade

        e["grade"] = _grade(e["score"])
        e.pop("_n"), e.pop("_sum")
    overall = round(sum(scores) / len(scores), 1) if scores else 0.0
    from app.engine.features import _grade

    return {
        "score": overall,
        "grade": _grade(overall),
        "by_source": list(per_source.values()),
        "stale_features": sorted(all_stale),
        "missing_features": sorted(all_missing),
        "failed_providers": failures,
        "sampled_locations": min(len(locations), 6),
        "clock": scenario_clock(db),
    }


@router.get("/hazards", summary="Extensible hazard definitions")
def list_hazards() -> dict:
    return {
        "count": len(HAZARDS),
        "hazards": [
            {
                "key": k, "label": v.label, "icon": v.icon, "unit_hint": v.unit_hint,
                "required_features": v.required_features,
                "citizen_language": v.citizen_language,
                "weights": {
                    "hazard": v.hazard_weights, "vulnerability": v.vulnerability_weights,
                    "trend": v.trend_weights, "forecast": v.forecast_weights,
                },
            }
            for k, v in HAZARDS.items()
        ],
    }
