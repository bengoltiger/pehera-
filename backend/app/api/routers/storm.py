"""Storm / weather-system tracker endpoint (Sections MB-7, MB-8).

Cyclonic systems, cloudburst clusters and surge events are the forcing behind
Mumbai's worst flooding. Each scenario carries an epicentre track and forcing
curves; this router turns that into a weather-system view: where the system is
now, how strong it is, where it is heading and what it will look like along the
way. Everything is deterministic simulated data.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.clock import build_context, scenario_clock
from app.simulation.scenarios import haversine_km

router = APIRouter(tags=["storm"])

# Key that tells the map whether a scenario is a system the coast must watch.
_SYSTEM_LABELS = {
    "mumbai_storm_surge": "Cyclonic storm",
    "mumbai_compound": "Cyclonic storm + surge",
    "mumbai_high_tide": "High spring tide",
    "mumbai_cloudburst": "Mesoscale convective cluster",
    "mumbai_heavy_rain": "Monsoon trough",
    "mumbai_mithi": "Monsoon trough (river watch)",
    "mumbai_normal": "Calm monsoon day",
    "mumbai_heatwave": "Heat dome (no system)",
}


def _system_present(labels: List[str], wind: float, surge: float) -> bool:
    if wind >= 30 or surge >= 0.3:
        return True
    return any("storm" in l or "trough" in l or "cluster" in l or "tide" in l for l in labels)


@router.get(
    "/storm",
    summary="Active weather system (position, intensity, heading)",
    description=(
        "Location and strength of the forcing system behind the current scenario, "
        "with its projected track. Uses the scenario epicentre track and forcing "
        "curves — the same physics the risk engine applies — so the storm view and "
        "the risk map always agree."
    ),
)
def current_storm(
    lead_ticks: int = Query(default=8, ge=1, le=12),
    db: Session = Depends(get_db),
) -> dict:
    ctx = build_context(db)
    from app.simulation.scenarios import get_scenario, scenario_field_at

    sc = get_scenario(ctx.scenario_id)
    t = ctx.tick
    clat, clng = sc.epicentre.at(t)
    field = scenario_field_at(sc, t, clat, clng)
    prev = scenario_field_at(sc, max(0, t - 1), clat, clng)
    nxt = scenario_field_at(sc, min(t + 1, sc.total_ticks), *sc.epicentre.at(t + 1))

    spd_kmh: Optional[float] = None
    brg: Optional[float] = None
    if t < sc.total_ticks:
        plat, plng = sc.epicentre.at(t + 1)
        d = haversine_km(clat, clng, plat, plng)
        minutes = sc.tick_minutes
        spd_kmh = round(d / (minutes / 60.0), 1) if minutes else None
        brg = round((math.degrees(math.atan2(
            math.sin(math.radians(plng - clng)) * math.cos(math.radians(plat)),
            math.cos(math.radians(clat)) * math.sin(math.radians(plat))
            - math.sin(math.radians(clat)) * math.cos(math.radians(plat))
            * math.cos(math.radians(plng - clng)))) + 360) % 360, 1) if d > 0.05 else None

    track = []
    for k in range(lead_ticks):
        kt = min(t + k, sc.total_ticks)
        kf = scenario_field_at(sc, kt, *sc.epicentre.at(kt))
        track.append({
            "tick": kt,
            "lat": round(sc.epicentre.at(kt)[0], 5),
            "lng": round(sc.epicentre.at(kt)[1], 5),
            "wind_speed": round(kf.get("wind_speed") or 0, 1),
            "wind_gust": round(kf.get("wind_gust") or 0, 1),
            "surge_m": round(kf.get("surge_m") or 0, 2),
            "rain_intensity": round(kf.get("rain_intensity") or 0, 1),
        })

    wind = field.get("wind_speed") or 0.0
    surge = field.get("surge_m") or 0.0
    gust = field.get("wind_gust") or 0.0
    rain = field.get("rain_intensity") or 0.0
    pressure = field.get("pressure_hpa")
    labels = sc.hazard_focus or []
    present = _system_present(labels, wind, surge)

    return {
        "system": {
            "name": "Arabian Sea system (demo)" if present else "No active system",
            "type": _SYSTEM_LABELS.get(sc.id, "Weather system"),
            "active": present,
            "latitude": round(clat, 5),
            "longitude": round(clng, 5),
            "bearing_deg": brg,
            "speed_kmh": spd_kmh,
            "radius_km": sc.decay_km,
        },
        "intensity": {
            "wind_speed_kmh": round(wind, 1),
            "gust_kmh": round(gust, 1),
            "surge_m": round(surge, 2),
            "tide_level_m": round(field.get("tide_level_m") or 0, 2),
            "rain_intensity_mmh": round(rain, 1),
            "central_pressure_hpa": round(pressure, 1) if pressure is not None else None,
            "trend_3h": "building" if (nxt.get("wind_speed") or 0) > wind + 2
            else ("weakening" if (nxt.get("wind_speed") or 0) < wind - 2 else "steady"),
        },
        "track": track,
        "clock": scenario_clock(db),
        "is_simulated": True,
        "note": "Deterministic simulated system — the whole storm is a scenario forcing function.",
    }


@router.get(
    "/storm/track",
    summary="Full epicentre track for the current scenario",
    description="Every tick position of the forcing system, for rendering the projected path.",
)
def storm_track(
    db: Session = Depends(get_db),
) -> dict:
    ctx = build_context(db)
    from app.simulation.scenarios import get_scenario, scenario_field_at

    sc = get_scenario(ctx.scenario_id)
    points = []
    for kt in range(0, sc.total_ticks + 1):
        kf = scenario_field_at(sc, kt, *sc.epicentre.at(kt))
        points.append({
            "tick": kt,
            "lat": round(sc.epicentre.at(kt)[0], 5),
            "lng": round(sc.epicentre.at(kt)[1], 5),
            "surge_m": round(kf.get("surge_m") or 0, 2),
            "wind_speed": round(kf.get("wind_speed") or 0, 1),
        })
    return {
        "scenario_id": sc.id,
        "points": points,
        "count": len(points),
        "is_simulated": True,
    }