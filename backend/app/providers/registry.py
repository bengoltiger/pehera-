"""Provider registry -- the single place where feeds are wired up.

To connect a real source: implement `DataProvider`, register it here, and set
the matching `PEHRA_*_PROVIDER` environment variable.
"""
from __future__ import annotations

from typing import Dict, List, Type

from app.core.config import settings
from app.providers.base import DataProvider, ForecastProvider
from app.providers.demo import (
    DemoHistoricalProvider,
    DemoRainfallProvider,
    DemoRiverProvider,
    DemoSatelliteProvider,
    DemoSoilProvider,
    DemoTerrainProvider,
    DemoWeatherProvider,
)

# slot -> {config value -> implementation}
_REGISTRY: Dict[str, Dict[str, Type[DataProvider]]] = {
    "rainfall": {"demo": DemoRainfallProvider},
    "weather": {"demo": DemoWeatherProvider},
    "river": {"demo": DemoRiverProvider},
    "satellite": {"demo": DemoSatelliteProvider},
    "soil": {"demo": DemoSoilProvider},
    "terrain": {"demo": DemoTerrainProvider},
    "historical": {"demo": DemoHistoricalProvider},
}

_SLOT_SETTING = {
    "rainfall": "rainfall_provider",
    "weather": "weather_provider",
    "river": "river_provider",
    "satellite": "satellite_provider",
    "soil": "weather_provider",
    "terrain": "terrain_provider",
    "historical": "historical_provider",
}


class ProviderRegistry:
    def __init__(self) -> None:
        self._instances: Dict[str, DataProvider] = {}
        for slot, impls in _REGISTRY.items():
            wanted = getattr(settings, _SLOT_SETTING[slot], "demo")
            impl = impls.get(wanted) or impls["demo"]
            self._instances[slot] = impl()

    @property
    def all(self) -> List[DataProvider]:
        return list(self._instances.values())

    def get(self, slot: str) -> DataProvider:
        return self._instances[slot]

    @property
    def forecast_provider(self) -> ForecastProvider:
        wp = self._instances["weather"]
        assert isinstance(wp, ForecastProvider)
        return wp

    def any_real_feed(self) -> bool:
        return any(not p.is_simulated for p in self.all)


registry = ProviderRegistry()
