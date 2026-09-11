"""Shared current-risk snapshot for the spatial layer routers.

Traffic, routes, shelters and hospitals all need the *current* risk per ward so
their status fields agree with the risk the command centre shows. This helper
computes that once per request instead of duplicating it in every router.
"""
from __future__ import annotations

from typing import Dict

from sqlalchemy.orm import Session

from app.db.models import Location
from app.services.clock import build_context
from app.services.prediction import compute_prediction


def ward_risk(db: Session) -> Dict[str, dict]:
    ctx = build_context(db)
    out: Dict[str, dict] = {}
    for loc in db.query(Location).all():
        p = compute_prediction(db, loc, ctx=ctx, detail=False, persist=False)
        if p.get("available"):
            r = p["risk"]
            out[loc.id] = {
                "risk": r["overall"],
                "severity": r["severity"]["key"],
                "label": r["severity"]["label"],
                "hazard": p.get("dominant_hazard") or r.get("hazard"),
            }
        else:
            out[loc.id] = {"risk": None, "severity": "unavailable",
                           "label": "Unavailable", "hazard": None}
    return out