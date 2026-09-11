"""Feature normalisation & validation (Layer 2: understand).

Every raw observation is validated and mapped to a 0..1 comparable scale
before the risk engine mixes it. Curves are declared in risk_config, never
inline.
"""
from __future__ import annotations

import math
from typing import Dict, Optional

from app.core.risk_config import NORMALISATION


class ValidationIssue(Exception):
    pass


def validate_value(feature: str, value: Optional[float]) -> Optional[float]:
    """Reject physically impossible values instead of silently using them."""
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(v) or math.isinf(v):
        return None
    hard_limits = {
        "rain_intensity": (0.0, 400.0),
        "rain_accumulation_3h": (0.0, 1200.0),
        "rain_acceleration": (-300.0, 300.0),
        "river_level_ratio": (0.0, 3.0),
        "river_rate": (-5.0, 5.0),
        "soil_moisture": (0.0, 0.7),
        "wind_speed": (0.0, 320.0),
        "wind_gust": (0.0, 400.0),
        "forecast_rain_3h": (0.0, 900.0),
        "cloud_top_temp_k": (150.0, 320.0),
        "lightning_rate": (0.0, 600.0),
        "temperature_c": (-40.0, 60.0),
        "humidity": (0.0, 100.0),
        "pressure_hpa": (850.0, 1090.0),
        "terrain_vulnerability": (0.0, 1.0),
        "drainage_deficiency": (0.0, 1.0),
        "population_density": (0.0, 200000.0),
        "historical_similarity": (0.0, 1.0),
        "elevation_m": (-500.0, 9000.0),
        "slope_deg": (0.0, 90.0),
        "coastal_exposure": (0.0, 1.0),
        "flood_susceptibility": (0.0, 1.0),
        "tide_level_m": (0.0, 12.0),
        "surge_m": (0.0, 10.0),
        "tide_rise_rate": (-5.0, 5.0),
    }
    lo, hi = hard_limits.get(feature, (-1e9, 1e9))
    if v < lo or v > hi:
        raise ValidationIssue(f"{feature}={v} outside physical range [{lo}, {hi}]")
    return v


def normalise(feature: str, value: Optional[float]) -> Optional[float]:
    """Map a raw value to 0..1 using the configured range and curve."""
    if value is None:
        return None
    spec = NORMALISATION.get(feature)
    if not spec:
        return None
    lo, hi = float(spec["min"]), float(spec["max"])
    curve = spec.get("curve", "linear")

    if curve == "inverse":
        # smaller raw value = more dangerous (cloud tops, pressure)
        if hi == lo:
            return 0.0
        t = (hi - float(value)) / (hi - lo)
    elif curve == "log":
        v = max(float(value), lo)
        t = math.log10(v / lo + 1e-9) / max(math.log10(hi / lo), 1e-9) if lo > 0 else 0.0
    else:
        if hi == lo:
            return 0.0
        t = (float(value) - lo) / (hi - lo)

    t = max(0.0, min(1.0, t))
    if curve == "sqrt":
        # intensity metrics matter disproportionately at the low end
        t = math.sqrt(t)
    return round(t, 6)


def denormalise(feature: str, t: float) -> Optional[float]:
    spec = NORMALISATION.get(feature)
    if not spec:
        return None
    lo, hi = float(spec["min"]), float(spec["max"])
    curve = spec.get("curve", "linear")
    t = max(0.0, min(1.0, t))
    if curve == "sqrt":
        t = t * t
    if curve == "inverse":
        return hi - t * (hi - lo)
    if curve == "log" and lo > 0:
        return lo * (10 ** (t * math.log10(hi / lo)))
    return lo + t * (hi - lo)


def unit_for(feature: str) -> str:
    spec = NORMALISATION.get(feature)
    return spec["unit"] if spec else ""


def normalise_all(raw: Dict[str, Optional[float]]) -> Dict[str, Optional[float]]:
    return {k: normalise(k, v) for k, v in raw.items() if k in NORMALISATION}


FEATURE_LABELS: Dict[str, str] = {
    "rain_intensity": "Rainfall intensity",
    "rain_accumulation_3h": "3-hour rainfall",
    "rain_acceleration": "Rainfall acceleration",
    "river_level_ratio": "River level",
    "river_rate": "River rise rate",
    "soil_moisture": "Soil saturation",
    "wind_speed": "Wind speed",
    "wind_gust": "Wind gusts",
    "forecast_rain_3h": "Forecast rainfall (3h)",
    "cloud_top_temp_k": "Cloud-top temperature",
    "lightning_rate": "Lightning activity",
    "temperature_c": "Temperature",
    "humidity": "Humidity",
    "pressure_hpa": "Atmospheric pressure",
    "terrain_vulnerability": "Terrain vulnerability",
    "drainage_deficiency": "Drainage capacity",
    "population_density": "Population density",
    "historical_similarity": "Historical event similarity",
    "elevation_m": "Elevation",
    "slope_deg": "Ground slope",
    "flood_susceptibility": "Flood susceptibility",
    "coastal_exposure": "Coastal exposure",
    "tide_level_m": "Tide level",
    "surge_m": "Storm surge",
    "tide_rise_rate": "Tide rise rate",
}

FEATURE_LABELS_HI: Dict[str, str] = {
    "rain_intensity": "वर्षा की तीव्रता",
    "rain_accumulation_3h": "3 घंटे की वर्षा",
    "rain_acceleration": "वर्षा में वृद्धि दर",
    "river_level_ratio": "नदी का जलस्तर",
    "river_rate": "जलस्तर बढ़ने की दर",
    "soil_moisture": "मिट्टी की नमी",
    "wind_speed": "हवा की गति",
    "wind_gust": "तेज़ झोंके",
    "forecast_rain_3h": "पूर्वानुमानित वर्षा (3 घंटे)",
    "cloud_top_temp_k": "बादल शीर्ष तापमान",
    "lightning_rate": "बिजली गिरने की दर",
    "temperature_c": "तापमान",
    "humidity": "आर्द्रता",
    "pressure_hpa": "वायुदाब",
    "terrain_vulnerability": "भू-भाग संवेदनशीलता",
    "drainage_deficiency": "जल निकासी क्षमता",
    "population_density": "जनसंख्या घनत्व",
    "historical_similarity": "ऐतिहासिक घटना समानता",
    "elevation_m": "ऊँचाई",
    "slope_deg": "भू-ढाल",
    "flood_susceptibility": "बाढ़ संवेदनशीलता",
    "coastal_exposure": "तटीय जोखिम",
    "tide_level_m": "ज्वार स्तर",
    "surge_m": "तूफानी लहर",
    "tide_rise_rate": "ज्वार वृद्धि दर",
}


def label_for(feature: str, lang: str = "en") -> str:
    if lang == "hi":
        return FEATURE_LABELS_HI.get(feature, FEATURE_LABELS.get(feature, feature))
    return FEATURE_LABELS.get(feature, feature)
