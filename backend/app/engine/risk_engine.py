"""PEHRA risk engine (Sections 6, 7, 8, 9, 12, 47).

Design rules obeyed here:
  * nothing is random;
  * every number that reaches the UI is produced by this file (Section 95);
  * the composite score is a *sum of named contributions*, so the explanation
    panel is literally the arithmetic, not a decorative chart;
  * hazard and exposure are computed separately and combined transparently.

Composite arithmetic
--------------------
For a hazard H with component weights C (hazard / vulnerability / forecast,
summing to 1) plus an additive trend bonus, and per-component feature weights w:

    contribution(f) = Σ_c  C[c] · w[c][f] · normalised(f) · 100
    severity_index  = Σ_f contribution(f)          (clamped to [0, 100])

Trend contributes `TREND_BONUS_MAX · w[trend][f] · normalised(f)` points, so an
accelerating situation scores above a static one while a peak (where the rate
of change is zero) is not artificially suppressed. Every feature's share of the
score is exactly contribution(f) / Σ contribution.

Exposure modulates rather than adds, so an intense storm over an empty valley
keeps a high hazard score but a lower operational risk:

    overall = severity · (0.72 + 0.28 · exposure/100)
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from app.core.risk_config import (
    COMPOSITE,
    COMPOUND,
    HAZARD_FAMILIES,
    EXPOSURE_WEIGHTS,
    HAZARDS,
    OVERALL_MIX,
    HazardDefinition,
    level_for_score,
    momentum_for_rate,
)
from app.engine.normalise import label_for, normalise


@dataclass
class Contribution:
    feature: str
    label: str
    points: float          # absolute points added to the severity index
    share: float           # 0..1 share of the severity index
    normalised: float      # 0..1 input value
    raw_value: Optional[float]
    unit: str
    component: str         # dominant component this feature acted through
    direction: str         # "increases" | "reduces"

    def to_dict(self) -> dict:
        return {
            "feature": self.feature,
            "label": self.label,
            "points": round(self.points, 2),
            "share": round(self.share, 4),
            "percent": round(self.share * 100, 1),
            "normalised": round(self.normalised, 4),
            "raw_value": self.raw_value,
            "unit": self.unit,
            "component": self.component,
            "direction": self.direction,
            "bar": "█" * max(1, int(round(self.share * 10))) if self.share > 0 else "",
        }


@dataclass
class HazardResult:
    hazard: str
    label: str
    icon: str
    severity_index: float           # 0..100 environmental severity (the "hazard score")
    components: Dict[str, float]    # hazard / vulnerability / trend / forecast sub-scores 0..100
    contributions: List[Contribution]
    missing_required: List[str]
    used_features: List[str]
    weights_used: Dict[str, Dict[str, float]]
    is_computable: bool
    reason_uncomputable: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "hazard": self.hazard,
            "label": self.label,
            "icon": self.icon,
            "severity_index": round(self.severity_index, 1),
            "components": {k: round(v, 1) for k, v in self.components.items()},
            "contributions": [c.to_dict() for c in self.contributions],
            "missing_required": self.missing_required,
            "used_features": self.used_features,
            "is_computable": self.is_computable,
            "reason_uncomputable": self.reason_uncomputable,
        }


@dataclass
class ExposureResult:
    score: float
    population: int
    vulnerable_population: int
    critical_facilities: int
    breakdown: Dict[str, float]
    estimate_note: str = "Population figures are demo estimates, not census data."

    def to_dict(self) -> dict:
        return {
            "score": round(self.score, 1),
            "population": self.population,
            "vulnerable_population": self.vulnerable_population,
            "critical_facilities": self.critical_facilities,
            "breakdown": {k: round(v, 1) for k, v in self.breakdown.items()},
            "estimate_note": self.estimate_note,
        }


@dataclass
class CompoundResult:
    is_compound: bool
    dominant_hazard: str
    contributing_hazards: List[str]
    base_severity: float
    compound_severity: float
    bonus: float
    interactions: List[dict] = field(default_factory=list)
    explanation: str = ""

    def to_dict(self) -> dict:
        return {
            "is_compound": self.is_compound,
            "dominant_hazard": self.dominant_hazard,
            "contributing_hazards": self.contributing_hazards,
            "base_severity": round(self.base_severity, 1),
            "compound_severity": round(self.compound_severity, 1),
            "bonus": round(self.bonus, 1),
            "interactions": self.interactions,
            "explanation": self.explanation,
        }


# ---------------------------------------------------------------------------
# Core scoring
# ---------------------------------------------------------------------------
def _component_score(
    weights: Dict[str, float],
    norm: Dict[str, Optional[float]],
) -> tuple[float, Dict[str, float], List[str]]:
    """Weighted mean over the features that are actually available.

    Returns (0..1 score, effective weights used, missing feature list).
    Missing inputs are *not* imputed with zero -- that would silently lower the
    score. The remaining weights are renormalised and the omission is reported
    so confidence can be penalised honestly (Section 65).
    """
    available = {f: w for f, w in weights.items() if norm.get(f) is not None}
    missing = [f for f in weights if norm.get(f) is None]
    total_w = sum(available.values())
    if total_w <= 0:
        return 0.0, {}, missing
    effective = {f: w / total_w for f, w in available.items()}
    score = sum(effective[f] * float(norm[f]) for f in effective)  # type: ignore[arg-type]
    return score, effective, missing


def score_hazard(
    hazard_key: str,
    norm: Dict[str, Optional[float]],
    raw: Dict[str, Optional[float]],
    units: Dict[str, str] | None = None,
) -> HazardResult:
    """Compute one hazard's severity index and its full contribution breakdown."""
    hz: HazardDefinition = HAZARDS[hazard_key]
    units = units or {}
    cw = COMPOSITE.normalised()

    comp_specs = {
        "hazard": hz.hazard_weights,
        "vulnerability": hz.vulnerability_weights,
        "trend": hz.trend_weights,
        "forecast": hz.forecast_weights,
    }

    comp_scores: Dict[str, float] = {}
    effective_weights: Dict[str, Dict[str, float]] = {}
    all_missing: set[str] = set()
    # feature -> {component: points}
    per_feature: Dict[str, Dict[str, float]] = {}

    for cname, spec in comp_specs.items():
        score, eff, missing = _component_score(spec, norm)
        comp_scores[cname] = score * 100.0
        effective_weights[cname] = eff
        all_missing.update(missing)
        for f, w in eff.items():
            pts = cw[cname] * w * float(norm[f]) * 100.0  # type: ignore[arg-type]
            per_feature.setdefault(f, {})[cname] = pts

    severity = (
        sum(cw[c] * (comp_scores[c] / 100.0) for c in ("hazard", "vulnerability", "forecast"))
        * 100.0
    ) + cw["trend"] * comp_scores["trend"]
    severity_unclamped = severity
    severity = max(0.0, min(100.0, severity))

    missing_required = [f for f in hz.required_features if norm.get(f) is None]
    computable = len(missing_required) < len(hz.required_features) and severity >= 0

    # If literally nothing is available the score is meaningless -- say so.
    usable_count = sum(1 for f in per_feature if per_feature[f])
    if usable_count == 0:
        return HazardResult(
            hazard=hz.key,
            label=hz.label,
            icon=hz.icon,
            severity_index=0.0,
            components={k: 0.0 for k in comp_specs},
            contributions=[],
            missing_required=missing_required,
            used_features=[],
            weights_used=effective_weights,
            is_computable=False,
            reason_uncomputable="No usable environmental inputs are available for this hazard.",
        )

    total_points = sum(sum(v.values()) for v in per_feature.values()) or 1.0
    contributions: List[Contribution] = []
    for f, comps in per_feature.items():
        pts = sum(comps.values())
        dominant = max(comps.items(), key=lambda kv: kv[1])[0]
        contributions.append(
            Contribution(
                feature=f,
                label=label_for(f),
                points=pts,
                share=pts / total_points,
                normalised=float(norm[f]),  # type: ignore[arg-type]
                raw_value=raw.get(f),
                unit=units.get(f, ""),
                component=dominant,
                direction="increases" if pts > 0 else "reduces",
            )
        )
    contributions.sort(key=lambda c: c.points, reverse=True)

    return HazardResult(
        hazard=hz.key,
        label=hz.label,
        icon=hz.icon,
        severity_index=severity,
        components=comp_scores,
        contributions=contributions,
        missing_required=missing_required,
        used_features=sorted(per_feature.keys()),
        weights_used=effective_weights,
        is_computable=computable,
        reason_uncomputable=None
        if computable
        else "All required inputs for this hazard are unavailable.",
    )


