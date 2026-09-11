"""Simulation, scenario, replay, what-if and demo-control endpoints."""
from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db.models import Location, Scenario, User
from app.db.session import get_db
from app.realtime.bus import bus, event_stream
from app.riskmodels.registry import model_registry
from app.schemas.api import (
    ConnectivityRequest,
    FailureRequest,
    JumpRequest,
    ModelSelectRequest,
    OverridesRequest,
    ResetRequest,
    ScenarioRunRequest,
    SimulationStepRequest,
    SpeedRequest,
    VerifyRequest,
    WhatIfRequest,
)
from app.security.auth import record_audit, require_authority
from app.services.clock import (
    get_state,
    scenario_clock,
    set_running,
    set_speed,
)
from app.services.orchestrator import (
    collapse_overrides,
    jump,
    refresh_region,
    replay_scenario,
    reset_demo,
    set_connectivity,
    set_failure,
    set_overrides,
    set_scenario,
    step,
    verify_predictions,
    what_if,
)
from app.simulation.scenarios import SCENARIOS

router = APIRouter(tags=["simulation"])


@router.get(
    "/scenarios",
    summary="Deterministic demo scenario library",
    description=(
        "Every scenario is a fixed forcing function — the same tick always produces the same "
        "environmental state, which is what makes the demo reproducible (Section 45)."
    ),
)
def list_scenarios(db: Session = Depends(get_db)) -> dict:
    rows = db.query(Scenario).all()
    by_id = {r.id: r for r in rows}
    return {
        "count": len(SCENARIOS),
        "current": scenario_clock(db),
        "scenarios": [
            {
                "id": s.id, "name": s.name, "description": s.description,
                "hazard_focus": s.hazard_focus, "focus_location_id": s.focus_location_id,
                "tick_minutes": s.tick_minutes, "total_ticks": s.total_ticks,
                "duration_minutes": s.duration_minutes(), "narrative": s.narrative,
                "expected_peak_tick": s.expected_peak_tick,
                "is_deterministic": True,
                "has_outages": bool(s.outages),
                "outages": s.outages,
                "seeded": s.id in by_id,
            }
            for s in SCENARIOS.values()
        ],
    }


@router.get("/simulation/state", summary="Current simulation clock and controls")
def sim_state(db: Session = Depends(get_db)) -> dict:
    state = get_state(db)
    return {
        **scenario_clock(db),
        "sliders": collapse_overrides(state.overrides or {}),
        "active_model": model_registry.preferred,
        "sse_subscribers": bus.subscriber_count,
    }


@router.post(
    "/scenarios/{scenario_id}/run",
    summary="Load a scenario (authority only)",
    description="Switches the simulation to a scenario and optionally fast-forwards to a tick. "
                "Running a scenario recomputes risk for every location.",
    responses={404: {"description": "Unknown scenario"}, 403: {"description": "Role not permitted"}},
)
def run_scenario(scenario_id: str, payload: ScenarioRunRequest, request: Request,
                 db: Session = Depends(get_db), user: User = Depends(require_authority)) -> dict:
    if scenario_id not in SCENARIOS:
        raise HTTPException(status_code=404, detail={"error": "unknown_scenario",
                                                     "message": f"No scenario '{scenario_id}'.",
                                                     "valid": list(SCENARIOS.keys())})
    out = set_scenario(db, scenario_id, reset_tick=payload.reset_tick)
    record_audit(db, actor=user, action="run_scenario", entity_type="scenario",
                 entity_id=scenario_id, to_state=f"tick={out['tick']}", request=request)
    db.commit()
    if payload.auto_advance_to:
        target = min(payload.auto_advance_to, SCENARIOS[scenario_id].total_ticks)
        step(db, steps=target - out["tick"])
    result = refresh_region(db)
    return {"scenario": scenario_clock(db), "summary": result["summary"]}


@router.post(
    "/simulation/step",
    summary="Advance the simulation clock (authority only)",
    description=(
        "Advances one or more ticks. Each tick re-runs the whole loop: providers emit new "
        "observations, the engine recomputes risk, threat cells are re-tracked and the alert "
        "decision engine runs. Updates are pushed over SSE."
    ),
)
def sim_step(payload: SimulationStepRequest, db: Session = Depends(get_db),
             user: User = Depends(require_authority)) -> dict:
    out = step(db, steps=payload.steps, run_alerts=payload.run_alerts)
    return {"clock": scenario_clock(db), **out}


