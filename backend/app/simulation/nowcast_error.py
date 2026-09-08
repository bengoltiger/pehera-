"""Nowcast skill degradation (Sections 3, 41).

A demo scenario is a known forcing function, so it would be trivial — and
dishonest — to let PEHRA "forecast" by simply reading the scenario at a future
tick. That would make every prediction perfect and the verification dashboard
would report 100% accuracy, which is exactly the kind of fake claim the project
forbids.

Instead, everything forward-looking passes through this module, which applies
the two error modes that dominate real nowcasting:

* **Persistence drag** — the further ahead you look, the more the nowcast is
  pulled towards *current* conditions. Real nowcasts lag rapid intensification
  and hold on too long during decay.
* **Forecast spread** — a deterministic pseudo-random perturbation whose
  amplitude grows with lead time.

Both are deterministic functions of (scenario, location, feature, issue tick,
horizon), so a replay is bit-for-bit reproducible while the error is
uncorrelated across features and horizons, as genuine forecast noise is.

Observations of the *present and past* are never degraded — only projections.
"""
from __future__ import annotations

import hashlib
from typing import Any, Dict, Optional

#: features whose forward projection is degraded. Static properties
#: (terrain, drainage, population) are known, not forecast, and are excluded.
FORECASTABLE = (
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
)

#: features measured on an absolute scale where a multiplicative perturbation
#: would be meaningless (e.g. 260 K ± 8% is 20 K of nonsense). Perturbed
#: additively against a representative span instead.
ABSOLUTE_SCALE = {
    "cloud_top_temp_k": 60.0,   # 215-275 K working range
    "temperature_c": 14.0,      # 28-48 °C working range
    "pressure_hpa": 30.0,       # 985-1015 hPa working range
    "humidity": 60.0,
}


def hash_unit(*parts: Any) -> float:
    """Deterministic pseudo-random value in [-1, 1] derived from a key."""
    digest = hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()
    return (int(digest[:8], 16) / 0xFFFFFFFF) * 2.0 - 1.0


def skill(horizon_minutes: float) -> tuple[float, float]:
    """Return (persistence_weight, noise_amplitude) for a lead time.

    At +30 min the nowcast is close to truth (≈6% persistence drag, ≈2.6%
    spread); by +6 h it is heavily dragged towards persistence (45%) with ≈16%
    spread. These numbers are a modelling choice, documented here and in the
    README, not a measured skill score.
    """
    if horizon_minutes <= 0:
        return 0.0, 0.0
    hours = horizon_minutes / 60.0
    persistence = min(0.45, 0.11 * hours ** 0.8)
    noise = min(0.16, 0.045 * hours ** 0.85)
    return persistence, noise


def degrade_value(
    feature: str,
    future_value: Optional[float],
    present_value: Optional[float],
    *,
    horizon_minutes: float,
    key: tuple,
) -> Optional[float]:
    """Turn a known future value into a realistic nowcast of it."""
    if future_value is None or horizon_minutes <= 0 or feature not in FORECASTABLE:
        return future_value
    persistence, noise = skill(horizon_minutes)
    value = float(future_value)
    if present_value is not None:
        value = (1.0 - persistence) * value + persistence * float(present_value)
    jitter = noise * hash_unit(*key, feature, horizon_minutes)
    if feature in ABSOLUTE_SCALE:
        value += jitter * ABSOLUTE_SCALE[feature]
    else:
        value *= 1.0 + jitter
    if feature in ("rain_acceleration", "river_rate"):
        return value          # legitimately signed
    return max(0.0, value)


def degrade_field(
    future: Dict[str, Optional[float]],
    present: Dict[str, Optional[float]],
    *,
    horizon_minutes: float,
    key: tuple,
) -> Dict[str, Optional[float]]:
    """Apply :func:`degrade_value` across a whole feature dictionary."""
    if horizon_minutes <= 0:
        return dict(future)
    return {
        feat: degrade_value(feat, val, present.get(feat),
                            horizon_minutes=horizon_minutes, key=key)
        for feat, val in future.items()
    }


def describe() -> dict:
    """Machine-readable description for the API and the UI."""
    return {
        "why": "Demo scenarios are known forcing functions. Reading them directly at a future "
               "tick would make PEHRA a perfect oracle and every accuracy figure meaningless.",
        "error_modes": [
            {"name": "Persistence drag",
             "detail": "Projections are blended towards present conditions with weight "
                       "min(0.45, 0.11·h^0.8), so the nowcast lags intensification and "
                       "over-holds during decay."},
            {"name": "Forecast spread",
             "detail": "Deterministic perturbation of amplitude min(0.16, 0.045·h^0.85), "
                       "keyed on scenario, location, feature, issue tick and horizon."},
        ],
        "table": [
            {"horizon_minutes": h,
             "persistence_weight": round(skill(h)[0], 3),
             "noise_amplitude": round(skill(h)[1], 3)}
            for h in (30, 60, 120, 180, 360)
        ],
        "not_applied_to": "Present and past observations, and static properties such as terrain, "
                          "drainage and population.",
    }
