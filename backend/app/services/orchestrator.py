"""Orchestration: regional refresh, simulation stepping, replay, what-if, reset.

This is the conductor. It runs the full loop for every monitored location:

    OBSERVE → UNDERSTAND → PREDICT → EXPLAIN → PRIORITIZE → WARN
"""
from __future__ import annotations

import datetime as dt
from typing import Dict, List, Optional

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.alerts.engine import explain_priority, priority_score
from app.core.risk_config import ALERTS, HAZARDS, VERIFICATION
from app.db.models import (
    Alert,
    AlertAcknowledgement,
    AlertDelivery,
    AlertTransition,
    EarlySignal,
    Incident,
    Location,
    PredictionSnapshot,
    PredictionVerification,
    RiskPrediction,
    SimulationState,
    SystemLog,
    ThreatCell,
    new_id,
)
from app.engine.risk_field import sample_grid
from app.engine.threat_cells import cell_to_dict, detect_and_track
from app.realtime.bus import bus
from app.services.alerts import evaluate_and_recommend
from app.services.clock import build_context, get_state, utcnow
from app.services.observability import log_event, trim_logs
from app.services.prediction import (
    clear_caches,
    compute_prediction,
    critical_facility_count,
)
from app.simulation.scenarios import get_scenario, haversine_km

# in-memory cache of the last full regional sweep
_last_sweep: Dict[str, dict] = {}


def all_locations(db: Session) -> List[Location]:
    return db.query(Location).order_by(Location.name).all()


def refresh_region(
    db: Session,
    *,
    persist_predictions: bool = True,
    run_alerts: bool = True,
    detail: bool = True,
) -> dict:
    """One full pass of the intelligence loop over every monitored location."""
    started = dt.datetime.now()
    ctx = build_context(db)
    scenario = get_scenario(ctx.scenario_id)
    locations = all_locations(db)

    predictions: Dict[str, dict] = {}
    risk_rows: List[dict] = []

    for loc in locations:
        pred = compute_prediction(
            db, loc, ctx=ctx, detail=detail, persist=persist_predictions
        )
        predictions[loc.id] = pred
        if not pred.get("available"):
            continue
        peak = (pred.get("peak") or {}).get("risk")
        risk_rows.append(
            {
                "location_id": loc.id,
                "name": loc.name,
                "lat": loc.latitude,
                "lng": loc.longitude,
                "risk": pred["risk"]["overall"],
                "predicted_risk": peak or pred["risk"]["overall"],
                "hazard": pred["hazard"]["dominant"],
                "confidence": pred["risk"]["confidence"]["value"],
                "population": loc.population,
            }
        )
        # persist detected early signals so the incident story can cite them
        for sig in pred.get("early_signals", []):
            exists = (
                db.query(EarlySignal)
                .filter(
                    EarlySignal.location_id == loc.id,
                    EarlySignal.kind == sig["kind"],
                    EarlySignal.scenario_tick == ctx.tick,
                )
                .first()
            )
            if not exists:
                db.add(
                    EarlySignal(
                        id=new_id("sig"),
                        location_id=loc.id,
                        kind=sig["kind"],
                        label=sig["label"],
                        detail=sig["detail"],
                        magnitude=sig["magnitude"],
                        risk_at_detection=sig["risk_at_detection"],
                        detected_at=ctx.now,
                        scenario_tick=ctx.tick,
                    )
                )
    db.commit()

    # ---- gridded hazard field (drives the heat-map and cell tracking) ----
    field = sample_grid(ctx, locations)

    # ---- threat cells ----
    cells = detect_and_track(
        db,
        location_risks=risk_rows,
        field_points=field["points"],
        now=ctx.now,
        tick=ctx.tick,
        tick_minutes=scenario.tick_minutes,
    )
    cell_dicts = [cell_to_dict(c) for c in cells]

    # ---- alerting ----
    alert_actions: List[dict] = []
    if run_alerts:
        for loc in locations:
            pred = predictions.get(loc.id)
            if not pred or not pred.get("available"):
                continue
            entering, cell_id = _cell_entering(cell_dicts, loc)
            action = evaluate_and_recommend(
                db,
                location=loc,
                prediction=pred,
                threat_cell_id=cell_id,
                threat_cell_entering=entering,
                tick=ctx.tick,
            )
            if action.get("action") not in ("no_alert", "skipped"):
                alert_actions.append({"location_id": loc.id, **action})

    # ---- priority queue ----
    queue = build_priority_queue(db, predictions)

    duration = (dt.datetime.now() - started).total_seconds() * 1000
    log_event(
        db, level="info", component="orchestrator", event="region_refreshed",
        message=f"Refreshed {len(locations)} locations at tick {ctx.tick}",
        context={"scenario": ctx.scenario_id, "tick": ctx.tick, "cells": len(cell_dicts)},
        duration_ms=duration,
    )
    trim_logs(db)
    db.commit()

    summary = {
        "generated_at": ctx.now.isoformat() + "Z",
        "scenario": {"id": scenario.id, "name": scenario.name, "tick": ctx.tick,
                     "total_ticks": scenario.total_ticks, "tick_minutes": scenario.tick_minutes},
        "connectivity": ctx.connectivity,
        "locations": len(locations),
        "threat_cells": cell_dicts,
        "risk_field": field,
        "alert_actions": alert_actions,
        "priority_queue": queue,
        "duration_ms": round(duration, 1),
    }
    _last_sweep.clear()
    _last_sweep.update({"summary": summary, "predictions": predictions})

    bus.publish("risk_update", {
        "tick": ctx.tick,
        "scenario": scenario.id,
        "top": queue[:5],
        "threat_cells": len(cell_dicts),
        "alert_actions": alert_actions,
    })
    return {"summary": summary, "predictions": predictions}


