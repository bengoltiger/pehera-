"""Safe-route planner (Section MB-14).

The planner scores candidate paths against the same hazard field the risk map
uses: a path whose sample points stay below the severity threshold wins. This is
a genuinely derived feature — the route is *because* of the risk field, not
decorated on top of it.
"""
from __future__ import annotations

import math
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.models import Infrastructure, Location
from app.db.session import get_db
from app.engine.risk_field import build_sites, hazard_at_point
from app.services.clock import build_context, scenario_clock
from app.simulation.scenarios import haversine_km

router = APIRouter(tags=["routes"])

_SAMPLE_EVERY_KM = 0.5
_BLOCK_SEVERITY = 81.0
_SLOW_SEVERITY = 61.0


def _walk_line(a_lat: float, a_lng: float, b_lat: float, b_lng: float,
               step_km: float = _SAMPLE_EVERY_KM) -> List[tuple[float, float]]:
    total = haversine_km(a_lat, a_lng, b_lat, b_lng)
    n = max(1, int(math.ceil(total / step_km)))
    return [
        (a_lat + (b_lat - a_lat) * (i / n), a_lng + (b_lng - a_lng) * (i / n))
        for i in range(n + 1)
    ]


def _along(a_lat: float, a_lng: float, mid_lat: float, mid_lng: float,
           b_lat: float, b_lng: float, step_km: float = _SAMPLE_EVERY_KM):
    return _walk_line(a_lat, a_lng, mid_lat, mid_lng, step_km) + \
        _walk_line(mid_lat, mid_lng, b_lat, b_lng, step_km)


def _candidates(a_lat, a_lng, b_lat, b_lng) -> List[tuple]:
    mid_lat, mid_lng = (a_lat + b_lat) / 2, (a_lng + b_lng) / 2
    span_km = haversine_km(a_lat, a_lng, b_lat, b_lng)
    delta_lat = (b_lat - a_lat)
    delta_lng = (b_lng - a_lng)
    norm = math.hypot(delta_lat, delta_lng) or 1.0
    perp_km = max(1.5, span_km * 0.18)
    dlat = -delta_lng / norm * (perp_km / 110.574)
    dlng = delta_lat / norm * (perp_km / (111.320 * math.cos(math.radians(mid_lat))))
    offset = span_km * 0.12 / 110.574
    return [
        (a_lat, a_lng, b_lat, b_lng, "Shortest"),  # direct
        (a_lat, a_lng, mid_lat + dlat, mid_lng + dlng, b_lat, b_lng, "North detour"),
        (a_lat, a_lng, mid_lat - dlat, mid_lng - dlng, b_lat, b_lng, "South detour"),
        (a_lat, a_lng, mid_lat, mid_lng - offset * 0.5, b_lat, b_lng, "West detour"),
        (a_lat, a_lng, mid_lat, mid_lng + offset * 0.5, b_lat, b_lng, "East detour"),
    ]


def _score_route(sites, ctx, pts: List[tuple[float, float]]) -> dict:
    worst = 0.0
    worst_hazard: Optional[str] = None
    worst_pt: Optional[tuple[float, float]] = None
    for lat, lng in pts:
        p = hazard_at_point(ctx, lat, lng, sites)
        if p["severity"] > worst:
            worst = p["severity"]
            worst_hazard = p["hazard"]
            worst_pt = (p["lat"], p["lng"])
    blocked = worst >= _BLOCK_SEVERITY
    slow = worst >= _SLOW_SEVERITY
    speed = 8.0 if blocked else (20.0 if slow else 32.0)
    dist = sum(
        haversine_km(a[0], a[1], b[0], b[1])
        for a, b in zip(pts, pts[1:])
    )
    return {
        "max_severity": round(worst, 1),
        "worst_hazard": worst_hazard,
        "worst_point": {"lat": worst_pt[0], "lng": worst_pt[1]} if worst_pt else None,
        "blocked": blocked,
        "slow": slow,
        "distance_km": round(dist, 2),
        "eta_minutes": int(round(dist / speed * 60)),
    }


def _points_to_polyline(pts) -> List[dict]:
    thinned = [p for i, p in enumerate(pts) if i % 2 == 0 or i == len(pts) - 1]
    return [{"lat": round(p[0], 5), "lng": round(p[1], 5)} for p in thinned]


