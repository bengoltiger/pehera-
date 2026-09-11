"""Gridded risk field (Sections 15, 17, 18).

Locations are discrete, but weather is not. Sampling the hazard model on a
regular grid gives PEHRA three things it cannot get from point locations
alone:

  * a genuine risk heat-map for the map view (not a decorative overlay);
  * threat-cell centroids that move smoothly, so bearing and speed are
    measured rather than asserted;
  * risk estimates for coordinates the user picks that are not a seeded ward.

Static properties (terrain, drainage, population density) at a grid node are
interpolated from the seeded locations by inverse-distance weighting. That is
an approximation, and the API labels it as one.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from app.core.risk_config import HAZARDS
from app.engine.dem import flood_susceptibility
from app.engine.normalise import normalise
from app.engine.risk_engine import compute_compound, score_hazard
from app.providers.base import ProviderContext
from app.simulation.scenarios import get_scenario, haversine_km, scenario_field_at

GRID_FEATURES = (
    "rain_intensity", "rain_accumulation_3h", "river_level_ratio", "river_rate",
    "soil_moisture", "wind_speed", "wind_gust", "forecast_rain_3h",
    "cloud_top_temp_k", "lightning_rate", "temperature_c", "humidity", "pressure_hpa",
    "tide_level_m", "surge_m", "tide_rise_rate",
)


@dataclass
class StaticSite:
    id: str
    lat: float
    lng: float
    terrain: float
    drainage: float
    density: float
    elevation: float
    slope: float
    coastal: float
    has_river: bool
    hazards: Sequence[str]


def build_sites(locations) -> List[StaticSite]:
    return [
        StaticSite(
            id=l.id,
            lat=l.latitude,
            lng=l.longitude,
            terrain=l.terrain_vulnerability,
            drainage=l.drainage_deficiency,
            density=l.population / max(l.area_km2, 0.01),
            elevation=getattr(l, "elevation_m", 0.0),
            slope=getattr(l, "slope_deg", 0.0),
            coastal=getattr(l, "coastal_exposure", 0.0),
            has_river=bool(l.river_id),
            hazards=tuple(l.primary_hazards or ["flood"]),
        )
        for l in locations
    ]


def _idw(sites: List[StaticSite], lat: float, lng: float, k: int = 3) -> dict:
    """Inverse-distance weighted static properties at an arbitrary point."""
    scored = sorted(
        ((haversine_km(lat, lng, s.lat, s.lng), s) for s in sites), key=lambda t: t[0]
    )[:k]
    if not scored:
        return {"terrain": 0.4, "drainage": 0.4, "density": 500.0, "elevation": 0.0,
                "slope": 0.0, "coastal": 0.0, "has_river": False,
                "hazards": ("flood",), "nearest_id": None, "nearest_km": None}
    if scored[0][0] < 0.25:
        s = scored[0][1]
        return {"terrain": s.terrain, "drainage": s.drainage, "density": s.density,
                "elevation": s.elevation, "slope": s.slope, "coastal": s.coastal,
                "has_river": s.has_river, "hazards": s.hazards,
                "nearest_id": s.id, "nearest_km": round(scored[0][0], 2)}
    weights = [1.0 / (d ** 2) for d, _ in scored]
    tw = sum(weights) or 1.0
    hazards: List[str] = []
    for _, s in scored:
        for h in s.hazards:
            if h not in hazards:
                hazards.append(h)
    return {
        "terrain": sum(w * s.terrain for w, (_, s) in zip(weights, scored)) / tw,
        "drainage": sum(w * s.drainage for w, (_, s) in zip(weights, scored)) / tw,
        "density": sum(w * s.density for w, (_, s) in zip(weights, scored)) / tw,
        "elevation": sum(w * s.elevation for w, (_, s) in zip(weights, scored)) / tw,
        "slope": sum(w * s.slope for w, (_, s) in zip(weights, scored)) / tw,
        "coastal": sum(w * s.coastal for w, (_, s) in zip(weights, scored)) / tw,
        "has_river": any(s.has_river for _, s in scored[:2]),
        "hazards": tuple(hazards[:3]),
        "nearest_id": scored[0][1].id,
        "nearest_km": round(scored[0][0], 2),
    }


def hazard_at_point(
    ctx: ProviderContext,
    lat: float,
    lng: float,
    sites: List[StaticSite],
    *,
    tick: Optional[int] = None,
) -> dict:
    """Environmental severity at an arbitrary coordinate. No exposure applied --
    this is the pure hazard field."""
    scenario = get_scenario(ctx.scenario_id)
    t = ctx.tick if tick is None else tick
    field = scenario_field_at(scenario, t, lat, lng)
    overrides = ctx.overrides or {}
    static = _idw(sites, lat, lng)

    raw: Dict[str, Optional[float]] = {}
    for feat in GRID_FEATURES:
        v = field.get(feat)
        if v is not None and feat in overrides:
            v = float(v) * float(overrides[feat])
        if v is not None and feat == "forecast_rain_3h" and "forecast_intensity" in overrides:
            v = float(v) * float(overrides["forecast_intensity"])
        raw[feat] = v
    if not static["has_river"]:
        raw["river_level_ratio"] = None
        raw["river_rate"] = None

    prev = scenario_field_at(scenario, max(0, t - 1), lat, lng)
    pi, ci = prev.get("rain_intensity"), field.get("rain_intensity")
    if pi is not None and ci is not None:
        m = float(overrides.get("rain_intensity", 1.0))
        raw["rain_acceleration"] = (ci - pi) * m * (60.0 / max(scenario.tick_minutes, 1))
    else:
        raw["rain_acceleration"] = None

    raw["terrain_vulnerability"] = static["terrain"]
    raw["drainage_deficiency"] = static["drainage"]
    raw["population_density"] = static["density"]
    raw["elevation_m"] = round(static["elevation"], 2)
    raw["slope_deg"] = round(static["slope"], 2)
    raw["coastal_exposure"] = round(static["coastal"], 4)
    raw["flood_susceptibility"] = flood_susceptibility(
        static["elevation"], static["slope"], static["drainage"]
    )

    norm = {k: normalise(k, v) for k, v in raw.items()}
    results = [score_hazard(h, norm, raw) for h in static["hazards"] if h in HAZARDS]
    compound = compute_compound(results)
    return {
        "lat": round(lat, 5),
        "lng": round(lng, 5),
        "severity": round(compound.compound_severity, 1),
        "hazard": compound.dominant_hazard,
        "nearest_location_id": static["nearest_id"],
        "nearest_km": static["nearest_km"],
        "interpolated": (static["nearest_km"] or 0) > 0.25,
    }


def sample_grid(
    ctx: ProviderContext,
    locations,
    *,
    step_deg: float = 0.035,
    padding_deg: float = 0.09,
    min_severity: float = 12.0,
    tick: Optional[int] = None,
) -> dict:
    """Sample the hazard field over the bounding box of monitored locations."""
    if not locations:
        return {"points": [], "bbox": None, "step_deg": step_deg}
    sites = build_sites(locations)
    lats = [l.latitude for l in locations]
    lngs = [l.longitude for l in locations]
    min_lat, max_lat = min(lats) - padding_deg, max(lats) + padding_deg
    min_lng, max_lng = min(lngs) - padding_deg, max(lngs) + padding_deg

    points: List[dict] = []
    n_lat = int((max_lat - min_lat) / step_deg) + 1
    n_lng = int((max_lng - min_lng) / step_deg) + 1
    for i in range(n_lat):
        lat = min_lat + i * step_deg
        for j in range(n_lng):
            lng = min_lng + j * step_deg
            p = hazard_at_point(ctx, lat, lng, sites, tick=tick)
            if p["severity"] >= min_severity:
                points.append({"lat": p["lat"], "lng": p["lng"],
                               "severity": p["severity"], "hazard": p["hazard"]})
    return {
        "points": points,
        "bbox": {"min_lat": round(min_lat, 4), "max_lat": round(max_lat, 4),
                 "min_lng": round(min_lng, 4), "max_lng": round(max_lng, 4)},
        "step_deg": step_deg,
        "count": len(points),
        "min_severity": min_severity,
        "note": "Hazard-only field (exposure not applied). Static terrain and population "
                "properties between seeded wards are interpolated.",
    }


def field_centroid(points: List[dict], threshold: float) -> Optional[dict]:
    hot = [p for p in points if p["severity"] >= threshold]
    if not hot:
        return None
    w = sum((p["severity"] - threshold + 1) ** 2 for p in hot) or 1.0
    lat = sum(p["lat"] * (p["severity"] - threshold + 1) ** 2 for p in hot) / w
    lng = sum(p["lng"] * (p["severity"] - threshold + 1) ** 2 for p in hot) / w
    return {"lat": round(lat, 6), "lng": round(lng, 6), "count": len(hot)}


def build_terrain_grid(locations, *, step_deg: float = 0.02, padding_deg: float = 0.05) -> dict:
    """Build the DEM/terrain layer: elevation, slope, coastal exposure and the
    derived flood-susceptibility score for every node of the Mumbai grid.

    This is the spatial dataset the map renders and that ward and grid-cell
    risk both lean on (Sections MB-3, MB-4). Values between seeded wards are
    inverse-distance interpolated and labelled as such.
    """
    if not locations:
        return {"points": [], "bbox": None}
    sites = build_sites(locations)
    lats = [l.latitude for l in locations]
    lngs = [l.longitude for l in locations]
    min_lat, max_lat = min(lats) - padding_deg, max(lats) + padding_deg
    min_lng, max_lng = min(lngs) - padding_deg, max(lngs) + padding_deg

    points: List[dict] = []
    n_lat = int((max_lat - min_lat) / step_deg) + 1
    n_lng = int((max_lng - min_lng) / step_deg) + 1
    for i in range(n_lat):
        lat = min_lat + i * step_deg
        for j in range(n_lng):
            lng = min_lng + j * step_deg
            st = _idw(sites, lat, lng)
            sus = flood_susceptibility(st["elevation"], st["slope"], st["drainage"])
            points.append({
                "lat": round(lat, 5),
                "lng": round(lng, 5),
                "elevation_m": round(st["elevation"], 1),
                "slope_deg": round(st["slope"], 2),
                "coastal_exposure": round(st["coastal"], 3),
                "flood_susceptibility": round(sus, 3),
                "drainage_deficiency": round(st["drainage"], 3),
            })
    return {
        "points": points,
        "bbox": {"min_lat": round(min_lat, 4), "max_lat": round(max_lat, 4),
                 "min_lng": round(min_lng, 4), "max_lng": round(max_lng, 4)},
        "step_deg": step_deg,
        "count": len(points),
        "note": "DEM-derived terrain grid. Elevation, slope and coastal exposure are "
                "interpolated between seeded ward reference points (IDW).",
    }
