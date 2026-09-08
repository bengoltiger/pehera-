"""Deterministic demo providers.

IMPORTANT (Section 3): none of these classes contact a real network. They are
labelled `is_simulated=True` everywhere and that label is propagated all the
way to the UI. They exist to prove the adapter architecture works, and to give
the demo reproducible physics.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, List

from app.providers.base import (
    DataProvider,
    ForecastProvider,
    ForecastRecord,
    ObservationRecord,
    ProviderContext,
    ProviderError,
)
from app.simulation.nowcast_error import degrade_value
from app.simulation.scenarios import get_scenario, scenario_field_at


def _apply_overrides(field_values: dict, overrides: dict, features: List[str]) -> dict:
    """Simulation-lab sliders are multiplicative factors on scenario output."""
    out = dict(field_values)
    for feat in features:
        if feat in overrides and out.get(feat) is not None:
            out[feat] = float(out[feat]) * float(overrides[feat])
    return out


class _DemoBase(DataProvider):
    is_simulated = True

    def _field(self, location: Any, ctx: ProviderContext) -> dict:
        if ctx.forced_failures.get(self.key):
            raise ProviderError(f"{self.display_name} is unavailable (forced failure in demo controls)")
        if ctx.connectivity == "offline":
            raise ProviderError(f"{self.display_name} unreachable — device is offline")
        scenario = get_scenario(ctx.scenario_id)
        return scenario_field_at(scenario, ctx.tick, location.latitude, location.longitude)

    def _observed_at(self, ctx: ProviderContext) -> dt.datetime:
        lat = self.latency_seconds
        if ctx.connectivity == "degraded":
            lat = int(lat * 3.5)  # degraded links deliver older data
        return ctx.now - dt.timedelta(seconds=lat)

    def _record(
        self,
        location: Any,
        ctx: ProviderContext,
        feature: str,
        value,
        unit: str,
        reason: str | None = None,
        quality: float = 1.0,
    ) -> ObservationRecord:
        return ObservationRecord(
            feature=feature,
            value=None if value is None else round(float(value), 4),
            unit=unit,
            source=self.display_name,
            source_kind=self.source_kind,
            observed_at=self._observed_at(ctx),
            location_id=location.id,
            quality=quality if ctx.connectivity != "degraded" else quality * 0.8,
            is_simulated=True,
            unavailable_reason=reason,
        )


class DemoRainfallProvider(_DemoBase):
    key = "rainfall"
    display_name = "PEHRA Demo Rain-Gauge Network"
    source_kind = "rainfall"
    features = ["rain_intensity", "rain_accumulation_3h", "rain_acceleration"]
    latency_seconds = 120

    def fetch(self, location: Any, ctx: ProviderContext) -> List[ObservationRecord]:
        f = self._field(location, ctx)
        f = _apply_overrides(f, ctx.overrides, ["rain_intensity", "rain_accumulation_3h"])
        scenario = get_scenario(ctx.scenario_id)
        # acceleration is derived from the previous tick -- a genuine derivative
        prev = scenario_field_at(scenario, max(0, ctx.tick - 1), location.latitude, location.longitude)
        prev = _apply_overrides(prev, ctx.overrides, ["rain_intensity"])
        cur_i, prev_i = f.get("rain_intensity"), prev.get("rain_intensity")
        if cur_i is None or prev_i is None:
            accel = None
        else:
            per_hour = 60.0 / max(scenario.tick_minutes, 1)
            accel = (cur_i - prev_i) * per_hour
        unavailable = f.get("_unavailable", {}) or {}
        return [
            self._record(location, ctx, "rain_intensity", f.get("rain_intensity"), "mm/h",
                         unavailable.get("rain_intensity")),
            self._record(location, ctx, "rain_accumulation_3h", f.get("rain_accumulation_3h"), "mm",
                         unavailable.get("rain_accumulation_3h")),
            self._record(location, ctx, "rain_acceleration", accel, "mm/h²",
                         unavailable.get("rain_intensity")),
        ]


class DemoWeatherProvider(ForecastProvider, _DemoBase):
    key = "weather"
    display_name = "PEHRA Demo Weather Feed"
    source_kind = "weather"
    features = ["temperature_c", "humidity", "wind_speed", "wind_gust", "pressure_hpa"]
    latency_seconds = 300

    def fetch(self, location: Any, ctx: ProviderContext) -> List[ObservationRecord]:
        f = self._field(location, ctx)
        f = _apply_overrides(f, ctx.overrides, ["wind_speed", "wind_gust", "temperature_c"])
        u = f.get("_unavailable", {}) or {}
        return [
            self._record(location, ctx, "temperature_c", f.get("temperature_c"), "°C", u.get("temperature_c")),
            self._record(location, ctx, "humidity", f.get("humidity"), "%", u.get("humidity")),
            self._record(location, ctx, "wind_speed", f.get("wind_speed"), "km/h", u.get("wind_speed")),
            self._record(location, ctx, "wind_gust", f.get("wind_gust"), "km/h", u.get("wind_gust")),
            self._record(location, ctx, "pressure_hpa", f.get("pressure_hpa"), "hPa", u.get("pressure_hpa")),
        ]

    def fetch_forecast(self, location: Any, ctx: ProviderContext) -> List[ForecastRecord]:
        """Forecast = the scenario evaluated at future ticks. Honest by
        construction: the 'model' genuinely knows the forcing function, so we
        degrade agreement with horizon to represent real forecast spread."""
        if ctx.forced_failures.get("forecast"):
            raise ProviderError("Forecast provider unavailable (forced failure in demo controls)")
        scenario = get_scenario(ctx.scenario_id)
        out: List[ForecastRecord] = []
        override_feats = ["rain_intensity", "rain_accumulation_3h", "wind_speed", "temperature_c"]
        present = _apply_overrides(
            scenario_field_at(scenario, ctx.tick, location.latitude, location.longitude),
            ctx.overrides, override_feats,
        )
        # horizon 0 = "what the forecast says about the period starting now".
        # `forecast_rain_3h` is already a next-3-hours quantity, so its horizon-0
        # value is the one the risk engine must consume as a present-time input.
        for horizon in (0, 30, 60, 120, 180, 360):
            ticks_ahead = horizon / scenario.tick_minutes
            future = scenario_field_at(
                scenario, int(round(ctx.tick + ticks_ahead)), location.latitude, location.longitude
            )
            future = _apply_overrides(future, ctx.overrides, override_feats)
            agreement = max(0.42, 0.93 - 0.055 * (horizon / 60.0) ** 1.25)
            scale = float(ctx.overrides.get("forecast_intensity", 1.0))
            for feat, unit in (
                ("rain_intensity", "mm/h"),
                ("forecast_rain_3h", "mm"),
                ("wind_gust", "km/h"),
                ("temperature_c", "°C"),
                ("river_level_ratio", "×danger"),
            ):
                # Never an oracle: the known future is degraded by nowcast
                # skill decay before it leaves the provider (see
                # app/simulation/nowcast_error.py).
                val = degrade_value(
                    feat, future.get(feat), present.get(feat),
                    horizon_minutes=horizon,
                    key=(scenario.id, location.id, ctx.tick),
                )
                if val is not None and feat == "forecast_rain_3h":
                    val = val * scale
                out.append(
                    ForecastRecord(
                        feature=feat,
                        value=None if val is None else round(float(val), 4),
                        unit=unit,
                        source="PEHRA Demo Nowcaster",
                        horizon_minutes=horizon,
                        issued_at=ctx.now,
                        valid_at=ctx.now + dt.timedelta(minutes=horizon),
                        location_id=location.id,
                        model_agreement=round(agreement, 3),
                        is_simulated=True,
                    )
                )
        return out


class DemoRiverProvider(_DemoBase):
    key = "river"
    display_name = "PEHRA Demo River Gauge Network"
    source_kind = "river"
    features = ["river_level_ratio", "river_rate"]
    latency_seconds = 660  # gauges report less often than rain gauges

    def fetch(self, location: Any, ctx: ProviderContext) -> List[ObservationRecord]:
        f = self._field(location, ctx)
        f = _apply_overrides(f, ctx.overrides, ["river_level_ratio", "river_rate"])
        u = f.get("_unavailable", {}) or {}
        if not getattr(location, "river_id", None):
            # Locations with no river genuinely have no gauge -- that is not a
            # failure, it is a structural absence. Recorded as such.
            return [
                self._record(location, ctx, "river_level_ratio", None, "×danger",
                             "No river gauge is associated with this location"),
                self._record(location, ctx, "river_rate", None, "m/h",
                             "No river gauge is associated with this location"),
            ]
        return [
            self._record(location, ctx, "river_level_ratio", f.get("river_level_ratio"), "×danger",
                         u.get("river_level_ratio")),
            self._record(location, ctx, "river_rate", f.get("river_rate"), "m/h", u.get("river_rate")),
        ]


class DemoSatelliteProvider(_DemoBase):
    key = "satellite"
    display_name = "PEHRA Demo Satellite Product"
    source_kind = "satellite"
    features = ["cloud_top_temp_k", "lightning_rate"]
    latency_seconds = 1680  # 28 minutes -- satellite products lag

    def fetch(self, location: Any, ctx: ProviderContext) -> List[ObservationRecord]:
        f = self._field(location, ctx)
        u = f.get("_unavailable", {}) or {}
        return [
            self._record(location, ctx, "cloud_top_temp_k", f.get("cloud_top_temp_k"), "K",
                         u.get("cloud_top_temp_k"), quality=0.92),
            self._record(location, ctx, "lightning_rate", f.get("lightning_rate"), "strikes/15min",
                         u.get("lightning_rate"), quality=0.9),
        ]


class DemoSoilProvider(_DemoBase):
    key = "soil"
    display_name = "PEHRA Demo Soil-Moisture Product"
    source_kind = "soil"
    features = ["soil_moisture"]
    latency_seconds = 2700

    def fetch(self, location: Any, ctx: ProviderContext) -> List[ObservationRecord]:
        f = self._field(location, ctx)
        f = _apply_overrides(f, ctx.overrides, ["soil_moisture"])
        u = f.get("_unavailable", {}) or {}
        return [self._record(location, ctx, "soil_moisture", f.get("soil_moisture"), "m³/m³",
                             u.get("soil_moisture"), quality=0.88)]


class DemoTerrainProvider(_DemoBase):
    key = "terrain"
    display_name = "PEHRA Demo Terrain & Exposure Dataset"
    source_kind = "terrain"
    features = ["terrain_vulnerability", "drainage_deficiency", "population_density", "elevation_m"]
    latency_seconds = 0  # static dataset

    def fetch(self, location: Any, ctx: ProviderContext) -> List[ObservationRecord]:
        # Static datasets do not go offline with the network -- they are cached
        # on device. This is exactly why offline mode can still show terrain.
        if ctx.forced_failures.get(self.key):
            raise ProviderError("Terrain dataset unavailable (forced failure in demo controls)")
        density = location.population / max(location.area_km2, 0.01)
        return [
            self._record(location, ctx, "terrain_vulnerability", location.terrain_vulnerability, "index"),
            self._record(location, ctx, "drainage_deficiency", location.drainage_deficiency, "index"),
            self._record(location, ctx, "population_density", density, "people/km²"),
            self._record(location, ctx, "elevation_m", location.elevation_m, "m"),
        ]


class DemoHistoricalProvider(_DemoBase):
    key = "historical"
    display_name = "PEHRA Demo Historical Incident Archive"
    source_kind = "terrain"
    features = ["historical_similarity"]
    latency_seconds = 0

    def fetch(self, location: Any, ctx: ProviderContext) -> List[ObservationRecord]:
        if ctx.forced_failures.get(self.key):
            raise ProviderError("Historical archive unavailable (forced failure in demo controls)")
        f = self._field(location, ctx)
        # Similarity to past events in the archive: how close current rainfall
        # + river state are to the location's recorded historical event profile.
        hist = getattr(location, "_historical_profile", None) or {
            "rain_intensity": 45.0,
            "river_level_ratio": 0.95,
        }
        rain = f.get("rain_intensity") or 0.0
        river = f.get("river_level_ratio") or 0.0
        rs = 1.0 - min(1.0, abs(rain - hist["rain_intensity"]) / max(hist["rain_intensity"], 1.0))
        vs = 1.0 - min(1.0, abs(river - hist["river_level_ratio"]) / max(hist["river_level_ratio"], 0.1))
        similarity = max(0.0, 0.6 * rs + 0.4 * vs)
        return [self._record(location, ctx, "historical_similarity", similarity, "index", quality=0.8)]