@router.post(
    "/simulation/start",
    summary="Start the simulation clock (authority only)",
    description=(
        "Sets the clock state to running. Simulated time does not auto-advance in this "
        "demo — for safety every advance is explicit — but the state is broadcast to "
        "clients so a UI can reflect a running vs paused command post (Section 79)."
    ),
)
def sim_start(db: Session = Depends(get_db), user: User = Depends(require_authority)) -> dict:
    return set_running(db, True)


@router.post(
    "/simulation/pause",
    summary="Pause the simulation clock (authority only)",
)
def sim_pause(db: Session = Depends(get_db), user: User = Depends(require_authority)) -> dict:
    return set_running(db, False)


@router.post(
    "/simulation/speed",
    summary="Set clock speed multiplier (authority only)",
    description="1.0 equals one tick per explicit advance; the multiplier is broadcast as "
                "a display/expiry scale, it never makes time move without an explicit step.",
)
def sim_speed(payload: SpeedRequest, db: Session = Depends(get_db),
              user: User = Depends(require_authority)) -> dict:
    return set_speed(db, payload.speed)


@router.post(
    "/simulation/jump",
    summary="Jump the clock to a tick and recompute (authority only)",
    description="Fast-forwards or rewinds to an arbitrary tick, then recomputes the whole "
                "region (risk, threat cells, alerts) as if that tick had just happened.",
)
def sim_jump(payload: JumpRequest, db: Session = Depends(get_db),
             user: User = Depends(require_authority)) -> dict:
    out = jump(db, payload.tick, run_alerts=payload.run_alerts)
    return {"clock": scenario_clock(db), **out}


@router.post(
    "/simulation/refresh",
    summary="Recompute the whole region without advancing time",
    description="Useful after changing sliders, connectivity or the active model.",
)
def sim_refresh(db: Session = Depends(get_db), user: User = Depends(require_authority)) -> dict:
    out = refresh_region(db)
    return {"clock": scenario_clock(db), "summary": out["summary"]}


@router.post(
    "/simulation/overrides",
    summary="Set Simulation Lab sliders (authority only)",
    description=(
        "Multiplicative factors on the scenario baseline. One slider can expand to several "
        "features so the physics stays coherent — e.g. `rainfall` scales both intensity and "
        "3-hour accumulation (Section 77)."
    ),
)
def sim_overrides(payload: OverridesRequest, db: Session = Depends(get_db),
                  user: User = Depends(require_authority)) -> dict:
    expanded = set_overrides(db, payload.model_dump())
    out = refresh_region(db)
    return {"overrides": expanded, "sliders": payload.model_dump(),
            "clock": scenario_clock(db), "summary": out["summary"]}


@router.post(
    "/simulation/connectivity",
    summary="Force a connectivity state (authority only)",
    description="Drives the online / degraded / offline behaviour end to end: degraded links "
                "deliver older observations and reduce confidence; offline stops new "
                "observations entirely (Sections 35, 36).",
)
def sim_connectivity(payload: ConnectivityRequest, db: Session = Depends(get_db),
                     user: User = Depends(require_authority)) -> dict:
    out = set_connectivity(db, payload.mode)
    return {**out, "clock": scenario_clock(db)}


@router.post(
    "/simulation/failure",
    summary="Force a component failure (authority only)",
    description=(
        "Takes a provider or the ML model offline so failure handling can be demonstrated: "
        "the affected inputs become unavailable with a stated reason, confidence drops, and "
        "the model chain falls back visibly (Sections 63, 64, 65)."
    ),
)
def sim_failure(payload: FailureRequest, db: Session = Depends(get_db),
                user: User = Depends(require_authority)) -> dict:
    ff = set_failure(db, payload.component, payload.enabled)
    out = refresh_region(db)
    return {"forced_failures": ff, "clock": scenario_clock(db), "summary": out["summary"]}


@router.post(
    "/simulation/model",
    summary="Select the preferred risk model (authority only)",
    description="Switches the head of the model fallback chain. If the chosen model is "
                "unavailable the next one is used and the response says so.",
)
def sim_model(payload: ModelSelectRequest, db: Session = Depends(get_db),
              user: User = Depends(require_authority)) -> dict:
    model_registry.set_preferred(payload.model_key)
    from app.services.prediction import clear_caches

    clear_caches()
    out = refresh_region(db)
    return {
        "active": model_registry.preferred,
        "models": [m.describe() for m in model_registry.all()],
        "summary": out["summary"],
    }


