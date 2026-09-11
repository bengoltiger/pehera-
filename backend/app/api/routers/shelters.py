"""Shelter layer (Section MB-12).

Active relief shelters with capacity, contact details and a risk-derived
readiness state. Shelter data is a labelled demo dataset — positions are
illustrative, capacities are fictional.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.models import Infrastructure, Location
from app.db.session import get_db
from app.services.clock import scenario_clock
from app.services.risk_snapshot import ward_risk
from app.simulation.scenarios import haversine_km

router = APIRouter(tags=["shelters"])


def _shelter_dict(row: Infrastructure, risk: float, severity: str) -> dict:
    sev = (severity or "unavailable").lower()
    return {
        "id": row.id,
        "name": row.name,
        "kind": row.kind,
        "latitude": row.latitude,
        "longitude": row.longitude,
        "capacity": row.capacity,
        "criticality": row.criticality,
        "address": row.address,
        "phone": row.phone,
        "location_id": row.location_id,
        "host_ward_risk": risk,
        "readiness": "ready" if sev in ("safe", "low", "moderate")
        else ("at_risk" if sev == "high" else "impacted"),
        "data_origin": row.data_origin,
    }


@router.get(
    "/shelters",
    summary="List active relief shelters",
    description=(
        "All seeded relief shelters with capacity and a readiness state derived from the "
        "host ward's current risk. `ready` shelters are safe to route people to; `at_risk` "
        "are themselves threatened; `impacted` sit inside a CRITICAL ward."
    ),
)
def list_shelters(
    location_id: Optional[str] = Query(default=None, description="Filter by ward"),
    db: Session = Depends(get_db),
) -> dict:
    q = db.query(Infrastructure).filter(Infrastructure.kind == "shelter")
    if location_id:
        q = q.filter(Infrastructure.location_id == location_id)
    rows = q.order_by((Infrastructure.capacity.is_(None)), Infrastructure.capacity.desc()).all()
    risks = ward_risk(db)
    shelters = [
        _shelter_dict(r, (risks.get(r.location_id) or {}).get("risk"),
                      (risks.get(r.location_id) or {}).get("severity", "unavailable"))
        for r in rows
    ]
    total_capacity = sum(s["capacity"] or 0 for s in shelters)
    return {
        "count": len(shelters),
        "total_capacity": total_capacity,
        "shelters": shelters,
        "data_mode": {"is_simulated": True, "label": "DEMO shelter dataset"},
        "clock": scenario_clock(db),
    }


@router.get(
    "/shelters/nearest",
    summary="Nearest shelters to a coordinate",
    responses={404: {"description": "No shelters seeded"}},
)
def nearest_shelters(
    lat: float = Query(ge=-90, le=90),
    lng: float = Query(ge=-180, le=180),
    limit: int = Query(default=3, ge=1, le=10),
    db: Session = Depends(get_db),
) -> dict:
    rows = db.query(Infrastructure).filter(Infrastructure.kind == "shelter").all()
    if not rows:
        raise HTTPException(status_code=404, detail={"error": "no_shelters",
                                                     "message": "No shelters are configured."})
    risks = ward_risk(db)
    ranked = sorted(
        ((haversine_km(lat, lng, r.latitude, r.longitude), r) for r in rows), key=lambda t: t[0]
    )[:limit]
    return {
        "query": {"lat": round(lat, 5), "lng": round(lng, 5)},
        "count": len(ranked),
        "shelters": [
            {
                **_shelter_dict(r, (risks.get(r.location_id) or {}).get("risk"),
                                (risks.get(r.location_id) or {}).get("severity", "unavailable")),
                "distance_km": round(d, 2),
            }
            for d, r in ranked
        ],
        "is_simulated": True,
        "clock": scenario_clock(db),
    }


@router.get(
    "/shelters/{shelter_id}",
    summary="Shelter detail",
    responses={404: {"description": "Unknown shelter"}},
)
def get_shelter(shelter_id: str, db: Session = Depends(get_db)) -> dict:
    row = db.get(Infrastructure, shelter_id)
    if not row or row.kind != "shelter":
        raise HTTPException(status_code=404, detail={"error": "not_found",
                                                     "message": f"No shelter '{shelter_id}'."})
    risks = ward_risk(db)
    loc = db.get(Location, row.location_id)
    return {
        **_shelter_dict(row, (risks.get(row.location_id) or {}).get("risk"),
                        (risks.get(row.location_id) or {}).get("severity", "unavailable")),
        "host_ward": {"id": loc.id, "name": loc.name} if loc else None,
    }