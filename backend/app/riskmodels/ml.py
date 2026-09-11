"""Gradient-boosted nowcasting model.

This is the slot a real ML nowcaster (radar-sequence CNN, LSTM, etc.) would
occupy. The shipped implementation is a gradient-boosting regressor trained to
predict the *future* severity index from present conditions -- a genuine
nowcasting formulation -- but it is trained on simulated scenario data, which
is stated everywhere it is surfaced.

If the artefact is missing the model reports itself unavailable and the
service falls back visibly (Section 64). Nothing is silently substituted.
"""
from __future__ import annotations

import os
import pickle
import re
import sys
import warnings
from typing import List, Optional

import numpy as np
import sklearn

from app.core.config import settings
from app.core.risk_config import HAZARDS
from app.engine.risk_engine import (
    combine_overall,
    compute_compound,
    score_exposure,
    score_hazard,
)
from app.riskmodels.base import HorizonInputs, ModelPrediction, ModelUnavailable, RiskModel
from app.riskmodels.statistical import FEATURE_ORDER, build_vector

DEFAULT_ARTEFACT = os.path.join(os.path.dirname(__file__), "artefacts", "nowcaster.pkl")


def _load_pkl_with_version(path: str):
    """Load a pickle artefact and return ``(payload, pickle_sklearn_version)``.

    sklearn >= 1.3 no longer records ``__sklearn_version__`` on estimators, so
    the only authoritative trace of the training library version is the
    ``InconsistentVersionWarning`` raised during unpickling. We capture it and
    parse the version string; when nothing is found we return ``None`` and the
    model reports the version as unknown instead of guessing.
    """
    with open(path, "rb") as fh:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            payload = pickle.load(fh)
            version: Optional[str] = None
            for w in caught:
                text = str(w.message)
                m = re.search(r"version\s+([0-9]+(?:\.[0-9]+)*)", text)
                if m:
                    version = m.group(1)
                    break
    return payload, version


class MLNowcastingModel(RiskModel):
    name = "PEHRA-MLNowcaster"
    version = "0.3"
    kind = "ml"
    description = (
        "Gradient-boosted regressor that predicts the severity index at a "
        "requested horizon from present conditions only — it does not read the "
        "forecast feed, so it demonstrates true nowcasting behaviour."
    )
    trained_on = "Deterministic PEHRA demo scenarios (simulated data — not observed outcomes)"

    def __init__(self) -> None:
        self._model = None
        self._meta: dict = {}
        self._forced_unavailable = False
        self._pkl_sklearn = None
        self._load()

    def _artefact_path(self) -> str:
        return settings.ml_model_path or DEFAULT_ARTEFACT

    def _load(self) -> None:
        path = self._artefact_path()
        if os.path.exists(path):
            try:
                payload, self._pkl_sklearn = _load_pkl_with_version(path)
                self._model = payload["model"]
                self._meta = payload.get("meta", {})
                self.version = self._meta.get("version", self.version)
            except Exception:
                self._model = None

    def force_unavailable(self, flag: bool) -> None:
        """Used by the Simulation Lab to demonstrate graceful degradation."""
        self._forced_unavailable = flag

    def is_available(self) -> bool:
        return self._model is not None and not self._forced_unavailable

    def unavailable_reason(self) -> Optional[str]:
        if self._forced_unavailable:
            return "ML model disabled from the Simulation Lab to demonstrate fallback."
        if self._model is None:
            return (
                f"No trained artefact at {self._artefact_path()}. "
                "Run `python -m scripts.train_models` to fit it."
            )
        return None

    def describe(self) -> dict:
        d = super().describe()
        d["training_metrics"] = self._meta.get("metrics")
        d["training_samples"] = self._meta.get("n_samples")
        d["trained_at"] = self._meta.get("trained_at")
        d["feature_importance"] = self._meta.get("feature_importance")
        d["runtime_sklearn"] = sklearn.__version__
        d["runtime_python"] = sys.version.split()[0]
        d["pickle_sklearn"] = self._pkl_sklearn
        d["version_mismatch"] = (
            bool(self._pkl_sklearn) and self._pkl_sklearn != sklearn.__version__
        )
        d["metrics_caveat"] = (
            "Fit statistics on held-out SIMULATED scenario data. They describe how "
            "well the model reproduces the reference engine, not real-world skill."
        )
        d["honesty_note"] = (
            "Artefact is a project-trained pickle loaded as-is. Runtime and pickle "
            "library versions are reported side by side; PEHRA never silently "
            "re-pickles or retrains an artefact, so version drift stays visible."
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
        if not self.is_available():
            raise ModelUnavailable(self.unavailable_reason() or "ML model unavailable")

        norm = inputs.present
        raw = inputs.present_raw

        results = [score_hazard(h, norm, raw, inputs.units) for h in hazards if h in HAZARDS]
        compound = compute_compound(results)
        exposure = score_exposure(location, critical_facilities)

        x = build_vector(norm, horizon_minutes).reshape(1, -1)
        severity = float(np.clip(self._model.predict(x)[0], 0.0, 100.0))
        if compound.is_compound:
            severity = min(100.0, severity + compound.bonus * 0.5)

        overall = combine_overall(severity, exposure.score)
        n_missing = sum(1 for f in FEATURE_ORDER if norm.get(f) is None)
        coverage = 1.0 - n_missing / len(FEATURE_ORDER)
        model_conf = max(
            0.0, min(100.0, (0.88 * coverage + 0.04) * 100.0 - (horizon_minutes / 60.0) * 3.5)
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
            notes=[
                "Nowcast produced from present conditions only (no forecast feed used).",
                "Model was fitted on simulated scenario data.",
            ],
            horizon_minutes=horizon_minutes,
        )