@router.post(
    "/simulation/reset",
    summary="RESET DEMO — restore a known state (authority only)",
    description=(
        "Deletes every simulation-derived record (predictions, snapshots, alerts, deliveries, "
        "acknowledgements, threat cells, early signals, verifications, logs and generated "
        "incidents), clears all overrides and failures, restores the model chain and re-seeds "
        "reference data. The archived historical incident records are preserved (Section 80)."
    ),
)
def sim_reset(payload: ResetRequest, request: Request, db: Session = Depends(get_db),
              user: User = Depends(require_authority)) -> dict:
    out = reset_demo(db, scenario_id=payload.scenario_id)
    record_audit(db, actor=user, action="reset_demo", entity_type="system",
                 to_state=out["scenario_id"], detail=out["cleared"], request=request)
    db.commit()
    refresh_region(db)
    return {**out, "clock": scenario_clock(db)}


@router.post(
    "/what-if",
    summary="WHAT-IF LAB — hypothetical recomputation",
    description=(
        "Recomputes risk under hypothetical inputs without persisting anything and without "
        "creating alerts. Returns the baseline, the modified result, the delta, and a "
        "one-factor-at-a-time attribution showing which change moved the prediction most "
        "(Section 44)."
    ),
    responses={404: {"description": "Unknown location"}},
)
def post_what_if(payload: WhatIfRequest, db: Session = Depends(get_db)) -> dict:
    loc = db.get(Location, payload.location_id)
    if not loc:
        raise HTTPException(status_code=404, detail={"error": "location_not_found",
                                                     "message": "Unknown location."})
    overrides = {k: v for k, v in payload.model_dump().items() if k != "location_id"}
    active = {k: v for k, v in overrides.items() if abs(v - 1.0) > 1e-6}
    return what_if(db, loc, active or overrides)


@router.get(
    "/replay/{scenario_id}",
    summary="EVENT REPLAY — frame-by-frame scenario history",
    description=(
        "Runs a scenario end-to-end and returns every frame: inputs, risk, severity, "
        "confidence, uncertainty, momentum, early signals, explanation, projected peak and the "
        "implied alert level — plus a generated narrative of the event (Sections 43, 69). "
        "Does not disturb the live simulation state."
    ),
    responses={404: {"description": "Unknown scenario"}},
)
def get_replay(scenario_id: str, location_id: Optional[str] = None,
               db: Session = Depends(get_db)) -> dict:
    if scenario_id not in SCENARIOS:
        raise HTTPException(status_code=404, detail={"error": "unknown_scenario",
                                                     "message": f"No scenario '{scenario_id}'."})
    return replay_scenario(db, scenario_id=scenario_id, location_id=location_id)


@router.post(
    "/verify",
    summary="Run prediction-vs-actual verification (authority only)",
    description=(
        "Replays a scenario, compares each forecast against the risk the engine later computed "
        "from the observations that actually arrived, classifies every case "
        "(correct / under / over / false positive / missed) and stores the results so the model "
        "performance dashboard has measured — not invented — numbers (Sections 41, 42)."
    ),
    responses={404: {"description": "Unknown scenario"}},
)
def post_verify(payload: VerifyRequest, db: Session = Depends(get_db),
                user: User = Depends(require_authority)) -> dict:
    if payload.scenario_id not in SCENARIOS:
        raise HTTPException(status_code=404, detail={"error": "unknown_scenario",
                                                     "message": "Unknown scenario."})
    return verify_predictions(db, scenario_id=payload.scenario_id, location_id=payload.location_id)


@router.get(
    "/events",
    summary="Server-Sent Events stream",
    description=(
        "Live channel for risk updates, simulation ticks, alert changes, threat movement and "
        "connectivity changes. Every frame carries `is_simulated: true` — these are updates "
        "from PEHRA's own simulation clock, not real-world observations (Section 55)."
    ),
)
async def events(request: Request) -> StreamingResponse:
    queue = bus.subscribe()

    async def gen():
        try:
            async for frame in event_stream(queue):
                if await request.is_disconnected():
                    break
                yield frame
        finally:
            bus.unsubscribe(queue)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


@router.get("/events/recent", summary="Recent realtime events (polling fallback)")
def recent_events(limit: int = Query(default=20, ge=1, le=100)) -> dict:
    return {"events": bus.recent(limit), "subscribers": bus.subscriber_count}