def _cell_entering(cells: List[dict], loc: Location) -> tuple[bool, Optional[str]]:
    """Is a moving threat cell projected to reach this populated location?"""
    for c in cells:
        if not c["movement"]["is_moving"]:
            continue
        for p in c.get("predicted_track") or []:
            d = haversine_km(loc.latitude, loc.longitude, p["lat"], p["lng"])
            if d <= c["radius_km"]:
                now_d = haversine_km(loc.latitude, loc.longitude,
                                     c["center"]["lat"], c["center"]["lng"])
                if now_d > c["radius_km"]:
                    return True, c["id"]
    for c in cells:
        if loc.id in (c.get("location_ids") or []):
            return False, c["id"]
    return False, None


def build_priority_queue(db: Session, predictions: Dict[str, dict]) -> List[dict]:
    rows = []
    for loc_id, pred in predictions.items():
        if not pred.get("available"):
            continue
        loc = pred["location"]
        risk = pred["risk"]["overall"]
        exposure = pred["risk"]["exposure_score"]
        mom = pred["risk"]["momentum"]
        conf = pred["risk"]["confidence"]["value"]
        if risk < 25:
            continue
        ps = priority_score(risk=risk, exposure=exposure, momentum_rate=mom["rate_per_hour"],
                            confidence=conf)
        rows.append({
            "location_id": loc_id,
            "location_name": loc["name"],
            "location_name_hi": loc.get("name_hi"),
            "district": loc["district"],
            "latitude": loc["latitude"],
            "longitude": loc["longitude"],
            "hazard": pred["hazard"]["dominant"],
            "hazard_label": pred["hazard"]["label"],
            "risk": risk,
            "severity": pred["risk"]["severity"],
            "hazard_score": pred["risk"]["hazard_score"],
            "exposure_score": exposure,
            "exposed_population": loc["population"],
            "momentum": mom,
            "confidence": conf,
            "priority": ps["score"],
            "priority_factors": ps["factors"],
            "peak": pred.get("peak"),
            "decision_window": pred.get("decision_window"),
        })
    rows.sort(key=lambda r: r["priority"], reverse=True)
    for i, r in enumerate(rows, start=1):
        r["rank"] = i
        r["why_priority"] = explain_priority(
            rank=i, risk=r["risk"], exposure_people=r["exposed_population"],
            momentum_label=r["momentum"]["label"], momentum_rate=r["momentum"]["rate_per_hour"],
            confidence=r["confidence"], hazard_label=r["hazard_label"],
            location_name=r["location_name"],
        )
    return rows


def last_sweep() -> dict:
    return _last_sweep


