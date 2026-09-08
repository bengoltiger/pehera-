"""Prediction service -- the OBSERVE → UNDERSTAND → PREDICT → EXPLAIN chain.

This is the only place a risk number is created. The API and the UI merely
render what this module returns (Sections 95, 96).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
from typing import Dict, List, Optional, Tuple

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.risk_config import (
    ALERTS,
    DEFAULT_HORIZONS_MIN,
    HAZARDS,
    THREAT_CELLS,
)
from app.db.models import Infrastructure, Location, PredictionSnapshot, RiskPrediction
from app.engine.confidence import compute_confidence, compute_uncertainty
from app.engine.features import FeatureBundle, assemble_features, human_age
from app.engine.normalise import label_for, normalise
from app.engine.risk_engine import combine_overall, momentum, severity_label
from app.providers.base import ProviderContext
from app.riskmodels.base import HorizonInputs, ModelUnavailable
from app.riskmodels.registry import model_registry
from app.services.clock import build_context, get_state
from app.services.observability import log_event
from app.simulation.nowcast_error import degrade_field
from app.simulation.scenarios import get_scenario, scenario_field_at

# ---------------------------------------------------------------------------
# small in-process caches (Section 99)
# ---------------------------------------------------------------------------
_feature_cache: Dict[str, Tuple[float, FeatureBundle]] = {}
_infra_cache: Dict[str, int] = {}
_CACHE_TTL = 20.0  # seconds


def _ctx_signature(ctx: ProviderContext) -> str:
    payload = json.dumps(
        {
            "s": ctx.scenario_id,
            "t": ctx.tick,
            "o": ctx.overrides,
            "c": ctx.connectivity,
            "f": ctx.forced_failures,
        },
        sort_keys=True,
    )
    return hashlib.md5(payload.encode()).hexdigest()[:12]


def clear_caches() -> None:
    _feature_cache.clear()
    _infra_cache.clear()


def critical_facility_count(db: Session, location_id: str) -> int:
    if location_id in _infra_cache:
        return _infra_cache[location_id]
    n = (
        db.query(Infrastructure)
        .filter(Infrastructure.location_id == location_id, Infrastructure.criticality >= 0.7)
        .count()
    )
    _infra_cache[location_id] = n
    return n


def get_feature_bundle(db: Session, location: Location, ctx: ProviderContext) -> FeatureBundle:
    key = f"{location.id}:{_ctx_signature(ctx)}"
    hit = _feature_cache.get(key)
    now_mono = dt.datetime.now().timestamp()
    if hit and now_mono - hit[0] < _CACHE_TTL:
        return hit[1]
    bundle = assemble_features(location, ctx)
    _feature_cache[key] = (now_mono, bundle)
    if len(_feature_cache) > 400:
        for k in list(_feature_cache)[:150]:
            _feature_cache.pop(k, None)
    return bundle


# ---------------------------------------------------------------------------
# Forecast-driven future feature vectors
# ---------------------------------------------------------------------------
STATIC_FEATURES = ("terrain_vulnerability", "drainage_deficiency", "population_density",
                   "historical_similarity", "elevation_m")


def _future_norm_at_tick(
    location: Location, ctx: ProviderContext, tick: float, present: FeatureBundle
) -> Tuple[Dict[str, Optional[float]], Dict[str, Optional[float]]]:
    """Feature vector the forecast feed implies for a given tick.

    For ticks in the future this is a *nowcast*, not the scenario's ground
    truth: it is passed through the skill-decay model in
    ``app.simulation.nowcast_error`` so that projections lag, spread and can be
    wrong — which is what makes the verification numbers real. Past and present
    ticks are returned undegraded, because those conditions were observed.
    """
    scenario = get_scenario(ctx.scenario_id)
    field = scenario_field_at(scenario, int(round(tick)), location.latitude, location.longitude)
    overrides = ctx.overrides or {}
    raw: Dict[str, Optional[float]] = {}
    for feat in (
        "rain_intensity", "rain_accumulation_3h", "river_level_ratio", "river_rate",
        "soil_moisture", "wind_speed", "wind_gust", "forecast_rain_3h",
        "cloud_top_temp_k", "lightning_rate", "temperature_c", "humidity", "pressure_hpa",
    ):
        val = field.get(feat)
        if val is not None and feat in overrides:
            val = float(val) * float(overrides[feat])
        if val is not None and feat == "forecast_rain_3h" and "forecast_intensity" in overrides:
            val = float(val) * float(overrides["forecast_intensity"])
        raw[feat] = val
    # derived acceleration
    prev = scenario_field_at(scenario, max(0, int(round(tick)) - 1), location.latitude, location.longitude)
    pi, ci = prev.get("rain_intensity"), field.get("rain_intensity")
    if pi is not None and ci is not None:
        if "rain_intensity" in overrides:
            pi *= float(overrides["rain_intensity"])
            ci *= float(overrides["rain_intensity"])
        raw["rain_acceleration"] = (ci - pi) * (60.0 / max(scenario.tick_minutes, 1))
    else:
        raw["rain_acceleration"] = None
    # statics persist
    for feat in STATIC_FEATURES:
        raw[feat] = present.value(feat)
    # if a feature is unavailable now because the gauge is down, it stays
    # unavailable in the projection -- we must not invent it
    for feat, fv in present.features.items():
        if not fv.usable and fv.unavailable_reason and "No river gauge" in (fv.unavailable_reason or ""):
            raw[feat] = None
    horizon_minutes = (int(round(tick)) - ctx.tick) * scenario.tick_minutes
    if horizon_minutes > 0:
        present_raw = present.raw_dict()
        raw = degrade_field(
            raw, present_raw,
            horizon_minutes=horizon_minutes,
            key=(scenario.id, location.id, ctx.tick),
        )
    norm = {k: normalise(k, v) for k, v in raw.items()}
    return norm, raw


def build_horizon_inputs(
    location: Location, ctx: ProviderContext, bundle: FeatureBundle, horizons: List[int]
) -> HorizonInputs:
    scenario = get_scenario(ctx.scenario_id)
    future: Dict[int, Dict[str, Optional[float]]] = {}
    future_raw: Dict[int, Dict[str, Optional[float]]] = {}
    for h in horizons:
        if h <= 0:
            continue
        tick = ctx.tick + h / scenario.tick_minutes
        n, r = _future_norm_at_tick(location, ctx, tick, bundle)
        future[h] = n
        future_raw[h] = r
    units = {k: v.unit for k, v in bundle.features.items()}
    return HorizonInputs(
        present=bundle.norm_dict(),
        present_raw=bundle.raw_dict(),
        future=future,
        future_raw=future_raw,
        units=units,
    )


def hazards_for(location: Location) -> List[str]:
    hz = [h for h in (location.primary_hazards or []) if h in HAZARDS]
    return hz or ["flood"]


# ---------------------------------------------------------------------------
# Cheap risk evaluation at an arbitrary tick (used for momentum/peak scans)
# ---------------------------------------------------------------------------
def risk_at_tick(
    db: Session, location: Location, ctx: ProviderContext, tick: int, bundle: FeatureBundle
) -> float:
    from app.engine.risk_engine import compute_compound, score_exposure, score_hazard

    norm, raw = _future_norm_at_tick(location, ctx, tick, bundle)
    results = [score_hazard(h, norm, raw) for h in hazards_for(location)]
    comp = compute_compound(results)
    expo = score_exposure(location, critical_facility_count(db, location.id))
    return combine_overall(comp.compound_severity, expo.score)


# ---------------------------------------------------------------------------
# Early signals (Section 70)
# ---------------------------------------------------------------------------
def detect_early_signals(
    db: Session, location: Location, ctx: ProviderContext, bundle: FeatureBundle, current_risk: float
) -> List[dict]:
    scenario = get_scenario(ctx.scenario_id)
    signals: List[dict] = []
    t = ctx.tick

    def f(tick: int, key: str) -> Optional[float]:
        if tick < 0:
            return None
        v = scenario_field_at(scenario, tick, location.latitude, location.longitude).get(key)
        if v is not None and key in (ctx.overrides or {}):
            v = float(v) * float(ctx.overrides[key])
        return v

    # 1. rainfall acceleration
    r0, r1, r2 = f(t, "rain_intensity"), f(t - 1, "rain_intensity"), f(t - 2, "rain_intensity")
    if None not in (r0, r1, r2):
        d1, d2 = r0 - r1, r1 - r2  # type: ignore[operator]
        if d1 > 2.0 and d1 > d2:
            signals.append({
                "kind": "rainfall_acceleration",
                "label": "Rainfall acceleration detected",
                "detail": (
                    f"Intensity rose {r2:.0f} → {r1:.0f} → {r0:.0f} mm/h over the last "
                    f"{2 * scenario.tick_minutes} minutes; the rate of increase is itself increasing."
                ),
                "magnitude": round(d1 - d2, 2),
                "lead_indicator": True,
            })

    # 2. river trend reversal (falling/flat -> rising)
    v0, v1, v2 = f(t, "river_rate"), f(t - 1, "river_rate"), f(t - 2, "river_rate")
    if None not in (v0, v1, v2) and getattr(location, "river_id", None):
        if v0 > 0.05 and v0 > v1 > v2:  # type: ignore[operator]
            signals.append({
                "kind": "river_trend_reversal",
                "label": "Water-level trend turning upward",
                "detail": (
                    f"River rise rate moved {v2:+.2f} → {v1:+.2f} → {v0:+.2f} m/h. "
                    "Sustained acceleration of the gauge is the classic precursor to a flood peak."
                ),
                "magnitude": round(float(v0), 3),
                "lead_indicator": True,
            })

    # 3. forecast convergence: successive forecast issues agree and increase
    fa = bundle.forecast_agreement()
    fc_now = bundle.forecast_value("forecast_rain_3h", 180)
    fc_obs = bundle.value("rain_accumulation_3h")
    if fa is not None and fa > 0.7 and fc_now and fc_obs is not None and fc_now > fc_obs * 1.15:
        signals.append({
            "kind": "forecast_convergence",
            "label": "Forecast convergence detected",
            "detail": (
                f"Forecast members agree at {fa * 100:.0f}% and project {fc_now:.0f} mm in the next "
                f"3 hours against {fc_obs:.0f} mm observed in the last 3 — the models are converging on more rain."
            ),
            "magnitude": round(float(fa), 3),
            "lead_indicator": True,
        })

    # 4. soil saturation threshold crossing
    sm0, sm1 = f(t, "soil_moisture"), f(t - 1, "soil_moisture")
    if None not in (sm0, sm1) and sm1 < 0.40 <= sm0:  # type: ignore[operator]
        signals.append({
            "kind": "soil_saturation_crossing",
            "label": "Soil saturation crossed the configured threshold",
            "detail": (
                f"Soil moisture crossed 0.40 m³/m³ (now {sm0:.2f}). Additional rainfall now runs off "
                "instead of infiltrating, which sharply raises flood response."
            ),
            "magnitude": round(float(sm0), 3),
            "lead_indicator": True,
        })

    # 5. pressure fall
    p0, p2 = f(t, "pressure_hpa"), f(t - 2, "pressure_hpa")
    if None not in (p0, p2) and (p2 - p0) >= 3.0:  # type: ignore[operator]
        signals.append({
            "kind": "pressure_fall",
            "label": "Rapid pressure fall detected",
            "detail": f"Surface pressure fell {p2 - p0:.1f} hPa in {2 * scenario.tick_minutes} minutes — a deepening system.",
            "magnitude": round(float(p2 - p0), 2),
            "lead_indicator": True,
        })

    # 6. convective deepening from satellite
    c0, c2 = f(t, "cloud_top_temp_k"), f(t - 2, "cloud_top_temp_k")
    if None not in (c0, c2) and (c2 - c0) >= 8.0 and c0 < 235:  # type: ignore[operator]
        signals.append({
            "kind": "convective_deepening",
            "label": "Convective deepening detected",
            "detail": f"Cloud-top temperature fell {c2 - c0:.0f} K to {c0:.0f} K — the storm is growing vertically.",
            "magnitude": round(float(c2 - c0), 2),
            "lead_indicator": True,
        })

    for s in signals:
        s["risk_at_detection"] = round(current_risk, 1)
        s["detected_at"] = ctx.now.isoformat() + "Z"
    return signals


# ---------------------------------------------------------------------------
# Peak / decision window / lead time (Sections 19, 72, 73)
# ---------------------------------------------------------------------------
def forward_scan(
    db: Session, location: Location, ctx: ProviderContext, bundle: FeatureBundle, horizon_minutes: int = 360
) -> List[dict]:
    scenario = get_scenario(ctx.scenario_id)
    steps = int(horizon_minutes / scenario.tick_minutes)
    out = []
    for i in range(0, steps + 1):
        tick = ctx.tick + i
        risk = risk_at_tick(db, location, ctx, tick, bundle) if i > 0 else None
        out.append({"offset_minutes": i * scenario.tick_minutes, "tick": tick, "risk": risk})
    return out


def peak_and_windows(
    db: Session,
    location: Location,
    ctx: ProviderContext,
    bundle: FeatureBundle,
    current_risk: float,
    confidence: float,
) -> dict:
    scenario = get_scenario(ctx.scenario_id)
    scan = forward_scan(db, location, ctx, bundle)
    scan[0]["risk"] = current_risk

    risks = [(s["offset_minutes"], s["risk"]) for s in scan if s["risk"] is not None]
    peak_offset, peak_risk = max(risks, key=lambda kv: kv[1]) if risks else (0, current_risk)

    # A peak estimate is only meaningful if the trajectory actually has a shape
    # and confidence is not in the floor. Otherwise say so (Section 72).
    spread = max(r for _, r in risks) - min(r for _, r in risks) if risks else 0.0
    peak_available = spread >= 4.0 and confidence >= 35.0 and peak_offset > 0

    crit_threshold = ALERTS["thresholds"]["CRITICAL"]
    decision_minutes = None
    for offset, r in risks:
        if offset > 0 and r >= crit_threshold:
            decision_minutes = offset
            break
    already_critical = current_risk >= crit_threshold

    # backward scan for lead time: when did the engine first see WARNING?
    warn_threshold = ALERTS["thresholds"]["WARNING"]
    first_warn_offset = None
    for back in range(0, ctx.tick + 1):
        tick = ctx.tick - back
        r = risk_at_tick(db, location, ctx, tick, bundle) if back > 0 else current_risk
        if r >= warn_threshold:
            first_warn_offset = back * scenario.tick_minutes
        else:
            if first_warn_offset is not None:
                break
    lead_time_seconds = None
    if first_warn_offset is not None and peak_available:
        lead_time_seconds = int((first_warn_offset + peak_offset) * 60)

    return {
        "peak": {
            "available": peak_available,
            "risk": round(peak_risk, 1) if peak_available else None,
            "in_minutes": peak_offset if peak_available else None,
            "at": (ctx.now + dt.timedelta(minutes=peak_offset)).isoformat() + "Z" if peak_available else None,
            "label": "MODEL ESTIMATE",
            "reason_unavailable": None
            if peak_available
            else (
                "Peak timing unavailable — the projected trajectory is flat, so no meaningful "
                "peak can be identified."
                if spread < 4.0
                else (
                    "Peak timing unavailable — confidence is too low to time a peak."
                    if confidence < 35.0
                    else "Risk is already at its projected maximum: the peak is now, and "
                         "conditions are projected to ease from here."
                )
            ),
            "at_peak_now": bool(peak_offset == 0 and spread >= 4.0 and confidence >= 35.0),
        },
        "decision_window": {
            "available": decision_minutes is not None or already_critical,
            "minutes": 0 if already_critical else decision_minutes,
            "threshold": crit_threshold,
            "already_critical": already_critical,
            "label": "Estimated time before risk crosses the CRITICAL threshold",
            "reason_unavailable": None
            if (decision_minutes is not None or already_critical)
            else f"Risk is not projected to reach {crit_threshold:.0f} within the next 6 hours.",
        },
        "lead_time": {
            "available": lead_time_seconds is not None,
            "seconds": lead_time_seconds,
            "label": _fmt_duration(lead_time_seconds) if lead_time_seconds else None,
            "explanation": (
                "PEHRA's risk trajectory crossed the WARNING threshold "
                f"{_fmt_duration(first_warn_offset * 60)} before now, and the peak is projected "
                f"{_fmt_duration(peak_offset * 60)} from now. Measured on the simulated event timeline."
                if lead_time_seconds
                else "Lead time is measured once the engine crosses the WARNING threshold and a peak can be projected."
            ),
        },
        "trajectory": [{"offset_minutes": o, "risk": round(r, 1)} for o, r in risks],
    }


def _fmt_duration(seconds: Optional[int]) -> str:
    if seconds is None:
        return "—"
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}h {m:02d}m"
    return f"{m}m {sec:02d}s"


# ---------------------------------------------------------------------------
# Explanation (Section 12)
# ---------------------------------------------------------------------------
def build_explanation(
    hazard_result, bundle: FeatureBundle, severity: dict, momentum_info: dict, compound
) -> List[dict]:
    lines: List[dict] = []
    for c in hazard_result.contributions[:6]:
        fv = bundle.features.get(c.feature)
        raw = c.raw_value
        unit = fv.unit if fv else ""
        if raw is None:
            continue
        # describe the value in plain terms
        pct = c.share * 100
        if c.feature == "rain_intensity":
            text = f"Rainfall intensity is {raw:.0f} {unit}."
        elif c.feature == "rain_accumulation_3h":
            text = f"{raw:.0f} mm of rain has already fallen in the last 3 hours."
        elif c.feature == "rain_acceleration":
            text = (
                f"Rainfall is intensifying at {raw:+.0f} mm/h per hour."
                if raw > 0
                else f"Rainfall is easing at {raw:+.0f} mm/h per hour."
            )
        elif c.feature == "river_level_ratio":
            text = f"River level is at {raw * 100:.0f}% of its danger level."
        elif c.feature == "river_rate":
            text = (
                f"River level is rising at {raw:+.2f} m/h."
                if raw > 0
                else f"River level is falling at {raw:+.2f} m/h."
            )
        elif c.feature == "soil_moisture":
            text = f"Soil is {raw / 0.52 * 100:.0f}% saturated ({raw:.2f} m³/m³), so new rain runs off."
        elif c.feature == "terrain_vulnerability":
            text = f"The terrain here scores {raw:.2f}/1.00 for flood vulnerability (low-lying ground)."
        elif c.feature == "drainage_deficiency":
            text = f"Drainage capacity is deficient here ({raw:.2f}/1.00)."
        elif c.feature == "forecast_rain_3h":
            text = f"Forecast models indicate {raw:.0f} mm more rain in the next 3 hours."
        elif c.feature == "wind_gust":
            text = f"Wind gusts are reaching {raw:.0f} km/h."
        elif c.feature == "wind_speed":
            text = f"Sustained wind is {raw:.0f} km/h."
        elif c.feature == "lightning_rate":
            text = f"Lightning activity is {raw:.0f} strikes per 15 minutes."
        elif c.feature == "cloud_top_temp_k":
            text = f"Cloud tops are at {raw:.0f} K, indicating deep convection."
        elif c.feature == "temperature_c":
            text = f"Temperature is {raw:.0f} °C."
        elif c.feature == "humidity":
            text = f"Humidity is {raw:.0f}%."
        elif c.feature == "population_density":
            text = f"Population density is about {raw:,.0f} people/km²."
        else:
            text = f"{c.label} is {raw:.2f} {unit}".strip() + "."
        lines.append(
            {
                "rank": len(lines) + 1,
                "feature": c.feature,
                "label": c.label,
                "text": text,
                "percent": round(pct, 1),
                "points": round(c.points, 2),
                "component": c.component,
                "source": fv.source if fv else "",
                "freshness": fv.freshness if fv else "missing",
                "age_human": human_age(fv.age_seconds) if fv and fv.age_seconds is not None else "—",
            }
        )
    return lines


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def compute_prediction(
    db: Session,
    location: Location,
    *,
    ctx: Optional[ProviderContext] = None,
    detail: bool = True,
    persist: bool = True,
    preferred_model: Optional[str] = None,
    lang: str = "en",
) -> dict:
    ctx = ctx or build_context(db)
    scenario = get_scenario(ctx.scenario_id)
    bundle = get_feature_bundle(db, location, ctx)
    hz_list = hazards_for(location)
    horizons = DEFAULT_HORIZONS_MIN
    inputs = build_horizon_inputs(location, ctx, bundle, horizons)
    n_facilities = critical_facility_count(db, location.id)

    # ---- run the model chain (Section 64) ----
    try:
        pred, used_fallback, attempts = model_registry.predict_with_fallback(
            preferred=preferred_model,
            location=location,
            inputs=inputs,
            hazards=hz_list,
            critical_facilities=n_facilities,
            horizon_minutes=0,
        )
    except ModelUnavailable as exc:
        log_event(
            db, level="error", component="prediction", event="model_chain_failed",
            message=str(exc), context={"location": location.id}, commit=True,
        )
        return {
            "available": False,
            "location": _location_dict(location),
            "reason": "Prediction unavailable",
            "detail": str(exc),
            "data_health": bundle.data_health.to_dict(),
            "generated_at": ctx.now.isoformat() + "Z",
        }

    dominant = next(
        (r for r in pred.hazard_results if r.hazard == pred.dominant_hazard), None
    ) or (pred.hazard_results[0] if pred.hazard_results else None)

    if dominant is None or not dominant.is_computable:
        reason = (
            dominant.reason_uncomputable
            if dominant
            else "No hazard model could be evaluated for this location."
        )
        missing = bundle.data_health.missing_features
        return {
            "available": False,
            "location": _location_dict(location),
            "reason": "Prediction unavailable",
            "detail": reason,
            "missing_inputs": missing,
            "data_health": bundle.data_health.to_dict(),
            "generated_at": ctx.now.isoformat() + "Z",
        }

    # ---- confidence & uncertainty ----
    missing_required = sorted({m for r in pred.hazard_results for m in r.missing_required})
    conf = compute_confidence(
        data_health_score=bundle.data_health.score,
        model_confidence=pred.model_confidence,
        forecast_agreement=bundle.forecast_agreement(),
        historical_support=bundle.value("historical_similarity"),
        missing_required=[label_for(m) for m in missing_required],
        stale_features=[label_for(s) for s in bundle.data_health.stale_features],
        is_fallback=used_fallback,
        connectivity=ctx.connectivity,
    )
    unc = compute_uncertainty(pred.overall_risk, conf.value, 0)

    # ---- momentum vs the engine's own output one tick earlier ----
    prev_risk = risk_at_tick(db, location, ctx, max(0, ctx.tick - 1), bundle) if ctx.tick > 0 else None
    mom = momentum(prev_risk, pred.overall_risk, scenario.tick_minutes if prev_risk is not None else 0)

    sev = severity_label(pred.overall_risk)
    result: dict = {
        "available": True,
        "location": _location_dict(location),
        "generated_at": ctx.now.isoformat() + "Z",
        "scenario": {"id": scenario.id, "name": scenario.name, "tick": ctx.tick,
                     "tick_minutes": scenario.tick_minutes},
        "risk": {
            "overall": round(pred.overall_risk, 1),
            "hazard_score": round(pred.severity_index, 1),
            "exposure_score": round(pred.exposure.score, 1),
            "severity": sev,
            "confidence": conf.to_dict(),
            "uncertainty": unc.to_dict(),
            "momentum": mom,
        },
        "hazard": {
            "dominant": dominant.hazard,
            "label": dominant.label,
            "icon": dominant.icon,
            "results": [r.to_dict() for r in pred.hazard_results],
            "compound": pred.compound.to_dict(),
        },
        "exposure": pred.exposure.to_dict(),
        "model": {
            "name": pred.model_name,
            "version": pred.model_version,
            "kind": pred.model_kind,
            "is_fallback": used_fallback,
            "attempts": attempts,
            "notes": pred.notes,
            "banner": (
                f"Fallback prediction — {attempts[0]['model']} was unavailable "
                f"({attempts[0]['reason']}). Confidence has been reduced."
            )
            if used_fallback
            else None,
        },
        "data_health": bundle.data_health.to_dict(),
        "inputs": bundle.metadata_dict(),
        "data_mode": {
            "is_simulated": True,
            "label": "DEMO / SIMULATED DATA",
            "note": "All environmental values come from PEHRA's deterministic demo feeds. "
                    "No live observation network is connected.",
        },
        "connectivity": ctx.connectivity,
    }

    if detail:
        result["explanation"] = build_explanation(dominant, bundle, sev, mom, pred.compound)
        result["contributors"] = [c.to_dict() for c in dominant.contributions]
        result["early_signals"] = detect_early_signals(db, location, ctx, bundle, pred.overall_risk)
        windows = peak_and_windows(db, location, ctx, bundle, pred.overall_risk, conf.value)
        result.update(windows)
        result["timeline"] = build_timeline(
            db, location, ctx, bundle, inputs, hz_list, n_facilities, conf, preferred_model
        )
        result["comparison"] = build_comparison(db, location, ctx, bundle, pred.overall_risk, windows)
        result["narrative"] = build_narrative(location, result, lang=lang)
        result["forecasts"] = [f.to_dict() for f in bundle.forecasts]

    if persist:
        _persist(db, location, ctx, pred, conf, unc, mom, sev, dominant, bundle, used_fallback, result)

    return result


def build_timeline(
    db: Session,
    location: Location,
    ctx: ProviderContext,
    bundle: FeatureBundle,
    inputs: HorizonInputs,
    hz_list: List[str],
    n_facilities: int,
    base_conf,
    preferred_model: Optional[str],
) -> List[dict]:
    """NOW / +30m / +1h / +2h / +3h / +6h (Section 10)."""
    out: List[dict] = []
    for h in DEFAULT_HORIZONS_MIN:
        try:
            pred, fb, _ = model_registry.predict_with_fallback(
                preferred=preferred_model,
                location=location,
                inputs=inputs,
                hazards=hz_list,
                critical_facilities=n_facilities,
                horizon_minutes=h,
            )
        except ModelUnavailable:
            out.append({
                "horizon_minutes": h,
                "label": _horizon_label(h),
                "available": False,
                "reason": "No model could produce this horizon.",
            })
            continue

        missing_required = sorted({m for r in pred.hazard_results for m in r.missing_required})
        conf = compute_confidence(
            data_health_score=bundle.data_health.score,
            model_confidence=pred.model_confidence,
            forecast_agreement=bundle.forecast_agreement(),
            historical_support=bundle.value("historical_similarity"),
            missing_required=[label_for(m) for m in missing_required],
            stale_features=[label_for(s) for s in bundle.data_health.stale_features],
            is_fallback=fb,
            connectivity=ctx.connectivity,
        )
        # honest horizon decay of confidence
        conf_value = max(20.0, conf.value - (h / 60.0) * 4.5)
        unc = compute_uncertainty(pred.overall_risk, conf_value, h)
        sev = severity_label(pred.overall_risk)
        dominant = next((r for r in pred.hazard_results if r.hazard == pred.dominant_hazard), None)
        intensity = None
        if dominant:
            top = dominant.contributions[0] if dominant.contributions else None
            if top and top.raw_value is not None:
                intensity = f"{top.label} {top.raw_value:.0f} {top.unit}".strip()
        out.append({
            "horizon_minutes": h,
            "label": _horizon_label(h),
            "available": True,
            "risk": round(pred.overall_risk, 1),
            "hazard_score": round(pred.severity_index, 1),
            "exposure_score": round(pred.exposure.score, 1),
            "severity": sev,
            "confidence": round(conf_value, 1),
            "uncertainty": unc.to_dict(),
            "main_hazard": dominant.label if dominant else "—",
            "main_hazard_key": dominant.hazard if dominant else None,
            "expected_intensity": intensity,
            "valid_at": (ctx.now + dt.timedelta(minutes=h)).isoformat() + "Z",
        })
    return out


def _horizon_label(h: int) -> str:
    if h == 0:
        return "NOW"
    if h < 60:
        return f"+{h} MIN"
    if h % 60 == 0:
        return f"+{h // 60} HR"
    return f"+{h // 60}H {h % 60}M"


def build_comparison(db, location, ctx, bundle, current_risk: float, windows: dict) -> dict:
    """Risk one hour ago → now → predicted peak (Section 74)."""
    scenario = get_scenario(ctx.scenario_id)
    ticks_back = max(1, int(60 / scenario.tick_minutes))
    past = None
    if ctx.tick - ticks_back >= 0:
        past = risk_at_tick(db, location, ctx, ctx.tick - ticks_back, bundle)
    peak = windows.get("peak", {})
    return {
        "one_hour_ago": round(past, 1) if past is not None else None,
        "now": round(current_risk, 1),
        "predicted_peak": peak.get("risk"),
        "peak_in_minutes": peak.get("in_minutes"),
        "note": "Past value is the engine re-evaluated on the conditions recorded one hour ago."
        if past is not None
        else "No earlier conditions are available yet in this scenario run.",
    }


def build_narrative(location: Location, result: dict, lang: str = "en") -> dict:
    """The three citizen questions, phrased from the actual computation."""
    risk = result["risk"]
    sev = risk["severity"]
    mom = risk["momentum"]
    expl = result.get("explanation", [])
    hazard_key = result["hazard"]["dominant"]
    hz = HAZARDS.get(hazard_key)

    top_two = [e["text"] for e in expl[:2]]
    whats_happening = " ".join(top_two) if top_two else "Conditions are being monitored."

    peak = result.get("peak", {})
    if mom["band"] in ("ACCELERATING", "RISING") and peak.get("available"):
        whats_next = (
            f"Risk is expected to keep increasing and to peak at about {peak['risk']:.0f}/100 "
            f"in roughly {peak['in_minutes']} minutes."
        )
    elif mom["band"] in ("FALLING", "RAPID_FALL"):
        whats_next = "Risk is easing and is expected to keep declining over the next few hours."
    elif peak.get("available"):
        whats_next = f"Risk is expected to stay near its current level, peaking around {peak['risk']:.0f}/100."
    else:
        whats_next = "No significant change is projected in the next few hours."

    action = sev["action"]
    if hz and sev["key"] in ("HIGH", "CRITICAL"):
        action = f"{hz.citizen_language.get('do', action).capitalize()}. Follow official instructions."

    hi = {
        "whats_happening": _hindi_whats_happening(result),
        "whats_next": _hindi_whats_next(mom, peak),
        "what_to_do": _hindi_action(sev["key"], hazard_key),
    }

    return {
        "whats_happening": whats_happening,
        "whats_next": whats_next,
        "what_to_do": action,
        "hi": hi,
        "one_liner": (
            f"{sev['label']} {hz.label.lower() if hz else 'hazard'} risk — {risk['overall']:.0f}/100, "
            f"{mom['label'].lower()}, confidence {risk['confidence']['value']:.0f}%."
        ),
    }


def _hindi_whats_happening(result: dict) -> str:
    parts = []
    inputs = result.get("inputs", {})
    ri = inputs.get("rain_intensity", {})
    if ri.get("value") is not None:
        parts.append(f"वर्षा की तीव्रता {ri['value']:.0f} मि.मी./घंटा है।")
    rl = inputs.get("river_level_ratio", {})
    if rl.get("value") is not None:
        parts.append(f"नदी का जलस्तर खतरे के स्तर का {rl['value'] * 100:.0f}% है।")
    sm = inputs.get("soil_moisture", {})
    if sm.get("value") is not None:
        parts.append("मिट्टी संतृप्त है, इसलिए नया पानी बहकर जाएगा।")
    return " ".join(parts) or "स्थिति की निगरानी की जा रही है।"


def _hindi_whats_next(mom: dict, peak: dict) -> str:
    if mom["band"] in ("ACCELERATING", "RISING") and peak.get("available"):
        return f"अगले लगभग {peak['in_minutes']} मिनट में जोखिम बढ़कर {peak['risk']:.0f}/100 तक पहुँच सकता है।"
    if mom["band"] in ("FALLING", "RAPID_FALL"):
        return "जोखिम कम हो रहा है और आगे भी घटने की संभावना है।"
    return "अगले कुछ घंटों में बड़ा बदलाव अपेक्षित नहीं है।"


_HI_ACTIONS = {
    "SAFE": "कोई कार्रवाई आवश्यक नहीं। आधिकारिक सूचनाओं पर ध्यान दें।",
    "LOW": "सतर्क रहें। अभी तैयारी की आवश्यकता नहीं है।",
    "MODERATE": "निचले इलाकों की सड़कों से बचें और अपनी योजना की समीक्षा करें।",
    "HIGH": "निचले इलाकों और नालों से दूर रहें। आधिकारिक निर्देशों का पालन करें।",
    "CRITICAL": "तुरंत ऊँची और सुरक्षित जगह पर जाएँ और आपातकालीन निर्देशों का पालन करें।",
}


def _hindi_action(sev_key: str, hazard_key: str) -> str:
    return _HI_ACTIONS.get(sev_key, _HI_ACTIONS["MODERATE"])


def _location_dict(loc: Location) -> dict:
    return {
        "id": loc.id,
        "name": loc.name,
        "name_hi": loc.name_hi,
        "admin_type": loc.admin_type,
        "district": loc.district,
        "state": loc.state,
        "latitude": loc.latitude,
        "longitude": loc.longitude,
        "elevation_m": loc.elevation_m,
        "area_km2": loc.area_km2,
        "population": loc.population,
        "vulnerable_population": loc.vulnerable_population,
        "terrain_vulnerability": loc.terrain_vulnerability,
        "drainage_deficiency": loc.drainage_deficiency,
        "river_id": loc.river_id,
        "polygon": loc.polygon,
        "primary_hazards": loc.primary_hazards,
        "data_origin": loc.data_origin,
    }


def _persist(db, location, ctx, pred, conf, unc, mom, sev, dominant, bundle, used_fallback, result) -> None:
    """Store the prediction + full input snapshot (Sections 39, 40)."""
    rp = RiskPrediction(
        location_id=location.id,
        hazard=dominant.hazard,
        horizon_minutes=0,
        hazard_score=round(pred.severity_index, 2),
        exposure_score=round(pred.exposure.score, 2),
        overall_risk=round(pred.overall_risk, 2),
        severity=sev["key"],
        confidence=round(conf.value, 2),
        uncertainty=round(unc.plus_minus, 2),
        range_low=round(unc.low, 2),
        range_high=round(unc.high, 2),
        momentum_rate=mom["rate_per_hour"],
        momentum_band=mom["band"],
        model_name=pred.model_name,
        model_version=pred.model_version,
        is_fallback=used_fallback,
        degraded_reason=result["model"]["banner"],
        contributors=[c.to_dict() for c in dominant.contributions],
        confidence_breakdown=conf.to_dict(),
        data_health=bundle.data_health.to_dict(),
        explanation=result.get("explanation", []),
        created_at=ctx.now,
        scenario_tick=ctx.tick,
    )
    db.add(rp)
    db.flush()
    db.add(
        PredictionSnapshot(
            prediction_id=rp.id,
            location_id=location.id,
            inputs_raw={k: v for k, v in bundle.raw_dict().items()},
            inputs_normalised={k: v for k, v in bundle.norm_dict().items()},
            feature_metadata=bundle.metadata_dict(),
            weights_used=dominant.weights_used,
            output={
                "overall_risk": rp.overall_risk,
                "hazard_score": rp.hazard_score,
                "exposure_score": rp.exposure_score,
                "severity": rp.severity,
                "confidence": rp.confidence,
                "uncertainty": rp.uncertainty,
            },
            model_name=pred.model_name,
            model_version=pred.model_version,
            created_at=ctx.now,
        )
    )
    db.commit()
    result["prediction_id"] = rp.id
