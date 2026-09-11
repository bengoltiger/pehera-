"""Hospital layer (Section MB-11).

Seeded Mumbai hospitals with bed capacity, contact details and a risk-derived
operational state. Hospital data is a labelled demo dataset — real facilities,
illustrative positions and fictional capacities.
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

router = APIRouter(tags=["hospitals"])


def _hospital_dict(row: Infrastructure, risk: float, severity: str) -> dict:
    sev = (severity or "unavailable").lower()
    return {
        "id": row.id,
        "name": row.name,
        "kind": row.kind,
        "latitude": row.latitude,
        "longitude": row.longitude,
        "beds": row.capacity,
        "criticality": row.criticality,
        "address": row.address,
        "phone": row.phone,
        "location_id": row.location_id,
        "host_ward_risk": risk,
        "status": "operational"
        if sev in ("safe", "low", "moderate", "unavailable")
        else ("diverting" if sev == "high" else "stretched"),
        "data_origin": row.data_origin,
    }


@router.get(
    "/hospitals",
    summary="List hospitals with bed capacity",
    description=(
        "All seeded hospital facilities. `status` is derived from the host ward's current "
        "risk: `diverting` wards are HIGH, `stretched` wards are CRITICAL. Positions are "
        "illustrative and capacities fictional (labelled demo data)."
    ),
)
def list_hospitals(
    location_id: Optional[str] = Query(default=None, description="Filter by ward"),
    db: Session = Depends(get_db),
) -> dict:
    q = db.query(Infrastructure).filter(Infrastructure.kind == "hospital")
    if location_id:
        q = q.filter(Infrastructure.location_id == location_id)
    rows = q.order_by((Infrastructure.capacity.is_(None)), Infrastructure.capacity.desc()).all()
    risks = ward_risk(db)
    hospitals = [
        _hospital_dict(r, (risks.get(r.location_id) or {}).get("risk"),
                       (risks.get(r.location_id) or {}).get("severity", "unavailable"))
        for r in rows
    ]
    return {
        "count": len(hospitals),
        "total_beds": sum(h["beds"] or 0 for h in hospitals),
        "hospitals": hospitals,
        "data_mode": {"is_simulated": True, "label": "DEMO hospital dataset"},
        "clock": scenario_clock(db),
    }


@router.get(
    "/hospitals/nearest",
    summary="Nearest hospitals to a coordinate",
    responses={404: {"description": "No hospitals seeded"}},
)
def nearest_hospitals(
    lat: float = Query(ge=-90, le=90),
    lng: float = Query(ge=-180, le=180),
    limit: int = Query(default=3, ge=1, le=10),
    db: Session = Depends(get_db),
) -> dict:
    rows = db.query(Infrastructure).filter(Infrastructure.kind == "hospital").all()
    if not rows:
        raise HTTPException(status_code=404, detail={"error": "no_hospitals",
                                                     "message": "No hospitals are configured."})
    risks = ward_risk(db)
    ranked = sorted(
        ((haversine_km(lat, lng, r.latitude, r.longitude), r) for r in rows), key=lambda t: t[0]
    )[:limit]
    return {
        "query": {"lat": round(lat, 5), "lng": round(lng, 5)},
        "count": len(ranked),
        "hospitals": [
            {
                **_hospital_dict(r, (risks.get(r.location_id) or {}).get("risk"),
                                 (risks.get(r.location_id) or {}).get("severity", "unavailable")),
                "distance_km": round(d, 2),
            }
            for d, r in ranked
        ],
        "is_simulated": True,
        "clock": scenario_clock(db),
    }


@router.get(
    "/hospitals/{hospital_id}",
    summary="Hospital detail",
    responses={404: {"description": "Unknown hospital"}},
)
def get_hospital(hospital_id: str, db: Session = Depends(get_db)) -> dict:
    row = db.get(Infrastructure, hospital_id)
    if not row or row.kind != "hospital":
        raise HTTPException(status_code=404, detail={"error": "not_found",
                                                     "message": f"No hospital '{hospital_id}'."})
    risks = ward_risk(db)
    loc = db.get(Location, row.location_id)
    return {
        **_hospital_dict(row, (risks.get(row.location_id) or {}).get("risk"),
                         (risks.get(row.location_id) or {}).get("severity", "unavailable")),
        "host_ward": {"id": loc.id, "name": loc.name} if loc else None,
    }