# ---------------------------------------------------------------------------
# Simulation control
# ---------------------------------------------------------------------------
def step(db: Session, *, steps: int = 1, run_alerts: bool = True) -> dict:
    state = get_state(db)
    scenario = get_scenario(state.scenario_id)
    results = []
    for _ in range(max(1, steps)):
        if state.tick >= scenario.total_ticks:
            break
        state.tick += 1
        state.updated_at = utcnow()
        db.commit()
        clear_caches()
        out = refresh_region(db, run_alerts=run_alerts)
        results.append({"tick": state.tick, "summary": out["summary"]})
    bus.publish("simulation_step", {"tick": state.tick, "scenario": state.scenario_id})
    return {
        "tick": state.tick,
        "at_end": state.tick >= scenario.total_ticks,
        "steps_run": len(results),
        "last": results[-1]["summary"] if results else None,
    }


def set_scenario(db: Session, scenario_id: str, *, reset_tick: bool = True) -> dict:
    state = get_state(db)
    scenario = get_scenario(scenario_id)
    state.scenario_id = scenario.id
    if reset_tick:
        state.tick = 0
        state.overrides = {}
    state.updated_at = utcnow()
    db.commit()
    clear_caches()
    bus.publish("scenario_changed", {"scenario": scenario.id, "tick": state.tick})
    return {"scenario_id": scenario.id, "tick": state.tick}


def set_overrides(db: Session, overrides: Dict[str, float]) -> dict:
    """Simulation-lab sliders. A single UI control may expand to several
    features so the physics stays coherent (Section 77)."""
    state = get_state(db)
    expanded = expand_overrides(overrides)
    state.overrides = expanded
    state.updated_at = utcnow()
    db.commit()
    clear_caches()
    bus.publish("overrides_changed", {"overrides": expanded})
    return expanded


SLIDER_EXPANSION = {
    "rainfall": ["rain_intensity", "rain_accumulation_3h"],
    "river_level": ["river_level_ratio", "river_rate"],
    "soil_moisture": ["soil_moisture"],
    "wind": ["wind_speed", "wind_gust"],
    "forecast_intensity": ["forecast_intensity"],
}


