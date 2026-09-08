"""Simulation clock & provider context (Sections 55, 77, 80).

The whole system reads its "now" through this module. In a production
deployment the clock would simply be wall-time and `tick` would disappear;
everything downstream is written against `ProviderContext`, not against the
simulator.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from sqlalchemy.orm import Session

from app.db.models import SimulationState
from app.providers.base import ProviderContext
from app.simulation.scenarios import get_scenario


def get_state(db: Session) -> SimulationState:
    state = db.get(SimulationState, 1)
    if not state:
        state = SimulationState(
            id=1, scenario_id="normal_day", tick=0, running=False, speed=1.0,
            overrides={}, connectivity="online", forced_failures={},
        )
        db.add(state)
        db.commit()
        db.refresh(state)
    return state


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def build_context(db: Session, *, tick_override: Optional[int] = None,
                  overrides_extra: Optional[dict] = None) -> ProviderContext:
    state = get_state(db)
    overrides = dict(state.overrides or {})
    if overrides_extra:
        overrides.update(overrides_extra)
    return ProviderContext(
        now=utcnow(),
        scenario_id=state.scenario_id,
        tick=state.tick if tick_override is None else tick_override,
        overrides=overrides,
        connectivity=state.connectivity,
        forced_failures=dict(state.forced_failures or {}),
    )


def scenario_clock(db: Session) -> dict:
    """Human-readable position within the running scenario."""
    state = get_state(db)
    sc = get_scenario(state.scenario_id)
    elapsed = state.tick * sc.tick_minutes
    return {
        "scenario_id": sc.id,
        "scenario_name": sc.name,
        "tick": state.tick,
        "total_ticks": sc.total_ticks,
        "tick_minutes": sc.tick_minutes,
        "elapsed_minutes": elapsed,
        "elapsed_label": f"T+{elapsed // 60}h {elapsed % 60:02d}m",
        "running": state.running,
        "speed": state.speed,
        "connectivity": state.connectivity,
        "overrides": state.overrides or {},
        "forced_failures": state.forced_failures or {},
        "at_end": state.tick >= sc.total_ticks,
        "expected_peak_tick": sc.expected_peak_tick,
        "narrative": sc.narrative,
    }
