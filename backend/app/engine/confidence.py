"""Confidence & uncertainty (Sections 11, 64, 65, 71).

Confidence is never a decorative number. It is a weighted blend of four
measurable components, each of which is shown to the user, minus explicit
penalties for missing or stale inputs. Whenever confidence drops, the reason
is recorded and surfaced.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from app.core.risk_config import CONFIDENCE, confidence_band


@dataclass
class ConfidenceResult:
    value: float                     # 0..100
    components: dict                 # named 0..100 sub-scores
    weights: dict
    penalties: List[dict] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)
    is_reduced: bool = False

    def to_dict(self) -> dict:
        band = confidence_band(self.value)
        return {
            "value": round(self.value, 1),
            "band": band["key"],
            "label": band["label"],
            "band_note": band["note"],
            "components": {k: round(v, 1) for k, v in self.components.items()},
            "weights": self.weights,
            "penalties": self.penalties,
            "reasons": self.reasons,
            "is_reduced": self.is_reduced,
        }


@dataclass
class UncertaintyResult:
    plus_minus: float
    low: float
    high: float
    drivers: List[str]

    def to_dict(self) -> dict:
        return {
            "plus_minus": round(self.plus_minus, 1),
            "low": round(self.low, 1),
            "high": round(self.high, 1),
            "range_label": f"{self.low:.0f}–{self.high:.0f}",
            "drivers": self.drivers,
        }


def compute_confidence(
    *,
    data_health_score: float,
    model_confidence: float,
    forecast_agreement: Optional[float],
    historical_support: Optional[float],
    missing_required: List[str],
    stale_features: List[str],
    is_fallback: bool = False,
    connectivity: str = "online",
) -> ConfidenceResult:
    w = CONFIDENCE["components"]

    # forecast agreement / historical support may be genuinely unknown.
    fa = (forecast_agreement * 100.0) if forecast_agreement is not None else None
    hs = (historical_support * 100.0) if historical_support is not None else None

    components = {
        "data_quality": max(0.0, min(100.0, data_health_score)),
        "model_confidence": max(0.0, min(100.0, model_confidence)),
        "forecast_agreement": fa if fa is not None else 50.0,
        "historical_support": hs if hs is not None else 50.0,
    }

    reasons: List[str] = []
    if fa is None:
        reasons.append("Forecast agreement unknown — no usable forecast was returned; a neutral 50% is assumed.")
    if hs is None:
        reasons.append("Historical support unknown — the incident archive returned no comparable event.")

    base = sum(w[k] * components[k] for k in w)

    penalties: List[dict] = []
    value = base

    if missing_required:
        pts = CONFIDENCE["missing_feature_penalty"] * len(missing_required)
        value -= pts
        penalties.append(
            {
                "kind": "missing_inputs",
                "points": round(pts, 1),
                "detail": ", ".join(missing_required),
            }
        )
        reasons.append(
            "Confidence reduced because required input(s) are unavailable: "
            + ", ".join(missing_required.__iter__())
            + "."
        )

    if stale_features:
        pts = CONFIDENCE["stale_penalty"] * min(len(stale_features), 3)
        value -= pts
        penalties.append(
            {"kind": "stale_inputs", "points": round(pts, 1), "detail": ", ".join(stale_features)}
        )
        reasons.append(
            f"Confidence reduced because {len(stale_features)} input(s) are stale: "
            + ", ".join(stale_features[:4])
            + "."
        )

    if is_fallback:
        before = value
        value *= CONFIDENCE["fallback_confidence_multiplier"]
        penalties.append(
            {
                "kind": "fallback_model",
                "points": round(before - value, 1),
                "detail": "Primary model unavailable — a fallback engine produced this prediction.",
            }
        )
        reasons.append("Confidence reduced because a fallback risk engine was used.")

    if connectivity == "degraded":
        value -= 5.0
        penalties.append({"kind": "degraded_link", "points": 5.0, "detail": "Degraded connectivity"})
        reasons.append("Confidence reduced because the data link is degraded.")
    elif connectivity == "offline":
        value -= 25.0
        penalties.append({"kind": "offline", "points": 25.0, "detail": "Offline — cached data only"})
        reasons.append("Confidence heavily reduced: the device is offline and no new observations are arriving.")

    value = max(CONFIDENCE["floor"], min(CONFIDENCE["ceiling"], value))

    return ConfidenceResult(
        value=value,
        components=components,
        weights=dict(w),
        penalties=penalties,
        reasons=reasons,
        is_reduced=bool(penalties),
    )


def compute_uncertainty(
    prediction: float,
    confidence: float,
    horizon_minutes: int = 0,
    extra_drivers: Optional[List[str]] = None,
) -> UncertaintyResult:
    """±band widens as confidence falls and as the horizon lengthens."""
    conf_gap = max(0.0, 1.0 - confidence / 100.0)
    hours = horizon_minutes / 60.0
    pm = (
        CONFIDENCE["uncertainty_base"]
        + CONFIDENCE["uncertainty_confidence_factor"] * conf_gap
        + CONFIDENCE["uncertainty_horizon_factor"] * hours
    )
    pm = round(min(45.0, pm), 1)
    drivers = list(extra_drivers or [])
    if conf_gap > 0.2:
        drivers.append("Lower confidence widens the expected range.")
    if hours >= 2:
        drivers.append(f"A {hours:.0f}-hour horizon adds forecast spread.")
    if not drivers:
        drivers.append("Inputs are complete and recent, so the range is narrow.")
    return UncertaintyResult(
        plus_minus=pm,
        low=max(0.0, prediction - pm),
        high=min(100.0, prediction + pm),
        drivers=drivers,
    )
