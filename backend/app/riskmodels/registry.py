"""Model registry & explicit fallback chain (Sections 38, 64)."""
from __future__ import annotations

from typing import Dict, List, Optional

from app.core.config import settings
from app.riskmodels.base import ModelPrediction, ModelUnavailable, RiskModel
from app.riskmodels.demo import DemoRiskModel
from app.riskmodels.ml import MLNowcastingModel
from app.riskmodels.statistical import StatisticalRiskModel


class ModelRegistry:
    def __init__(self) -> None:
        self.demo = DemoRiskModel()
        self.statistical = StatisticalRiskModel()
        self.ml = MLNowcastingModel()
        self._models: Dict[str, RiskModel] = {
            "demo": self.demo,
            "statistical": self.statistical,
            "ml": self.ml,
        }
        self.preferred = settings.active_risk_model

    def set_preferred(self, key: str) -> None:
        if key in self._models:
            self.preferred = key

    def get(self, key: str) -> RiskModel:
        return self._models[key]

    def all(self) -> List[RiskModel]:
        return list(self._models.values())

    def chain(self, preferred: Optional[str] = None) -> List[RiskModel]:
        """Preferred model first, then the fallback order. The demo engine is
        always last because it is rule-based and can never be 'unavailable'."""
        key = preferred or self.preferred
        order = [key] + [k for k in ("ml", "statistical", "demo") if k != key]
        return [self._models[k] for k in order if k in self._models]

    def predict_with_fallback(self, *, preferred: Optional[str] = None, **kwargs):
        """Returns (prediction, used_fallback, attempts).

        `attempts` records every model that was tried and why it failed, so the
        UI can state exactly what happened instead of silently switching.
        """
        attempts: List[dict] = []
        chain = self.chain(preferred)
        for idx, model in enumerate(chain):
            if not model.is_available():
                attempts.append(
                    {
                        "model": model.name,
                        "kind": model.kind,
                        "status": "unavailable",
                        "reason": model.unavailable_reason(),
                    }
                )
                continue
            try:
                pred: ModelPrediction = model.predict(**kwargs)
                attempts.append({"model": model.name, "kind": model.kind, "status": "used", "reason": None})
                return pred, idx > 0, attempts
            except ModelUnavailable as exc:
                attempts.append(
                    {"model": model.name, "kind": model.kind, "status": "unavailable", "reason": str(exc)}
                )
            except Exception as exc:  # a model bug must not take the system down
                attempts.append(
                    {"model": model.name, "kind": model.kind, "status": "error", "reason": f"{type(exc).__name__}: {exc}"}
                )
        raise ModelUnavailable("Every risk model failed. No prediction can be produced.")


model_registry = ModelRegistry()
