"""Mumbai regional topology bundle (Predict / Telemetry map).

Serves a static, explicitly-indicative map of the region — wards, rivers,
creeks, lakes, salt pans, mangroves, forest, chronic flood spots and the
transport skeleton — so the authority's Predict screen can switch from a
cartoon radar to something that looks like the city they operate in.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.services.topology import build_topology

router = APIRouter(prefix="/map", tags=["map", "topology"])


@router.get(
    "/topology",
    summary="Mumbai regional topology bundle (indicative layers)",
    description=(
        "A curated, hand-drawn overview of the region: administrative wards, "
        "rivers (Mithi, Dahisar, Poisar, Oshiwara), creeks, lakes, salt pans, "
        "mangroves, Sanjay Gandhi NP, chronic flood spots, reclaimed low ground "
        "and the transport skeleton. Coordinates are APPROXIMATE demo "
        "geometry and carry an explicit 'is_simulated' honesty flag."
    ),
)
def mumbai_topology() -> dict:
    return build_topology()