@router.get(
    "/routes",
    summary="Safest route between two coordinates",
    description=(
        "Planner scored against the live hazard field. Candidate paths are sampled every "
        "~500 m and the one with the lowest peak severity is returned; a path whose worst "
        "point is CRITICAL is reported as blocked. `polyline` can be dropped straight onto "
        "a map."
    ),
)
def plan_route(
    from_lat: float = Query(default=18.9306, ge=-90, le=90),
    from_lng: float = Query(default=72.8337, ge=-180, le=180),
    to_lat: float = Query(default=19.0697, ge=-90, le=90),
    to_lng: float = Query(default=72.8834, ge=-180, le=180),
    db: Session = Depends(get_db),
) -> dict:
    ctx = build_context(db)
    sites = build_sites(db.query(Location).all())
    scored: List[tuple[float, dict, List[tuple]]] = []
    for c in _candidates(from_lat, from_lng, to_lat, to_lng):
        if len(c) == 5:
            pts = _walk_line(c[0], c[1], c[2], c[3])
            name = c[4]
        else:
            pts = _along(c[0], c[1], c[2], c[3], c[4], c[5])
            name = c[6]
        s = _score_route(sites, ctx, pts)
        scored.append((s["max_severity"], s, pts, name))

    scored.sort(key=lambda x: (x[0]))
    best = scored[0]

    return {
        "from": {"lat": round(from_lat, 5), "lng": round(from_lng, 5)},
        "to": {"lat": round(to_lat, 5), "lng": round(to_lng, 5)},
        "scenario_id": ctx.scenario_id,
        "tick": ctx.tick,
        "best": best[3],
        "route": {
            "label": best[3],
            "polyline": _points_to_polyline(best[2]),
            **best[1],
        },
        "alternatives": [
            {"label": name, "max_severity": s["max_severity"],
             "distance_km": s["distance_km"], "blocked": s["blocked"]}
            for _, s, _, name in scored
        ],
        "note": "Route safety is scored on simulated hazard data; roads themselves are not modelled.",
        "is_simulated": True,
        "clock": scenario_clock(db),
    }


@router.get(
    "/routes/evacuation",
    summary="Evacuation route to the nearest shelters",
    description="Nearest two shelters with planned safe routes and each route's peak severity.",
    responses={404: {"description": "Unknown location"}},
)
def evacuation_plan(
    location_id: str = Query(default="loc_kurla"),
    db: Session = Depends(get_db),
) -> dict:
    loc = db.get(Location, location_id)
    if not loc:
        raise HTTPException(status_code=404, detail={"error": "location_not_found",
                                                     "message": f"No location '{location_id}'."})
    shelters = (
        db.query(Infrastructure)
        .filter(Infrastructure.kind == "shelter")
        .order_by(Infrastructure.capacity.desc())
        .all()
    )
    near = sorted(
        ((haversine_km(loc.latitude, loc.longitude, s.latitude, s.longitude), s) for s in shelters),
        key=lambda t: t[0],
    )[:2]

    ctx = build_context(db)
    sites = build_sites(db.query(Location).all())
    routes = []
    for d, sh in near:
        scored = []
        for c in _candidates(loc.latitude, loc.longitude, sh.latitude, sh.longitude):
            if len(c) == 5:
                pts = _walk_line(c[0], c[1], c[2], c[3])
                name = c[4]
            else:
                pts = _along(c[0], c[1], c[2], c[3], c[4], c[5])
                name = c[6]
            s = _score_route(sites, ctx, pts)
            scored.append((s["max_severity"], s, pts, name))
        scored.sort(key=lambda x: x[0])
        s = scored[0][1]
        routes.append({
            "shelter_id": sh.id,
            "shelter_name": sh.name,
            "address": sh.address,
            "phone": sh.phone,
            "capacity": sh.capacity,
            "distance_km": round(d, 2),
            "eta_minutes": int(round(d / (20.0 if s["slow"] else 32.0) * 60)),
            "peak_severity": s["max_severity"],
            "blocked": s["blocked"],
            "polyline": _points_to_polyline(scored[0][2]),
        })
    return {
        "from": {"location_id": loc.id, "name": loc.name},
        "routes": routes,
        "is_simulated": True,
        "clock": scenario_clock(db),
    }