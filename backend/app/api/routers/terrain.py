"""Terrain / DEM layer endpoints (Sections MB-3, MB-4).

Mumbai's flood behaviour is spatial: elevation, slope, coastal exposure and
drainage decide where water stands. This router exposes the DEM-derived grid
the risk engine leans on, so the map can render the terrain directly and the
engine and the map can never disagree.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.models import Location
from app.db.session import get_db
from app.engine.dem import flood_susceptibility
from app.engine.risk_field import build_terrain_grid
from app.services.prediction import _location_dict

router = APIRouter(tags=["terrain"])


@router.get(
    "/terrain",
    summary="DEM-derived terrain grid (elevation, slope, coastal exposure)",
    description=(
        "A regular grid over the monitored region. Each node carries elevation "
        "(m above MSL), slope, coastal exposure, drainage deficiency and the derived "
        "flood-susceptibility score (0–1). Values between seeded wards are "
        "inverse-distance interpolated and labelled as such."
    ),
)
def terrain_grid(
    step_deg: float = Query(default=0.012, ge=0.005, le=0.05),
    padding_deg: float = Query(default=0.06, ge=0.0, le=0.3),
    db: Session = Depends(get_db),
) -> dict:
    locations = db.query(Location).all()
    return build_terrain_grid(locations, step_deg=step_deg, padding_deg=padding_deg)


@router.get(
    "/terrain/point",
    summary="Terrain properties at an arbitrary coordinate",
    description="Same interpolation used by the grid, evaluated at a single point.",
)
def terrain_at_point(
    lat: float = Query(ge=-90, le=90),
    lng: float = Query(ge=-180, le=180),
    db: Session = Depends(get_db),
) -> dict:
    from app.engine.risk_field import _idw, build_sites

    sites = build_sites(db.query(Location).all())
    st = _idw(sites, lat, lng)
    return {
        "lat": round(lat, 6),
        "lng": round(lng, 6),
        "elevation_m": round(st["elevation"], 2),
        "slope_deg": round(st["slope"], 2),
        "coastal_exposure": round(st["coastal"], 4),
        "drainage_deficiency": round(st["drainage"], 3),
        "flood_susceptibility": round(flood_susceptibility(
            st["elevation"], st["slope"], st["drainage"]), 3),
        "nearest_location_id": st["nearest_id"],
        "nearest_km": st["nearest_km"],
        "interpolated": (st["nearest_km"] or 0) > 0.25,
        "note": "Static terrain properties are interpolated between seeded wards.",
    }