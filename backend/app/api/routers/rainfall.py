"""Rainfall layer endpoints (Sections MB-5, MB-6).

Mumbai floods from rain falling faster than drains can carry it. The rainfall
router reports accumulation buckets (1/3/6/12/24 h) that are *derived from the
scenario forcing curve* — the same curve the risk engine consumes — and clearly
labelled as simulated estimates.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.models import Location
from app.db.session import get_db
from app.services.clock import build_context, scenario_clock
from app.simulation.scenarios import get_scenario, scenario_field_at

router = APIRouter(tags=["rainfall"])


def _loc(db: Session, location_id: str) -> Location:
    loc = db.get(Location, location_id)
    if not loc:
        raise HTTPException(status_code=404,
                            detail={"error": "location_not_found",
                                    "message": f"No monitored location with id '{location_id}'."})
    return loc


def _buckets(scenario, lat: float, lng: float, tick: int, horizon_hours: int) -> list:
    """Accumulated rainfall over hourly buckets out to `horizon_hours`, sampled
    from the scenario forcing at the given point."""
    out = []
    for hour in range(1, horizon_hours + 1):
        acc = 0.0
        for k in range(0, 4 * hour):
            kt = tick + k + 1
            f = scenario_field_at(scenario, kt, lat, lng)
            acc += (f.get("rain_intensity") or 0.0) * scenario.tick_minutes / 60.0
        out.append({"hours": hour, "accumulated_mm": round(acc, 1)})
    return out


@router.get(
    "/rainfall",
    summary="Current rainfall state and accumulation buckets",
    description=(
        "Per-monitored-ward rainfall: current intensity, the scenario's reported 3-hour "
        "accumulation, and simulated accumulation estimates out to 24 h from the forcing "
        "curve. All values are simulated — never real telemetry."),
    responses={404: {"description": "Unknown location"}},
)
def rainfall(
    location_id: str = Query(default="loc_kurla", description="Monitored ward"),
    db: Session = Depends(get_db),
) -> dict:
    loc = _loc(db, location_id)
    ctx = build_context(db)
    sc = get_scenario(ctx.scenario_id)
    t = ctx.tick
    field = scenario_field_at(sc, t, loc.latitude, loc.longitude)

    return {
        "location_id": loc.id,
        "generated_at": ctx.now.isoformat() + "Z",
        "now": {
            "rain_intensity_mmh": round(field.get("rain_intensity") or 0, 1),
            "rain_accumulation_3h_mm": round(field.get("rain_accumulation_3h") or 0, 1),
            "forecast_rain_3h_mm": round(field.get("forecast_rain_3h") or 0, 1),
        },
        "buckets": _buckets(sc, loc.latitude, loc.longitude, t, 24),
        "data_mode": {"is_simulated": True, "label": "SIMULATED rainfall estimate"},
        "clock": scenario_clock(db),
    }


@router.get(
    "/rainfall/forecast",
    summary="Forward rainfall buckets (forecast)",
    description=(
        "Same accumulation buckets expressed as the nowcaster's forward projection. The "
        "forecast is deliberately seeded from the scenario curve with skill decay, so short "
        "horizons are reliable and long horizons are not."),
    responses={404: {"description": "Unknown location"}},
)
def rainfall_forecast(
    location_id: str = Query(default="loc_kurla", description="Monitored ward"),
    horizon_hours: int = Query(default=6, ge=1, le=24),
    db: Session = Depends(get_db),
) -> dict:
    loc = _loc(db, location_id)
    ctx = build_context(db)
    sc = get_scenario(ctx.scenario_id)
    t = ctx.tick

    buckets = []
    for hour in range(1, horizon_hours + 1):
        acc = 0.0
        for k in range(0, 4 * hour):
            kt = t + k + 1
            f = scenario_field_at(sc, kt, loc.latitude, loc.longitude)
            acc += (f.get("forecast_rain_3h") or 0.0) / 3.0 * sc.tick_minutes / 60.0
            # decay skill: confidence falls with horizon
        skill = max(0.30, 1.0 - 0.10 * hour)
        buckets.append({
            "hours": hour,
            "forecast_mm": round(acc * skill, 1),
            "confidence": round(skill * 100, 0),
        })

    return {
        "location_id": loc.id,
        "issued_at": ctx.now.isoformat() + "Z",
        "source": "PEHRA Demo Nowcaster",
        "horizon_hours": horizon_hours,
        "buckets": buckets,
        "data_mode": {"is_simulated": True, "label": "SIMULATED forecast"},
        "clock": scenario_clock(db),
    }