def expand_overrides(raw: Dict[str, float]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for key, value in (raw or {}).items():
        try:
            v = float(value)
        except (TypeError, ValueError):
            continue
        v = max(0.0, min(3.0, v))
        if key in SLIDER_EXPANSION:
            for feat in SLIDER_EXPANSION[key]:
                out[feat] = v
        else:
            out[key] = v
    return out


def collapse_overrides(expanded: Dict[str, float]) -> Dict[str, float]:
    """Inverse of expand, for rendering the sliders back in the UI."""
    out: Dict[str, float] = {}
    for slider, feats in SLIDER_EXPANSION.items():
        vals = [expanded.get(f) for f in feats if expanded.get(f) is not None]
        out[slider] = float(vals[0]) if vals else 1.0
    return out


def set_connectivity(db: Session, mode: str) -> dict:
    state = get_state(db)
    if mode not in ("online", "degraded", "offline"):
        raise ValueError("connectivity must be online, degraded or offline")
    state.connectivity = mode
    state.updated_at = utcnow()
    db.commit()
    clear_caches()
    bus.publish("connectivity_changed", {"connectivity": mode})
    return {"connectivity": mode}


def set_failure(db: Session, component: str, enabled: bool) -> dict:
    state = get_state(db)
    ff = dict(state.forced_failures or {})
    if enabled:
        ff[component] = True
    else:
        ff.pop(component, None)
    state.forced_failures = ff
    state.updated_at = utcnow()
    db.commit()
    clear_caches()
    if component == "ml_model":
        from app.riskmodels.registry import model_registry

        model_registry.ml.force_unavailable(enabled)
    bus.publish("failure_changed", {"forced_failures": ff})
    return ff


# ---------------------------------------------------------------------------
# Reset (Section 80)
# ---------------------------------------------------------------------------
def reset_demo(db: Session, *, scenario_id: Optional[str] = None) -> dict:
    """Restore the whole application to a known state. Nothing simulation-
    derived survives; seeded reference data does."""
    from app.db.seed import seed_all

    counts = {}
    for model in (
        AlertAcknowledgement, AlertDelivery, AlertTransition, Alert,
        PredictionVerification, PredictionSnapshot, RiskPrediction,
        EarlySignal, ThreatCell, SystemLog,
    ):
        counts[model.__tablename__] = db.query(model).delete(synchronize_session=False)
    # keep the archived historical incidents, drop simulation-generated ones
    counts["incidents"] = (
        db.query(Incident).filter(Incident.status != "archived").delete(synchronize_session=False)
    )
    db.query(SimulationState).delete(synchronize_session=False)
    db.commit()

    db.add(
        SimulationState(
            id=1,
            scenario_id=scenario_id or "normal_day",
            tick=0,
            running=False,
            speed=1.0,
            overrides={},
            connectivity="online",
            forced_failures={},
        )
    )
    db.commit()

    from app.riskmodels.registry import model_registry

    model_registry.ml.force_unavailable(False)
    model_registry.set_preferred("demo")
    clear_caches()
    seed_all(db)
    log_event(db, level="info", component="orchestrator", event="demo_reset",
              message="Demo state reset to a known baseline.", context=counts, commit=True)
    bus.publish("demo_reset", {"scenario": scenario_id or "normal_day"})
    return {"cleared": counts, "scenario_id": scenario_id or "normal_day", "tick": 0}


# ---------------------------------------------------------------------------
# What-if lab (Section 44)
# ---------------------------------------------------------------------------
def what_if(db: Session, location: Location, overrides: Dict[str, float]) -> dict:
    """Recompute risk under hypothetical inputs WITHOUT persisting anything,
    and attribute the change to individual factors."""
    base_ctx = build_context(db)
    baseline = compute_prediction(db, location, ctx=base_ctx, detail=True, persist=False)
    if not baseline.get("available"):
        return {"available": False, "reason": baseline.get("detail")}

    expanded = expand_overrides(overrides)
    merged = {**(base_ctx.overrides or {}), **expanded}
    ctx = build_context(db, overrides_extra=merged)
    modified = compute_prediction(db, location, ctx=ctx, detail=True, persist=False)

    # one-factor-at-a-time attribution: which slider moved the answer most?
    attribution = []
    for slider, value in (overrides or {}).items():
        single = expand_overrides({slider: value})
        ctx_single = build_context(db, overrides_extra={**(base_ctx.overrides or {}), **single})
        one = compute_prediction(db, location, ctx=ctx_single, detail=False, persist=False)
        if one.get("available"):
            delta = one["risk"]["overall"] - baseline["risk"]["overall"]
            attribution.append({
                "factor": slider,
                "value": value,
                "risk": one["risk"]["overall"],
                "delta": round(delta, 1),
                "abs_delta": round(abs(delta), 1),
            })
    attribution.sort(key=lambda a: a["abs_delta"], reverse=True)

    alert_level = None
    from app.alerts.engine import evaluate_triggers

    trig = evaluate_triggers(
        risk=modified["risk"]["overall"],
        momentum_rate=modified["risk"]["momentum"]["rate_per_hour"],
        confidence=modified["risk"]["confidence"]["value"],
        prediction=modified,
    )
    alert_level = trig.level if trig.should_alert else None

    return {
        "available": True,
        "location": baseline["location"],
        "baseline": _whatif_slice(baseline),
        "modified": _whatif_slice(modified),
        "delta": {
            "risk": round(modified["risk"]["overall"] - baseline["risk"]["overall"], 1),
            "hazard": round(modified["risk"]["hazard_score"] - baseline["risk"]["hazard_score"], 1),
            "exposure": round(modified["risk"]["exposure_score"] - baseline["risk"]["exposure_score"], 1),
            "confidence": round(
                modified["risk"]["confidence"]["value"] - baseline["risk"]["confidence"]["value"], 1
            ),
        },
        "attribution": attribution,
        "most_influential": attribution[0] if attribution else None,
        "expected_alert_level": alert_level,
        "expected_alert_reason": trig.reasons,
        "overrides": overrides,
        "note": "What-if results are not persisted and never create alerts.",
    }


def _whatif_slice(pred: dict) -> dict:
    return {
        "risk": pred["risk"]["overall"],
        "hazard": pred["risk"]["hazard_score"],
        "exposure": pred["risk"]["exposure_score"],
        "severity": pred["risk"]["severity"],
        "confidence": pred["risk"]["confidence"]["value"],
        "uncertainty": pred["risk"]["uncertainty"],
        "contributors": pred.get("contributors", [])[:6],
        "explanation": pred.get("explanation", [])[:5],
    }


# ---------------------------------------------------------------------------
# Event replay + verification (Sections 41, 43)
# ---------------------------------------------------------------------------
def replay_scenario(
    db: Session, *, scenario_id: str, location_id: Optional[str] = None,
    persist: bool = False,
) -> dict:
    """Run a scenario end-to-end and return the full frame-by-frame history.

    Used by the Event Replay screen and by the verification service. It does
    not disturb the live simulation state.
    """
    state = get_state(db)
    saved = (state.scenario_id, state.tick, dict(state.overrides or {}), state.connectivity)
    scenario = get_scenario(scenario_id)
    focus_id = location_id or scenario.focus_location_id
    location = db.get(Location, focus_id) or all_locations(db)[0]

    frames = []
    try:
        state.scenario_id = scenario.id
        state.overrides = {}
        state.connectivity = "online"
        for tick in range(0, scenario.total_ticks + 1):
            state.tick = tick
            db.commit()
            clear_caches()
            ctx = build_context(db)
            pred = compute_prediction(db, location, ctx=ctx, detail=True, persist=persist)
            if not pred.get("available"):
                frames.append({"tick": tick, "available": False, "reason": pred.get("detail")})
                continue
            frames.append({
                "tick": tick,
                "available": True,
                "offset_minutes": tick * scenario.tick_minutes,
                "clock": _relative_clock(tick, scenario),
                "risk": pred["risk"]["overall"],
                "hazard_score": pred["risk"]["hazard_score"],
                "exposure_score": pred["risk"]["exposure_score"],
                "severity": pred["risk"]["severity"],
                "confidence": pred["risk"]["confidence"]["value"],
                "uncertainty": pred["risk"]["uncertainty"],
                "momentum": pred["risk"]["momentum"],
                "early_signals": pred.get("early_signals", []),
                "explanation": pred.get("explanation", [])[:4],
                "contributors": pred.get("contributors", [])[:6],
                "inputs": {
                    k: {"value": v["value"], "unit": v["unit"], "freshness": v["freshness"]}
                    for k, v in pred["inputs"].items()
                },
                "peak": pred.get("peak"),
                "decision_window": pred.get("decision_window"),
                "data_health": pred["data_health"]["score"],
                "alert_level": _implied_alert_level(pred),
            })
    finally:
        state.scenario_id, state.tick, state.overrides, state.connectivity = saved
        db.commit()
        clear_caches()

    ok = [f for f in frames if f.get("available")]
    peak_frame = max(ok, key=lambda f: f["risk"]) if ok else None
    first_warn = next((f for f in ok if f["risk"] >= ALERTS["thresholds"]["WARNING"]), None)
    lead_seconds = None
    if peak_frame and first_warn and peak_frame["tick"] > first_warn["tick"]:
        lead_seconds = (peak_frame["tick"] - first_warn["tick"]) * scenario.tick_minutes * 60

    return {
        "scenario": scenario.as_dict(),
        "location": {"id": location.id, "name": location.name},
        "frames": frames,
        "peak": {"tick": peak_frame["tick"], "risk": peak_frame["risk"]} if peak_frame else None,
        "first_warning": {"tick": first_warn["tick"], "risk": first_warn["risk"]} if first_warn else None,
        "lead_time_seconds": lead_seconds,
        "lead_time_note": (
            "Measured on the simulated event timeline: interval between the first WARNING-level "
            "risk and the observed peak."
        ),
        "story": _replay_story(frames, scenario),
    }


def _relative_clock(tick: int, scenario) -> str:
    peak = scenario.expected_peak_tick
    if peak is None:
        return f"T+{tick * scenario.tick_minutes // 60}h{tick * scenario.tick_minutes % 60:02d}"
    delta = (tick - peak) * scenario.tick_minutes
    sign = "+" if delta >= 0 else "-"
    a = abs(delta)
    return f"T{sign}{a // 60}h{a % 60:02d}m" if a >= 60 else f"T{sign}{a}m"


def _implied_alert_level(pred: dict) -> Optional[str]:
    from app.alerts.engine import level_for_risk

    return level_for_risk(pred["risk"]["overall"])


def _replay_story(frames: List[dict], scenario) -> List[dict]:
    """Human-readable narrative of the replay (Section 69)."""
    story: List[dict] = []
    prev_level = None
    seen_signals: set[str] = set()
    for f in frames:
        if not f.get("available"):
            continue
        clock = f["clock"]
        for s in f.get("early_signals", []):
            if s["kind"] in seen_signals:
                continue
            seen_signals.add(s["kind"])
            story.append({"clock": clock, "tick": f["tick"], "kind": "early_signal",
                          "text": f"{s['label']} — {s['detail']}"})
        level = f["severity"]["key"]
        if level != prev_level:
            story.append({"clock": clock, "tick": f["tick"], "kind": "severity_change",
                          "text": f"Risk moved to {level} ({f['risk']:.0f}/100), "
                                  f"confidence {f['confidence']:.0f}%."})
            prev_level = level
        if f.get("alert_level") and f["tick"] > 0:
            prev = frames[f["tick"] - 1] if f["tick"] - 1 < len(frames) else None
            if prev and prev.get("alert_level") != f["alert_level"]:
                story.append({"clock": clock, "tick": f["tick"], "kind": "alert",
                              "text": f"Alert level {f['alert_level']} recommended."})
    ok = [f for f in frames if f.get("available")]
    if ok:
        peak = max(ok, key=lambda x: x["risk"])
        story.append({"clock": peak["clock"], "tick": peak["tick"], "kind": "peak",
                      "text": f"Risk peaked at {peak['risk']:.0f}/100."})
        last = ok[-1]
        story.append({"clock": last["clock"], "tick": last["tick"], "kind": "resolution",
                      "text": f"By the end of the scenario risk had fallen to {last['risk']:.0f}/100."})
    story.sort(key=lambda s: (s["tick"], s["kind"] != "early_signal"))
    return story


def verify_predictions(db: Session, *, scenario_id: str, location_id: Optional[str] = None) -> dict:
    """Compare what PEHRA predicted at t against what the scenario actually did.

    The 'actual' is the risk the engine computes from the observations that
    genuinely arrived later in the same simulated event. This is a real
    measurement of the forecast, on simulated ground truth -- and it is
    labelled as such everywhere.
    """
    replay = replay_scenario(db, scenario_id=scenario_id, location_id=location_id, persist=False)
    frames = [f for f in replay["frames"] if f.get("available")]
    if len(frames) < 4:
        return {"available": False, "reason": "Not enough frames to evaluate."}

    scenario = get_scenario(scenario_id)
    loc_id = replay["location"]["id"]
    by_tick = {f["tick"]: f for f in frames}

    # rebuild the timeline predictions for each frame
    state = get_state(db)
    saved = (state.scenario_id, state.tick)
    records = []
    try:
        state.scenario_id = scenario.id
        location = db.get(Location, loc_id)
        for f in frames:
            state.tick = f["tick"]
            db.commit()
            clear_caches()
            ctx = build_context(db)
            pred = compute_prediction(db, location, ctx=ctx, detail=True, persist=False)
            if not pred.get("available"):
                continue
            for entry in pred.get("timeline", []):
                if not entry.get("available") or entry["horizon_minutes"] == 0:
                    continue
                target_tick = f["tick"] + int(entry["horizon_minutes"] / scenario.tick_minutes)
                actual_frame = by_tick.get(target_tick)
                if not actual_frame:
                    continue
                records.append({
                    "issued_tick": f["tick"],
                    "target_tick": target_tick,
                    "horizon_minutes": entry["horizon_minutes"],
                    "predicted": entry["risk"],
                    "actual": actual_frame["risk"],
                    "confidence": entry["confidence"],
                })
    finally:
        state.scenario_id, state.tick = saved
        db.commit()
        clear_caches()

    # classify and persist
    db.query(PredictionVerification).filter(
        PredictionVerification.location_id == loc_id,
        PredictionVerification.source == f"replay:{scenario_id}",
    ).delete(synchronize_session=False)

    tol = VERIFICATION["correct_tolerance"]
    ev_t = VERIFICATION["event_threshold"]
    pr_t = VERIFICATION["predicted_threshold"]
    counts = {"CORRECT": 0, "UNDERPREDICTED": 0, "OVERPREDICTED": 0,
              "FALSE_POSITIVE": 0, "MISSED_EVENT": 0}
    tp = fp = fn = tn = 0
    errors = []
    from app.riskmodels.registry import model_registry

    active = model_registry.get(model_registry.preferred)

    for r in records:
        p, a = r["predicted"], r["actual"]
        err = p - a
        errors.append(err)
        pos_pred, pos_actual = p >= pr_t, a >= ev_t
        if pos_pred and pos_actual:
            tp += 1
            outcome = "CORRECT" if abs(err) <= tol else ("OVERPREDICTED" if err > 0 else "UNDERPREDICTED")
        elif pos_pred and not pos_actual:
            fp += 1
            outcome = "FALSE_POSITIVE"
        elif not pos_pred and pos_actual:
            fn += 1
            outcome = "MISSED_EVENT"
        else:
            tn += 1
            outcome = "CORRECT" if abs(err) <= tol else ("OVERPREDICTED" if err > 0 else "UNDERPREDICTED")
        counts[outcome] = counts.get(outcome, 0) + 1
        db.add(PredictionVerification(
            prediction_id=None,
            location_id=loc_id,
            predicted_risk=round(p, 2),
            actual_risk=round(a, 2),
            actual_event_occurred=pos_actual,
            outcome=outcome,
            horizon_minutes=r["horizon_minutes"],
            error=round(err, 2),
            lead_time_seconds=replay.get("lead_time_seconds"),
            model_name=active.name,
            model_version=active.version,
            source=f"replay:{scenario_id}",
        ))
    db.commit()

    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    f1 = (2 * precision * recall / (precision + recall)) if (precision and recall) else None
    mae = sum(abs(e) for e in errors) / len(errors) if errors else None
    bias = sum(errors) / len(errors) if errors else None

    log_event(db, level="info", component="analytics", event="verification_run",
              message=f"Verified {len(records)} predictions for {scenario_id}",
              context={"tp": tp, "fp": fp, "fn": fn, "tn": tn}, commit=True)

    return {
        "available": True,
        "scenario_id": scenario_id,
        "location": replay["location"],
        "sample_size": len(records),
        "confusion": {"true_positive": tp, "false_positive": fp,
                      "false_negative": fn, "true_negative": tn},
        "outcomes": counts,
        "metrics": {
            "precision": round(precision, 3) if precision is not None else None,
            "recall": round(recall, 3) if recall is not None else None,
            "f1": round(f1, 3) if f1 is not None else None,
            "false_positive_rate": round(fp / (fp + tn), 3) if (fp + tn) else None,
            "false_negative_rate": round(fn / (fn + tp), 3) if (fn + tp) else None,
            "mae": round(mae, 2) if mae is not None else None,
            "bias": round(bias, 2) if bias is not None else None,
            "lead_time_seconds": replay.get("lead_time_seconds"),
        },
        "by_horizon": _metrics_by_horizon(records, tol),
        "caveat": (
            "Measured by replaying a DETERMINISTIC SIMULATED scenario and comparing each "
            "forecast against the risk the engine later computed from the observations that "
            "actually arrived. This is a genuine measurement of forecast consistency on "
            "simulated ground truth — it is NOT real-world disaster-prediction accuracy."
        ),
    }


def _metrics_by_horizon(records: List[dict], tol: float) -> List[dict]:
    out: Dict[int, List[dict]] = {}
    for r in records:
        out.setdefault(r["horizon_minutes"], []).append(r)
    rows = []
    for h, rs in sorted(out.items()):
        errs = [r["predicted"] - r["actual"] for r in rs]
        rows.append({
            "horizon_minutes": h,
            "count": len(rs),
            "mae": round(sum(abs(e) for e in errs) / len(errs), 2),
            "bias": round(sum(errs) / len(errs), 2),
            "within_tolerance_pct": round(
                100.0 * sum(1 for e in errs if abs(e) <= tol) / len(errs), 1
            ),
        })
    return rows
