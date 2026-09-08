"""The deterministic demo risk model -- PEHRA's reference implementation.

It is fully transparent: the score is the sum of its published contributions.
For future horizons it consumes the forecast feed (the same thing a production
deployment would do with IMD/NWP output).
"""
from __future__ import annotations

from typing import List

from app.core.risk_config import HAZARDS
from app.engine.risk_engine import (
    combine_overall,
    compute_compound,
    score_exposure,
    score_hazard,
)
from app.riskmodels.base import HorizonInputs, ModelPrediction, RiskModel


class DemoRiskModel(RiskModel):
    name = "PEHRA-DemoNowcaster"
    version = "0.1"
    kind = "demo"
    description = (
        "Deterministic weighted risk engine. Combines hazard, environmental "
        "vulnerability, trend/momentum and forecast severity into a composite "
        "index, then modulates it by exposure. Every point of the score is "
        "attributable to a named input."
    )
    trained_on = None  # rule-based: nothing is fitted, nothing is claimed

    def predict(
        self,
        *,
        location,
        inputs: HorizonInputs,
        hazards: List[str],
        critical_facilities: int,
        horizon_minutes: int = 0,
    ) -> ModelPrediction:
        if horizon_minutes > 0 and horizon_minutes in inputs.future:
            norm = inputs.future[horizon_minutes]
            raw = inputs.future_raw.get(horizon_minutes, {})
        else:
            norm = inputs.present
            raw = inputs.present_raw

        results = [
            score_hazard(h, norm, raw, inputs.units) for h in hazards if h in HAZARDS
        ]
        compound = compute_compound(results)
        exposure = score_exposure(location, critical_facilities)

        severity = compound.compound_severity if compound.dominant_hazard else 0.0
        overall = combine_overall(severity, exposure.score)

        # Self-assessment: how much of what the model wants does it actually have?
        computable = [r for r in results if r.is_computable]
        if not computable:
            model_conf = 0.0
        else:
            req_total = sum(len(HAZARDS[r.hazard].required_features) for r in computable)
            req_missing = sum(len(r.missing_required) for r in computable)
            coverage = 1.0 - (req_missing / max(req_total, 1))
            # deterministic engines are most trustworthy at short horizons
            horizon_penalty = min(0.35, (horizon_minutes / 60.0) * 0.05)
            model_conf = max(0.0, min(100.0, (0.9 * coverage - horizon_penalty + 0.1) * 100.0))

        notes: List[str] = []
        if horizon_minutes > 0:
            if horizon_minutes in inputs.future:
                notes.append(
                    f"Forecast-driven nowcast for +{horizon_minutes} min using the forecast feed."
                )
            else:
                notes.append(
                    f"No forecast input available for +{horizon_minutes} min — present conditions were persisted."
                )

        return ModelPrediction(
            hazard_results=results,
            compound=compound,
            exposure=exposure,
            severity_index=severity,
            overall_risk=overall,
            dominant_hazard=compound.dominant_hazard or (hazards[0] if hazards else ""),
            model_confidence=model_conf,
            model_name=self.name,
            model_version=self.version,
            model_kind=self.kind,
            notes=notes,
            horizon_minutes=horizon_minutes,
        )