def score_exposure(location, critical_facilities: int = 0) -> ExposureResult:
    """How many people and assets could be affected (Section 7)."""
    density = location.population / max(location.area_km2, 0.01)
    pop_n = normalise("population_density", density) or 0.0
    # vulnerable share, capped at 40% for the normalisation
    vuln_share = location.vulnerable_population / max(location.population, 1)
    vuln_n = max(0.0, min(1.0, vuln_share / 0.4))
    infra_n = max(0.0, min(1.0, critical_facilities / 8.0))

    breakdown = {
        "population": EXPOSURE_WEIGHTS["population"] * pop_n * 100.0,
        "critical_infrastructure": EXPOSURE_WEIGHTS["critical_infrastructure"] * infra_n * 100.0,
        "vulnerable_population": EXPOSURE_WEIGHTS["vulnerable_population"] * vuln_n * 100.0,
    }
    score = max(0.0, min(100.0, sum(breakdown.values())))
    return ExposureResult(
        score=score,
        population=int(location.population),
        vulnerable_population=int(location.vulnerable_population),
        critical_facilities=int(critical_facilities),
        breakdown=breakdown,
    )


def combine_overall(severity: float, exposure: float) -> float:
    """Exposure modulates severity; it never invents danger where there is none."""
    factor = OVERALL_MIX["severity"] + OVERALL_MIX["exposure"] * (exposure / 100.0)
    return max(0.0, min(100.0, severity * factor))


