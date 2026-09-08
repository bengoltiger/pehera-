"""Provider adapter interface (Section 37, 103).

Every external data source -- real or simulated -- implements `DataProvider`.
Swapping the demo feed for IMD / ISRO / CWC telemetry means writing one new
class and changing one environment variable. Nothing downstream changes.
"""
from __future__ import annotations

import abc
import datetime as dt
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ObservationRecord:
    """A single measurement with mandatory provenance metadata (Section 3)."""

    feature: str
    value: Optional[float]
    unit: str
    source: str
    source_kind: str
    observed_at: dt.datetime
    location_id: str
    observed_or_predicted: str = "observed"
    quality: float = 1.0
    is_simulated: bool = True
    unavailable_reason: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ForecastRecord:
    feature: str
    value: Optional[float]
    unit: str
    source: str
    horizon_minutes: int
    issued_at: dt.datetime
    valid_at: dt.datetime
    location_id: str
    model_agreement: float = 0.8
    is_simulated: bool = True


@dataclass
class ProviderContext:
    """Everything a provider needs to answer a fetch, without knowing about
    the database or the web framework."""

    now: dt.datetime
    scenario_id: str
    tick: int
    overrides: Dict[str, float] = field(default_factory=dict)
    connectivity: str = "online"
    forced_failures: Dict[str, bool] = field(default_factory=dict)


class ProviderError(RuntimeError):
    """Raised when a provider cannot serve data. Never swallowed silently."""


class DataProvider(abc.ABC):
    """Common interface for every sensing source."""

    #: stable identifier used in configuration
    key: str = "base"
    #: human-readable name shown in the UI as the data source
    display_name: str = "Base Provider"
    #: which freshness profile applies (see risk_config.FRESHNESS)
    source_kind: str = "default"
    #: features this provider is responsible for
    features: List[str] = []
    #: True when the data does not come from a real-world feed
    is_simulated: bool = True
    #: simulated end-to-end latency, drives realistic "updated N min ago"
    latency_seconds: int = 120

    @abc.abstractmethod
    def fetch(self, location: Any, ctx: ProviderContext) -> List[ObservationRecord]:
        """Return current observations for a location."""

    def health(self, ctx: ProviderContext) -> dict:
        failed = bool(ctx.forced_failures.get(self.key))
        offline = ctx.connectivity == "offline"
        status = "unavailable" if (failed or offline) else (
            "degraded" if ctx.connectivity == "degraded" else "operational"
        )
        return {
            "key": self.key,
            "name": self.display_name,
            "kind": self.source_kind,
            "status": status,
            "is_simulated": self.is_simulated,
            "features": list(self.features),
            "latency_seconds": self.latency_seconds,
            "note": "Deterministic demo feed — not a real observation network."
            if self.is_simulated
            else "Live feed.",
        }


class ForecastProvider(DataProvider):
    """Providers that also emit forward-looking values."""

    @abc.abstractmethod
    def fetch_forecast(self, location: Any, ctx: ProviderContext) -> List[ForecastRecord]:
        ...
