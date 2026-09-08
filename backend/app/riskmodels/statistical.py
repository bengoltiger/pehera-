"""Statistical risk model.

A ridge regression fitted on samples produced by the deterministic engine.
It is a genuine fitted model (coefficients are learned, not written by hand)
but we are explicit about what it learned from: simulated scenario data, not
observed disaster outcomes. It therefore cannot be quoted as "accurate" in a
real-world sense, and PEHRA never does so.
"""
from __future__ import annotations

import os
import pickle
from typing import List, Optional

import numpy as np

from app.core.risk_config import HAZARDS
from app.engine.risk_engine import (
    HazardResult,
    combine_overall,
    compute_compound,
    score_exposure,
    score_hazard,
)
from app.riskmodels.base import HorizonInputs, ModelPrediction, RiskModel

FEATURE_ORDER = [
    "rain_intensity",
    "rain_accumulation_3h",
    "rain_acceleration",
    "river_level_ratio",
    "river_rate",
    "soil_moisture",
    "wind_speed",
    "wind_gust",
    "forecast_rain_3h",
    "cloud_top_temp_k",
    "lightning_rate",
    "temperature_c",
    "humidity",
    "pressure_hpa",
    "terrain_vulnerability",
    "drainage_deficiency",
    "population_density",
    "historical_similarity",
]

ARTEFACT = os.path.join(os.path.dirname(__file__), "artefacts", "statistical.pkl")


def build_vector(norm: dict, horizon_minutes: int = 0) -> np.ndarray:
    row = [float(norm.get(f) or 0.0) for f in FEATURE_ORDER]
    row.append(horizon_minutes / 360.0)
    # explicit missingness flags -- the model knows what it did not see
    row.extend([0.0 if norm.get(f) is None else 1.0 for f in FEATURE_ORDER])
    return np.asarray(row, dtype=float)


class StatisticalRiskModel(RiskModel):
    name = "PEHRA-StatRegressor"
    version = "0.2"
    kind = "statistical"
    description = (
        "Ridge regression over normalised environmental features with explicit "
        "missingness indicators. Approximates the reference engine and degrades "
        "smoothly when inputs are absent."
    )
    trained_on = "Deterministic PEHRA demo scenarios (simulated data — not observed outcomes)"

    def __init__(self) -> None:
        self._model = None
        self._meta: dict = {}
        self._load()

    def _load(self) -> None:
        if os.path.exists(ARTEFACT):
            try:
                with open(ARTEFACT, "rb") as fh:
                    payload = pickle.load(fh)
                self._model = payload["model"]
                self._meta = payload.get("meta", {})
                self.version = self._meta.get("version", self.version)
            except Exception:
                self._model = None

    def is_available(self) -> bool:
        return self._model is not None

    def unavailable_reason(self) -> Optional[str]:
        if self._model is None:
            return (
                "No fitted artefact found. Run `python -m scripts.train_models` to fit it."
            )
        return None

    def describe(self) -> dict:
        d = super().describe()
        d["training_metrics"] = self._meta.get("metrics")
        d["training_samples"] = self._meta.get("n_samples")
        d["metrics_caveat"] = (
            "These are fit statistics against the deterministic engine on simulated "
            "data. They are NOT real-world forecast accuracy."
        )
        return d

    def predict(
        self,
        *,
        location,
        inputs: HorizonInputs,
        hazards: List[str],
        critical_facilities: int,
        horizon_minutes: int = 0,
    ) -> ModelPrediction:
        if self._model is None:
            from app.riskmodels.base import ModelUnavailable

            raise ModelUnavailable(self.unavailable_reason() or "Statistical model unavailable")

        norm = inputs.future.get(horizon_minutes, inputs.present) if horizon_minutes else inputs.present
        raw = inputs.future_raw.get(horizon_minutes, inputs.present_raw) if horizon_minutes else inputs.present_raw

        # The regression supplies the severity index; the reference engine still
        # supplies the *explanation* so the two never disagree about inputs.
        results: List[HazardResult] = [
            score_hazard(h, norm, raw, inputs.units) for h in hazards if h in HAZARDS
        ]
        compound = compute_compound(results)
        exposure = score_exposure(location, critical_facilities)

        x = build_vector(norm, horizon_minutes).reshape(1, -1)
        predicted = float(self._model.predict(x)[0])
        severity = max(0.0, min(100.0, predicted))

        # blend the fitted severity with the engine's compound adjustment so
        # multi-hazard interactions are not lost
        if compound.is_compound:
            severity = min(100.0, severity + compound.bonus * 0.6)

        overall = combine_overall(severity, exposure.score)
        n_missing = sum(1 for f in FEATURE_ORDER if norm.get(f) is None)
        coverage = 1.0 - n_missing / len(FEATURE_ORDER)
        model_conf = max(0.0, min(100.0, (0.85 * coverage + 0.05) * 100.0 - horizon_minutes * 0.03))

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
            notes=[
                "Severity produced by a fitted ridge regression; contributions shown "
                "come from the reference engine on identical inputs."
            ],
            horizon_minutes=horizon_minutes,
        )
