"""Risk model interface (Section 38).

    RiskModel
     ├── DemoRiskModel          deterministic, fully transparent weighted engine
     ├── StatisticalRiskModel   fitted linear model + trend extrapolation
     └── MLNowcastingModel      gradient-boosted nowcaster (needs a trained artefact)

Every model returns the same `ModelPrediction`, so swapping them changes
nothing downstream. Models declare their own availability; the service layer
falls back explicitly and visibly when the preferred model cannot run
(Section 64).
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from app.engine.risk_engine import CompoundResult, ExposureResult, HazardResult


@dataclass
class HorizonInputs:
    """Normalised feature vectors for the present and for each forecast horizon.

    `future[h]` is what the *forecast providers* say the world will look like in
    h minutes. A model may use it (the demo nowcaster does) or ignore it and
    extrapolate on its own (the ML nowcaster does).
    """

    present: Dict[str, Optional[float]]
    present_raw: Dict[str, Optional[float]]
    future: Dict[int, Dict[str, Optional[float]]] = field(default_factory=dict)
    future_raw: Dict[int, Dict[str, Optional[float]]] = field(default_factory=dict)
    units: Dict[str, str] = field(default_factory=dict)


@dataclass
class ModelPrediction:
    hazard_results: List[HazardResult]
    compound: CompoundResult
    exposure: ExposureResult
    severity_index: float
    overall_risk: float
    dominant_hazard: str
    model_confidence: float          # the model's own self-assessment, 0..100
    model_name: str
    model_version: str
    model_kind: str
    notes: List[str] = field(default_factory=list)
    horizon_minutes: int = 0


class ModelUnavailable(RuntimeError):
    """Raised when a model cannot produce a prediction. Triggers fallback."""


class RiskModel(abc.ABC):
    name: str = "AbstractModel"
    version: str = "0.0"
    kind: str = "abstract"
    description: str = ""
    #: what the model was fitted on -- None for rule-based engines
    trained_on: Optional[str] = None

    def is_available(self) -> bool:
        return True

    def unavailable_reason(self) -> Optional[str]:
        return None

    @abc.abstractmethod
    def predict(
        self,
        *,
        location,
        inputs: HorizonInputs,
        hazards: List[str],
        critical_facilities: int,
        horizon_minutes: int = 0,
    ) -> ModelPrediction:
        ...

    def describe(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "kind": self.kind,
            "description": self.description,
            "trained_on": self.trained_on,
            "available": self.is_available(),
            "unavailable_reason": self.unavailable_reason(),
        }
