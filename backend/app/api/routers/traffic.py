"""Traffic / road-state layer (Section MB-13).

Congestion is derived from the current risk field: road segments near wards the
engine has already scored HIGH/CRITICAL are slowed or blocked. No telemetry is
invented — the demo derives road state from the same risk number the command
centre shows.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.models import Infrastructure, Location
from app.db.session import get_db
from app.services.clock import scenario_clock
from app.services.risk_snapshot import ward_risk

router = APIRouter(tags=["traffic"])

# Named Mumbai corridors as [from_lat, from_lng, to_lat, to_lng].
_CORRIDORS = [
    ("Western Express Hwy (Borivali–Dadar)", 19.2290, 72.8550, 19.0178, 72.8478),
    ("Eastern Express Hwy (Mulund–Sion)", 19.1720, 72.9570, 19.0400, 72.8610),
    ("Sion–Panvel Hwy (Sion–Vashi)", 19.0400, 72.8610, 19.0700, 73.0000),
    ("LBS Rd (Kurla–Mulund)", 19.0697, 72.8834, 19.1720, 72.9570),
    ("SV Rd (Dadar–Andheri)", 19.0178, 72.8478, 19.1200, 72.8480),
    ("Marine Drive (Nariman Point–Malabar Hill)", 18.9340, 72.8230, 18.9610, 72.8080),
    ("Goregaon–Mulund Link Rd", 19.1650, 72.8480, 19.1720, 72.9570),
    ("Vellard / JJ Flyover (Dadargri–Marine Lines)", 18.9930, 72.8360, 18.9380, 72.8290),
]


def _congestion_from(risk: float) -> tuple[str, float, float]:
    """(status, congestion 0-100, speed_kmh)."""
    if risk is None:
        return "unknown", 50.0, 22.0
    if risk >= 81:
        return "blocked", 98.0, 5.0
    if risk >= 61:
        return "heavy", 85.0, 10.0
    if risk >= 41:
        return "moderate", 60.0, 18.0
    if risk >= 21:
        return "light", 30.0, 28.0
    return "freeflow", 12.0, 36.0


@router.get(
    "/traffic",
    summary="Road state and congestion (derived from current risk)",
    description=(
        "Major Mumbai corridors, each scored from the risk engine's current per-ward output: "
        "a corridor near a HIGH/CRITICAL ward is slowed or blocked. Nothing here is "
        "fabricated telemetry — the state is derived from the same risk the command centre "
        "is looking at."
    ),
)
def traffic(db: Session = Depends(get_db)) -> dict:
    risks = ward_risk(db)
    corridors = []
    for name, a_lat, a_lng, b_lat, b_lng in _CORRIDORS:
        # find the wards nearest either end to anchor the segment's risk
        near: list[tuple[float, str]] = []
        for loc in db.query(Location).all():
            d = (loc.latitude - a_lat) ** 2 + (loc.longitude - a_lng) ** 2
            near.append((d, loc.id))
        near.sort(key=lambda x: x[0])
        ward_id = near[0][1]
        risk = (risks.get(ward_id) or {}).get("risk")
        status, congestion, speed = _congestion_from(risk)
        corridors.append({
            "id": "cor_" + name[:4].lower().replace(" ", "_") + str(len(corridors)),
            "name": name,
            "from": {"lat": round(a_lat, 5), "lng": round(a_lng, 5)},
            "to": {"lat": round(b_lat, 5), "lng": round(b_lng, 5)},
            "ward_anchor": ward_id,
            "congestion": congestion,
            "status": status,
            "speed_kmh": speed,
            "bound_ward_risk": risk,
        })

    blocked = [c for c in corridors if c["status"] == "blocked"]
    return {
        "count": len(corridors),
        "corridors": corridors,
        "blocked": blocked,
        "summary": {
            "open": sum(1 for c in corridors if c["status"] == "freeflow"),
            "light": sum(1 for c in corridors if c["status"] == "light"),
            "moderate": sum(1 for c in corridors if c["status"] == "moderate"),
            "heavy": sum(1 for c in corridors if c["status"] == "heavy"),
            "blocked": len(blocked),
        },
        "data_mode": {"is_simulated": True, "label": "SIMULATED traffic — derived from risk"},
        "clock": scenario_clock(db),
    }