def compute_compound(results: List[HazardResult]) -> CompoundResult:
    """Multi-hazard interaction (Section 47) -- damped, named, never a blind sum.

    Only hazards from DIFFERENT families compound. Within a family (e.g. flood
    and urban flooding) the strongest one is kept and the rest are treated as
    alternative descriptions of the same driver, not as extra danger.
    """
    usable = [r for r in results if r.is_computable and r.severity_index > 0]
    if not usable:
        return CompoundResult(False, "", [], 0.0, 0.0, 0.0, [], "No hazard is currently computable.")

    usable.sort(key=lambda r: r.severity_index, reverse=True)
    dominant = usable[0]
    dom_family = HAZARD_FAMILIES.get(dominant.hazard, dominant.hazard)

    # best hazard per family, excluding the dominant family
    per_family: dict[str, HazardResult] = {}
    for r in usable[1:]:
        fam = HAZARD_FAMILIES.get(r.hazard, r.hazard)
        if fam == dom_family:
            continue
        if r.severity_index < COMPOUND["secondary_min_severity"]:
            continue
        if fam not in per_family or r.severity_index > per_family[fam].severity_index:
            per_family[fam] = r
    secondary = sorted(per_family.values(), key=lambda r: r.severity_index, reverse=True)

    base = dominant.severity_index
    headroom = max(0.0, 100.0 - base)

    damped = 0.0
    for r in secondary:
        damped += COMPOUND["secondary_damping"] * (r.severity_index / 100.0) * headroom

    interactions: List[dict] = []
    keys = {dominant.hazard} | {r.hazard for r in secondary}
    raw_bonus = 0.0
    for inter in COMPOUND["interactions"]:
        if set(inter["pair"]).issubset(keys):
            raw_bonus += inter["bonus"]
            interactions.append(
                {"pair": inter["pair"], "bonus": inter["bonus"], "reason": inter["reason"]}
            )
    scaled_interaction = raw_bonus * (headroom / 100.0)
    total_bonus = min(COMPOUND["max_compound_bonus"], damped + scaled_interaction)
    compound_sev = max(0.0, min(100.0, base + total_bonus))

    is_compound = bool(secondary)
    same_family = [
        r.label for r in usable[1:]
        if HAZARD_FAMILIES.get(r.hazard, r.hazard) == dom_family and r.severity_index >= 35.0
    ]
    if is_compound:
        names = ", ".join(r.label for r in [dominant] + secondary)
        explanation = (
            f"Independent hazards are active at once ({names}). PEHRA takes the strongest hazard "
            f"({dominant.label}, {base:.0f}) and adds a damped, headroom-scaled contribution from the "
            f"others rather than summing them, giving {compound_sev:.0f}."
        )
        if interactions:
            explanation += " " + " ".join(i["reason"] for i in interactions)
    else:
        explanation = f"Only {dominant.label} is significant right now, so no compound adjustment is applied."
    if same_family:
        explanation += (
            f" {', '.join(same_family)} describe the same water event as {dominant.label} and are "
            "therefore not counted twice."
        )

    return CompoundResult(
        is_compound=is_compound,
        dominant_hazard=dominant.hazard,
        contributing_hazards=[dominant.hazard] + [r.hazard for r in secondary],
        base_severity=base,
        compound_severity=compound_sev,
        bonus=total_bonus,
        interactions=interactions,
        explanation=explanation,
    )


def momentum(previous_risk: Optional[float], current_risk: float, minutes: float) -> dict:
    """Rate of change in risk points per hour, plus a named band (Section 9)."""
    if previous_risk is None or minutes <= 0:
        band = momentum_for_rate(0.0)
        return {
            "rate_per_hour": 0.0,
            "delta": 0.0,
            "minutes": minutes,
            "band": band["key"],
            "label": band["label"],
            "arrow": band["arrow"],
            "previous_risk": None,
            "current_risk": round(current_risk, 1),
            "note": "No earlier prediction available for this location yet.",
        }
    delta = current_risk - previous_risk
    rate = delta / (minutes / 60.0)
    band = momentum_for_rate(rate)
    return {
        "rate_per_hour": round(rate, 2),
        "delta": round(delta, 1),
        "minutes": round(minutes, 1),
        "band": band["key"],
        "label": band["label"],
        "arrow": band["arrow"],
        "previous_risk": round(previous_risk, 1),
        "current_risk": round(current_risk, 1),
        "note": f"Risk moved {previous_risk:.0f} → {current_risk:.0f} in {minutes:.0f} minutes.",
    }


def severity_label(score: float) -> dict:
    lvl = level_for_score(score)
    return {
        "key": lvl["key"],
        "label": lvl["label"],
        "icon": lvl["icon"],
        "ascii": lvl["ascii"],
        "color": lvl["color"],
        "pattern": lvl["colorblind_pattern"],
        "explanation": lvl["explanation"],
        "action": lvl["action"],
        "range": [lvl["min"], lvl["max"]],
    }
