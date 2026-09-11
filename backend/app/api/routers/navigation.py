"""Navigation API (Sections MB-14, 22, 29).

Endpoints behind the :class:`RoutingProvider` abstraction:

  * ``GET  /api/routes/providers``   -- what planners exist and their honesty notes;
  * ``POST /api/routes/plan``        -- hazard-aware route between two coordinates
      (optionally requesting a preference). Returns the normalsed Section 29
      response for the chosen plan plus the alternatives for the other modes;
  * ``GET  /api/routes/{route_id}``   -- retrieve a stored, last-evaluated route;
  * ``POST /api/routes/{route_id}/re-route`` -- re-score the route against the
      current clock; if the risk level changed, publishes ``route.updated`` on
      the SSE bus (which the citizen client listens for) and returns a fresh
      plan when one is needed.

Routes are short-lived in-memory objects (a route is a session, not a
database record). Every response carries ``is_simulated: true``.
"""
from __future__ import annotations

import threading
from typing import Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.routing import RoutePlan, get_provider, providers

router = APIRouter(prefix="/routes", tags=["routes", "navigation"])

_active: Dict[str, RoutePlan] = {}
_lock = threading.Lock()


class PlanRequest(BaseModel):
    from_lat: float = Field(..., ge=-90, le=90)
    from_lng: float = Field(..., ge=-180, le=180)
    to_lat: float = Field(..., ge=-90, le=90)
    to_lng: float = Field(..., ge=-180, le=180)
    preference: str = Field(default="balanced", pattern="^(fastest|balanced|safest)$")


class ReRouteResult(BaseModel):
    route_id: str
    changed: bool
    previous_level: str
    risk_level: str
    risk_reason: str
    recommendation: str


@router.get("/providers", summary="Registered routing providers")
def list_providers() -> dict:
    return {
        "providers": [p.describe() for p in providers()],
        "default": "hazard_aware",
        "is_simulated": True,
        "note": "All routing in this deployment is derived from the simulated "
                "hazard field. No external routing engine is connected.",
    }


@router.post("/plan", summary="Plan a hazard-aware route (Section 29 response)",
             response_model=dict)
def plan_route(body: PlanRequest, db: Session = Depends(get_db)) -> dict:
    provider = get_provider()
    chosen = provider.plan(
        db,
        from_lat=body.from_lat, from_lng=body.from_lng,
        to_lat=body.to_lat, to_lng=body.to_lng,
        preference=body.preference,
    )
    alternatives = [
        provider.plan(
            db,
            from_lat=body.from_lat, from_lng=body.from_lng,
            to_lat=body.to_lat, to_lng=body.to_lng,
            preference=p,
        )
        for p in ("fastest", "balanced", "safest")
        if p != body.preference
    ]
    result = chosen.to_dict(db)
    result["alternatives"] = [a.to_dict(db, include_geometry=False) for a in alternatives]
    with _lock:
        _active[chosen.route_id] = chosen
        for a in alternatives:
            _active[a.route_id] = a
        if len(_active) > 64:
            # drop oldest by insertion order (dicts are ordered)
            for k in list(_active)[: len(_active) - 64]:
                _active.pop(k, None)
    return result


@router.get("/{route_id}", summary="Retrieve a stored route")
def get_route(route_id: str, db: Session = Depends(get_db)) -> dict:
    plan = _active.get(route_id)
    if not plan:
        raise HTTPException(status_code=404, detail={
            "error": "route_not_found",
            "message": "Unknown or expired route id. Plan a new route.",
        })
    return plan.to_dict(db)


@router.post("/{route_id}/re-route", summary="Re-evaluate a route and recommend re-routing",
             response_model=ReRouteResult)
def re_route(route_id: str, db: Session = Depends(get_db)) -> ReRouteResult:
    plan = _active.get(route_id)
    if not plan:
        raise HTTPException(status_code=404, detail={
            "error": "route_not_found",
            "message": "Unknown or expired route id. Plan a new route.",
        })
    result = get_provider().re_evaluate(db, plan)
    return ReRouteResult(**result)