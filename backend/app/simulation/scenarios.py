"""Deterministic demo scenarios (Sections 45, 78).

A scenario is a *forcing function*: for a given tick it returns the
environmental state at a moving epicentre, plus how that forcing decays with
distance. Nothing here is random -- the same tick always yields the same
numbers, which is what makes the demo reproducible and the risk engine
auditable.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _sample_curve(points: List[float], tick: int) -> float:
    """Piecewise-linear sample of a control-point curve at a (possibly
    fractional) tick index. Clamps at both ends."""
    if not points:
        return 0.0
    if tick <= 0:
        return float(points[0])
    if tick >= len(points) - 1:
        return float(points[-1])
    lo = int(math.floor(tick))
    hi = min(lo + 1, len(points) - 1)
    return _lerp(float(points[lo]), float(points[hi]), tick - lo)


@dataclass
class EpicentreTrack:
    """Where the forcing is centred at each tick. Enables real threat-cell
    movement instead of a decorative arrow."""

    lats: List[float]
    lngs: List[float]

    def at(self, tick: int) -> tuple[float, float]:
        return _sample_curve(self.lats, tick), _sample_curve(self.lngs, tick)


@dataclass
class ScenarioDefinition:
    id: str
    name: str
    description: str
    hazard_focus: List[str]
    focus_location_id: str
    tick_minutes: int
    total_ticks: int
    # curves at the epicentre, indexed by tick
    curves: Dict[str, List[float]]
    epicentre: EpicentreTrack
    # km at which forcing has decayed to ~37% of the epicentre value
    decay_km: float = 14.0
    # features that the scenario deliberately makes unavailable, per tick range
    outages: List[dict] = field(default_factory=list)
    narrative: str = ""
    expected_peak_tick: Optional[int] = None

    def duration_minutes(self) -> int:
        return self.tick_minutes * self.total_ticks

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "hazard_focus": self.hazard_focus,
            "focus_location_id": self.focus_location_id,
            "tick_minutes": self.tick_minutes,
            "total_ticks": self.total_ticks,
            "duration_minutes": self.duration_minutes(),
            "narrative": self.narrative,
            "expected_peak_tick": self.expected_peak_tick,
            "is_deterministic": True,
            "curves": self.curves,
            "decay_km": self.decay_km,
            "outages": self.outages,
        }


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


# ---------------------------------------------------------------------------
# The library. Every curve has exactly total_ticks+1 control points.
# Tick = 15 minutes -> 24 ticks = 6 hours of simulated event.
# ---------------------------------------------------------------------------

MUMBAI_NORMAL = ScenarioDefinition(
    id="mumbai_normal",
    name="Mumbai — normal monsoon day",
    description="Baseline monsoon-season day for Mumbai. Light intermittent rain, calm Arabian Sea tide, river gauges well below danger. Used as the calm reference state for the Mumbai demonstration.",
    hazard_focus=["flood", "coastal_flood"],
    focus_location_id="loc_andheri",
    tick_minutes=15,
    total_ticks=24,
    epicentre=EpicentreTrack(lats=[19.05] * 25, lngs=[72.85] * 25),
    decay_km=20.0,
    curves={
        "rain_intensity": [2, 3, 3, 4, 3, 3, 2, 3, 4, 4, 3, 3, 2, 2, 3, 2, 2, 3, 3, 2, 2, 3, 2, 2, 2],
        "rain_accumulation_3h": [6, 7, 8, 9, 9, 9, 9, 10, 10, 10, 10, 9, 9, 9, 9, 9, 8, 9, 9, 9, 8, 8, 8, 8, 8],
        "river_level_ratio": [0.42] * 25,
        "river_rate": [0.0, 0.01, 0.01, 0.02, 0.01, 0.0, 0.0, 0.01, 0.02, 0.01, 0.0, 0.0, 0.0, 0.01, 0.0, 0.0, -0.01, 0.0, 0.01, 0.0, 0.0, 0.0, 0.01, 0.0, 0.0],
        "soil_moisture": [0.26] * 25,
        "wind_speed": [12, 12, 13, 13, 12, 11, 12, 13, 14, 13, 12, 12, 11, 12, 12, 11, 12, 13, 12, 11, 11, 12, 12, 11, 11],
        "wind_gust": [19, 20, 21, 22, 20, 18, 20, 22, 24, 22, 20, 19, 18, 20, 20, 18, 20, 22, 20, 18, 18, 19, 20, 18, 18],
        "forecast_rain_3h": [8, 9, 9, 10, 9, 9, 9, 10, 10, 10, 10, 9, 9, 9, 9, 9, 8, 9, 9, 9, 8, 8, 8, 8, 8],
        "cloud_top_temp_k": [268] * 25,
        "lightning_rate": [0] * 25,
        "temperature_c": [30, 30, 31, 31, 31, 31, 31, 31, 30, 30, 30, 29, 29, 29, 28, 28, 28, 27, 27, 27, 26, 26, 26, 26, 26],
        "humidity": [82, 82, 83, 84, 85, 86, 87, 88, 88, 88, 87, 86, 85, 85, 84, 83, 83, 82, 82, 81, 81, 80, 80, 79, 79],
        "pressure_hpa": [1006] * 25,
        "tide_level_m": [0.9, 1.1, 1.4, 1.8, 2.2, 2.7, 3.2, 3.7, 4.1, 4.4, 4.6, 4.7, 4.7, 4.6, 4.4, 4.1, 3.7, 3.2, 2.7, 2.2, 1.8, 1.4, 1.1, 0.9, 0.8],
        "surge_m": [0.0] * 25,
    },
    narrative="Nothing significant is developing. PEHRA stays quiet — this demonstrates that the system does not cry wolf, even with a normal high tide rolling in.",
    expected_peak_tick=None,
)


MUMBAI_HEAVY_RAIN = ScenarioDefinition(
    id="mumbai_heavy_rain",
    name="Mumbai — heavy monsoon rain",
    description="A monsoon band builds off the harbour and drifts north across the island. Rain intensifies steadily, the Dharavi-BKC drainage network fills, and the high tide slows outflow in the afternoon.",
    hazard_focus=["urban_flood", "extreme_rain", "coastal_flood"],
    focus_location_id="loc_dadar",
    tick_minutes=15,
    total_ticks=24,
    epicentre=EpicentreTrack(
        lats=[18.94, 18.95, 18.96, 18.97, 18.98, 19.00, 19.01, 19.02, 19.03, 19.05, 19.06, 19.07,
              19.08, 19.10, 19.11, 19.12, 19.13, 19.15, 19.16, 19.17, 19.18, 19.19, 19.21, 19.22, 19.23],
        lngs=[72.83, 72.83, 72.84, 72.84, 72.84, 72.85, 72.85, 72.85, 72.86, 72.86, 72.86, 72.87,
              72.87, 72.87, 72.88, 72.88, 72.88, 72.89, 72.89, 72.89, 72.90, 72.90, 72.90, 72.91, 72.91],
    ),
    decay_km=12.0,
    curves={
        "rain_intensity": [5, 8, 12, 17, 22, 28, 33, 38, 42, 45, 46, 45, 42, 38, 33, 28, 24, 20, 16, 13, 11, 9, 7, 6, 5],
        "rain_accumulation_3h": [10, 15, 23, 33, 45, 59, 74, 89, 103, 115, 124, 131, 135, 135, 132, 127, 119, 109, 98, 87, 77, 68, 60, 53, 48],
        "river_level_ratio": [0.45, 0.46, 0.48, 0.51, 0.54, 0.58, 0.62, 0.66, 0.70, 0.74, 0.78, 0.81, 0.84, 0.86, 0.85, 0.84, 0.82, 0.80, 0.77, 0.74, 0.71, 0.68, 0.65, 0.62, 0.60],
        "river_rate": [0.02, 0.04, 0.07, 0.10, 0.14, 0.18, 0.21, 0.24, 0.26, 0.27, 0.26, 0.24, 0.20, 0.15, 0.10, 0.05, 0.01, -0.03, -0.06, -0.08, -0.09, -0.10, -0.11, -0.11, -0.10],
        "soil_moisture": [0.28, 0.29, 0.31, 0.33, 0.35, 0.37, 0.39, 0.41, 0.42, 0.43, 0.44, 0.45, 0.45, 0.45, 0.44, 0.43, 0.42, 0.41, 0.40, 0.39, 0.38, 0.37, 0.36, 0.35, 0.34],
        "wind_speed": [15, 17, 19, 22, 24, 26, 28, 29, 30, 31, 31, 30, 29, 28, 26, 24, 22, 20, 18, 17, 16, 15, 14, 13, 13],
        "wind_gust": [22, 26, 31, 36, 41, 46, 50, 53, 55, 56, 56, 54, 52, 49, 46, 42, 39, 35, 32, 29, 27, 25, 23, 22, 21],
        "forecast_rain_3h": [18, 26, 37, 49, 61, 73, 84, 93, 99, 102, 101, 96, 88, 78, 68, 58, 49, 41, 34, 28, 23, 19, 16, 13, 12],
        "cloud_top_temp_k": [258, 253, 248, 243, 238, 233, 229, 226, 223, 221, 220, 220, 222, 225, 229, 233, 238, 243, 248, 252, 256, 260, 263, 265, 266],
        "lightning_rate": [0, 1, 2, 4, 7, 10, 13, 16, 18, 19, 18, 17, 14, 11, 9, 7, 5, 3, 2, 1, 1, 0, 0, 0, 0],
        "temperature_c": [28, 28, 27, 27, 26, 26, 25, 25, 24, 24, 24, 24, 24, 24, 25, 25, 25, 26, 26, 26, 27, 27, 27, 28, 28],
        "humidity": [80, 82, 84, 86, 88, 90, 92, 93, 94, 95, 95, 95, 94, 94, 93, 92, 91, 90, 89, 88, 87, 86, 85, 84, 84],
        "pressure_hpa": [1004, 1003, 1002, 1000, 999, 998, 997, 996, 995, 995, 995, 996, 997, 998, 999, 1000, 1001, 1002, 1003, 1004, 1004, 1005, 1006, 1006, 1006],
        "tide_level_m": [0.8, 0.9, 1.1, 1.4, 1.8, 2.2, 2.7, 3.2, 3.6, 4.0, 4.3, 4.4, 4.5, 4.4, 4.2, 3.9, 3.5, 3.1, 2.6, 2.2, 1.8, 1.4, 1.1, 0.9, 0.8],
        "surge_m": [0.0] * 25,
    },
    narrative="Rainfall intensity roughly doubles every 45 minutes for two hours, then decays. The afternoon high tide coincides with peak rain and slows drainage outfall.",
    expected_peak_tick=10,
)


MUMBAI_CLOUDBURST = ScenarioDefinition(
    id="mumbai_cloudburst",
    name="Mumbai — cloudburst (Dharavi-Kurla)",
    description="A tiny convective cell parks directly over Kurla-BKC and releases ~90 mm in under an hour — a genuine Mumbai cloudburst. The river barely responds; this ward-scale danger is entirely drainage failure.",
    hazard_focus=["urban_flood", "extreme_rain"],
    focus_location_id="loc_kurla",
    tick_minutes=15,
    total_ticks=24,
    epicentre=EpicentreTrack(
        lats=[19.068, 19.069, 19.069, 19.070, 19.070, 19.070, 19.071, 19.071, 19.071, 19.071,
              19.071, 19.071, 19.070, 19.070, 19.070, 19.069, 19.069, 19.069, 19.068, 19.068,
              19.068, 19.068, 19.067, 19.067, 19.067],
        lngs=[72.878, 72.878, 72.879, 72.879, 72.880, 72.880, 72.880, 72.881, 72.881, 72.881,
              72.881, 72.881, 72.880, 72.880, 72.880, 72.879, 72.879, 72.879, 72.878, 72.878,
              72.878, 72.877, 72.877, 72.877, 72.876],
    ),
    decay_km=5.0,
    curves={
        "rain_intensity": [4, 9, 18, 33, 52, 74, 90, 96, 94, 84, 66, 46, 30, 19, 13, 10, 8, 6, 5, 4, 3, 3, 2, 2, 2],
        "rain_accumulation_3h": [8, 14, 28, 55, 95, 145, 198, 246, 282, 306, 318, 316, 300, 274, 244, 213, 184, 157, 133, 112, 94, 79, 67, 57, 49],
        "river_level_ratio": [0.40, 0.40, 0.41, 0.42, 0.44, 0.46, 0.49, 0.52, 0.55, 0.57, 0.58, 0.58, 0.57, 0.55, 0.53, 0.51, 0.50, 0.49, 0.48, 0.47, 0.46, 0.45, 0.45, 0.44, 0.44],
        "river_rate": [0.00, 0.01, 0.03, 0.06, 0.09, 0.13, 0.16, 0.18, 0.19, 0.18, 0.15, 0.11, 0.06, 0.02, -0.02, -0.04, -0.05, -0.06, -0.06, -0.06, -0.05, -0.04, -0.03, -0.03, -0.02],
        "soil_moisture": [0.30, 0.31, 0.33, 0.37, 0.41, 0.45, 0.48, 0.50, 0.51, 0.51, 0.50, 0.49, 0.48, 0.46, 0.44, 0.43, 0.41, 0.40, 0.39, 0.38, 0.37, 0.37, 0.36, 0.36, 0.35],
        "wind_speed": [14, 16, 19, 23, 28, 33, 37, 40, 41, 41, 39, 36, 32, 28, 24, 21, 18, 16, 15, 14, 13, 13, 12, 12, 12],
        "wind_gust": [22, 27, 34, 43, 54, 65, 74, 80, 82, 81, 76, 68, 58, 48, 40, 34, 30, 27, 24, 22, 21, 20, 19, 19, 18],
        "forecast_rain_3h": [28, 45, 76, 118, 166, 216, 262, 296, 318, 322, 306, 276, 236, 192, 152, 118, 92, 72, 57, 46, 38, 32, 27, 23, 21],
        "cloud_top_temp_k": [252, 245, 237, 228, 219, 211, 206, 203, 202, 204, 209, 217, 227, 237, 246, 253, 258, 262, 265, 267, 268, 269, 270, 271, 272],
        "lightning_rate": [2, 5, 11, 22, 40, 62, 82, 96, 104, 104, 96, 82, 62, 42, 27, 16, 10, 6, 4, 2, 2, 1, 1, 0, 0],
        "temperature_c": [29, 28, 27, 26, 25, 24, 23, 23, 22, 22, 23, 23, 24, 25, 26, 27, 27, 28, 28, 29, 29, 29, 30, 30, 30],
        "humidity": [76, 79, 83, 88, 93, 97, 99, 100, 100, 99, 97, 94, 91, 88, 85, 82, 80, 79, 78, 77, 76, 75, 75, 74, 74],
        "pressure_hpa": [1003, 1002, 1000, 997, 993, 989, 986, 984, 983, 984, 987, 991, 995, 999, 1002, 1004, 1005, 1006, 1006, 1007, 1007, 1007, 1008, 1008, 1008],
        "tide_level_m": [0.7, 0.6, 0.5, 0.6, 0.7, 0.9, 1.1, 1.4, 1.7, 2.0, 2.2, 2.3, 2.2, 2.0, 1.7, 1.4, 1.1, 0.9, 0.7, 0.6, 0.5, 0.6, 0.7, 0.9, 1.0],
        "surge_m": [0.0] * 25,
    },
    narrative="Peak rainfall of ~90 mm/h over 45 minutes on a low tide. The river stays calm — this scenario proves PEHRA separates ward-level drainage risk from river and coastal risk.",
    expected_peak_tick=8,
)


MUMBAI_HIGH_TIDE = ScenarioDefinition(
    id="mumbai_high_tide",
    name="Mumbai — heavy rain at high tide",
    description="The classic Mumbai combination: heavy rain meeting a 'full moon' high tide (~4.9 m). Storm-water outfalls cannot discharge against the tide, so streets between Mahim and Worli waterlog even with a moderate storm.",
    hazard_focus=["coastal_flood", "urban_flood"],
    focus_location_id="loc_mahim",
    tick_minutes=15,
    total_ticks=24,
    epicentre=EpicentreTrack(lats=[19.035] * 25, lngs=[72.845] * 25),
    decay_km=9.0,
    curves={
        "rain_intensity": [6, 10, 15, 21, 27, 32, 36, 38, 39, 38, 36, 33, 29, 25, 22, 19, 16, 14, 12, 10, 9, 8, 7, 6, 5],
        "rain_accumulation_3h": [14, 20, 30, 43, 58, 74, 90, 104, 115, 122, 127, 128, 125, 120, 112, 103, 94, 85, 77, 69, 62, 56, 50, 45, 41],
        "river_level_ratio": [0.46, 0.47, 0.49, 0.52, 0.55, 0.59, 0.63, 0.67, 0.71, 0.74, 0.76, 0.78, 0.79, 0.79, 0.78, 0.76, 0.74, 0.72, 0.69, 0.66, 0.63, 0.60, 0.57, 0.54, 0.52],
        "river_rate": [0.02, 0.05, 0.08, 0.12, 0.16, 0.19, 0.22, 0.24, 0.25, 0.24, 0.22, 0.19, 0.15, 0.10, 0.05, 0.01, -0.03, -0.06, -0.08, -0.10, -0.11, -0.11, -0.10, -0.08, -0.07],
        "soil_moisture": [0.27, 0.28, 0.30, 0.33, 0.36, 0.38, 0.41, 0.43, 0.45, 0.46, 0.47, 0.48, 0.48, 0.48, 0.47, 0.46, 0.45, 0.43, 0.42, 0.41, 0.40, 0.39, 0.38, 0.37, 0.36],
        "wind_speed": [14, 16, 18, 21, 23, 25, 27, 28, 29, 29, 28, 27, 26, 24, 23, 21, 20, 18, 17, 16, 15, 14, 14, 13, 13],
        "wind_gust": [22, 26, 30, 35, 39, 43, 46, 49, 50, 51, 50, 48, 46, 43, 40, 37, 34, 32, 29, 27, 26, 24, 23, 22, 21],
        "forecast_rain_3h": [22, 32, 45, 60, 76, 91, 104, 114, 121, 124, 123, 118, 109, 98, 86, 75, 65, 56, 48, 41, 35, 30, 26, 22, 20],
        "cloud_top_temp_k": [255, 249, 243, 237, 231, 226, 222, 219, 217, 217, 219, 223, 229, 236, 243, 250, 256, 261, 265, 268, 271, 273, 274, 275, 276],
        "lightning_rate": [0, 1, 2, 4, 7, 10, 13, 16, 18, 19, 18, 16, 13, 10, 7, 5, 3, 2, 1, 1, 0, 0, 0, 0, 0],
        "temperature_c": [28, 28, 27, 27, 26, 26, 25, 25, 24, 24, 24, 24, 25, 25, 25, 26, 26, 26, 27, 27, 27, 28, 28, 28, 28],
        "humidity": [80, 82, 85, 88, 91, 93, 95, 96, 97, 97, 96, 95, 94, 93, 92, 91, 90, 89, 88, 87, 86, 85, 84, 84, 83],
        "pressure_hpa": [1002, 1001, 1000, 998, 996, 994, 992, 991, 990, 990, 991, 993, 995, 998, 1000, 1002, 1003, 1004, 1005, 1006, 1007, 1007, 1008, 1008, 1008],
        "tide_level_m": [1.2, 1.6, 2.1, 2.7, 3.3, 3.9, 4.4, 4.7, 4.9, 4.9, 4.8, 4.5, 4.1, 3.6, 3.1, 2.6, 2.1, 1.7, 1.4, 1.1, 1.0, 0.9, 1.0, 1.1, 1.2],
        "surge_m": [0.05, 0.07, 0.10, 0.13, 0.16, 0.18, 0.20, 0.22, 0.25, 0.28, 0.30, 0.32, 0.34, 0.35, 0.35, 0.33, 0.30, 0.27, 0.23, 0.19, 0.15, 0.12, 0.09, 0.07, 0.05],
    },
    narrative="Tide peaks at ~4.9 m at the same time as rain peaks. Even moderate rain becomes a flooded-road event because the drains cannot discharge — coastal_flood and urban_flood compound.",
    expected_peak_tick=10,
)


MUMBAI_STORM_SURGE = ScenarioDefinition(
    id="mumbai_storm_surge",
    name="Mumbai — cyclonic storm & storm surge",
    description="A deep depression over the north Arabian Sea strengthens into a cyclonic storm and brushes the coast. Gale-force gusts, 2.9 m surge at Colaba, and sea water pushing into low-lying coastal wards.",
    hazard_focus=["coastal_flood", "severe_wind", "thunderstorm"],
    focus_location_id="loc_colaba",
    tick_minutes=15,
    total_ticks=24,
    epicentre=EpicentreTrack(
        lats=[18.98, 18.99, 19.00, 19.00, 19.01, 19.01, 19.02, 19.02, 19.03, 19.03, 19.04, 19.04,
              19.05, 19.05, 19.06, 19.06, 19.07, 19.07, 19.08, 19.08, 19.09, 19.09, 19.10, 19.10, 19.11],
        lngs=[72.70, 72.70, 72.71, 72.72, 72.73, 72.74, 72.75, 72.76, 72.77, 72.78, 72.79, 72.80,
              72.81, 72.82, 72.82, 72.83, 72.83, 72.84, 72.84, 72.85, 72.85, 72.86, 72.86, 72.87, 72.87],
    ),
    decay_km=16.0,
    curves={
        "rain_intensity": [8, 12, 17, 22, 27, 30, 32, 33, 33, 32, 31, 29, 27, 25, 23, 21, 19, 17, 15, 13, 11, 9, 8, 7, 6],
        "rain_accumulation_3h": [16, 24, 35, 48, 63, 78, 92, 104, 114, 121, 126, 128, 128, 125, 120, 114, 107, 99, 90, 81, 72, 63, 56, 49, 44],
        "river_level_ratio": [0.48, 0.50, 0.53, 0.57, 0.61, 0.66, 0.71, 0.76, 0.81, 0.85, 0.88, 0.90, 0.91, 0.90, 0.88, 0.85, 0.82, 0.79, 0.76, 0.73, 0.70, 0.67, 0.64, 0.61, 0.58],
        "river_rate": [0.04, 0.08, 0.13, 0.18, 0.23, 0.28, 0.33, 0.37, 0.41, 0.42, 0.42, 0.39, 0.34, 0.27, 0.18, 0.09, 0.00, -0.07, -0.12, -0.15, -0.16, -0.15, -0.13, -0.10, -0.08],
        "soil_moisture": [0.30, 0.32, 0.34, 0.36, 0.39, 0.42, 0.45, 0.48, 0.50, 0.51, 0.52, 0.52, 0.52, 0.51, 0.50, 0.49, 0.48, 0.46, 0.45, 0.43, 0.42, 0.41, 0.40, 0.39, 0.38],
        "wind_speed": [30, 36, 43, 52, 61, 70, 78, 85, 90, 93, 94, 92, 88, 82, 74, 66, 58, 51, 45, 40, 36, 33, 31, 29, 28],
        "wind_gust": [48, 58, 70, 85, 100, 114, 126, 136, 143, 146, 146, 142, 132, 120, 106, 92, 80, 70, 62, 56, 51, 48, 45, 43, 42],
        "forecast_rain_3h": [34, 45, 60, 78, 96, 112, 126, 136, 142, 144, 142, 135, 124, 111, 97, 84, 71, 60, 50, 42, 36, 31, 27, 24, 21],
        "cloud_top_temp_k": [248, 240, 232, 223, 215, 208, 203, 200, 198, 198, 200, 205, 213, 222, 232, 241, 249, 256, 262, 267, 271, 274, 276, 278, 279],
        "lightning_rate": [2, 5, 10, 18, 28, 39, 49, 57, 62, 63, 61, 55, 45, 35, 25, 17, 11, 7, 5, 3, 2, 1, 1, 0, 0],
        "temperature_c": [30, 29, 28, 27, 26, 25, 24, 23, 22, 22, 22, 22, 23, 24, 25, 26, 27, 27, 28, 28, 29, 29, 30, 30, 30],
        "humidity": [74, 78, 82, 87, 91, 94, 96, 98, 99, 99, 98, 97, 96, 94, 92, 90, 88, 87, 85, 84, 83, 82, 81, 80, 80],
        "pressure_hpa": [1000, 997, 994, 990, 986, 983, 980, 978, 977, 977, 979, 983, 988, 993, 997, 1000, 1002, 1004, 1005, 1006, 1007, 1008, 1008, 1009, 1009],
        "tide_level_m": [1.0, 1.2, 1.5, 1.8, 2.2, 2.5, 2.9, 3.2, 3.3, 3.4, 3.4, 3.5, 3.5, 3.4, 3.2, 2.9, 2.6, 2.3, 2.0, 1.7, 1.4, 1.2, 1.0, 0.9, 0.8],
        "surge_m": [0.05, 0.12, 0.22, 0.36, 0.55, 0.78, 1.05, 1.35, 1.65, 1.95, 2.25, 2.55, 2.75, 2.90, 2.95, 2.85, 2.60, 2.25, 1.80, 1.35, 0.95, 0.60, 0.35, 0.18, 0.08],
    },
    narrative="Water level = tide + surge. The surge peaks ~2.9 m at Colaba; combined with the tide this pushes low-lying coastal wards past their inundation threshold well before winds peak.",
    expected_peak_tick=13,
)


MUMBAI_MITHI = ScenarioDefinition(
    id="mumbai_mithi",
    name="Mumbai — Mithi river overflow",
    description="Sustained catchment rain above Vihar Lake drives the Mithi down its concrete channel and over its banks between Dharavi, BKC and Bandra-Kurla flats. The river crosses danger around tick 15.",
    hazard_focus=["flood", "urban_flood"],
    focus_location_id="loc_kurla",
    tick_minutes=15,
    total_ticks=24,
    epicentre=EpicentreTrack(
        lats=[19.12, 19.115, 19.11, 19.105, 19.10, 19.095, 19.09, 19.085, 19.08, 19.075, 19.07,
              19.065, 19.06, 19.055, 19.05, 19.045, 19.04, 19.035, 19.03, 19.025, 19.02, 19.015,
              19.01, 19.005, 19.00],
        lngs=[72.90, 72.898, 72.896, 72.894, 72.892, 72.89, 72.889, 72.887, 72.885, 72.884, 72.882,
              72.881, 72.879, 72.877, 72.876, 72.874, 72.873, 72.871, 72.869, 72.868, 72.866, 72.865,
              72.863, 72.862, 72.860],
    ),
    decay_km=10.0,
    curves={
        "rain_intensity": [12, 16, 21, 26, 31, 35, 38, 40, 41, 40, 38, 36, 33, 31, 29, 27, 25, 23, 21, 19, 17, 15, 13, 11, 10],
        "rain_accumulation_3h": [22, 30, 43, 58, 76, 95, 113, 130, 144, 154, 160, 162, 160, 155, 147, 138, 129, 119, 109, 99, 90, 82, 74, 67, 61],
        "river_level_ratio": [0.50, 0.53, 0.56, 0.60, 0.65, 0.70, 0.76, 0.82, 0.88, 0.95, 1.02, 1.08, 1.12, 1.14, 1.13, 1.10, 1.05, 1.00, 0.95, 0.90, 0.85, 0.80, 0.75, 0.71, 0.67],
        "river_rate": [0.06, 0.10, 0.15, 0.20, 0.26, 0.32, 0.39, 0.46, 0.53, 0.59, 0.63, 0.64, 0.60, 0.52, 0.40, 0.26, 0.12, -0.02, -0.13, -0.22, -0.28, -0.30, -0.29, -0.26, -0.22],
        "soil_moisture": [0.31, 0.33, 0.35, 0.38, 0.41, 0.44, 0.46, 0.48, 0.49, 0.50, 0.50, 0.50, 0.49, 0.48, 0.47, 0.46, 0.45, 0.44, 0.43, 0.42, 0.41, 0.40, 0.39, 0.38, 0.37],
        "wind_speed": [16, 17, 19, 21, 23, 25, 26, 27, 28, 28, 28, 27, 26, 25, 24, 23, 22, 21, 20, 19, 18, 17, 16, 15, 15],
        "wind_gust": [24, 27, 30, 34, 38, 42, 45, 48, 50, 51, 51, 50, 48, 45, 42, 39, 37, 34, 32, 30, 28, 27, 25, 24, 23],
        "forecast_rain_3h": [28, 38, 50, 64, 79, 94, 108, 120, 130, 137, 141, 141, 137, 130, 121, 111, 100, 90, 81, 73, 66, 59, 53, 48, 44],
        "cloud_top_temp_k": [256, 252, 248, 244, 240, 236, 233, 230, 228, 226, 226, 228, 231, 235, 240, 245, 250, 255, 259, 263, 266, 269, 271, 273, 275],
        "lightning_rate": [1, 2, 3, 5, 6, 8, 9, 10, 11, 11, 10, 9, 8, 6, 5, 4, 3, 2, 2, 1, 1, 0, 0, 0, 0],
        "temperature_c": [28, 28, 27, 27, 26, 26, 25, 25, 24, 24, 24, 24, 24, 25, 25, 25, 26, 26, 26, 27, 27, 27, 28, 28, 28],
        "humidity": [84, 86, 88, 90, 92, 93, 94, 95, 96, 96, 96, 95, 95, 94, 93, 92, 91, 90, 89, 88, 87, 86, 85, 84, 83],
        "pressure_hpa": [1001, 1000, 999, 998, 997, 996, 995, 994, 993, 992, 992, 992, 993, 994, 995, 996, 997, 998, 999, 1000, 1001, 1002, 1003, 1003, 1004],
        "tide_level_m": [0.8, 1.0, 1.3, 1.7, 2.1, 2.6, 3.1, 3.6, 4.0, 4.3, 4.5, 4.5, 4.3, 4.0, 3.6, 3.1, 2.6, 2.1, 1.7, 1.3, 1.0, 0.8, 0.7, 0.7, 0.8],
        "surge_m": [0.0] * 25,
    },
    narrative="Risk escalates as the Mithi crosses danger around tick 15 and overflows between Dharavi and BKC while the tide holds storm water back at the Mahim outfall.",
    expected_peak_tick=15,
)


MUMBAI_COMPOUND = ScenarioDefinition(
    id="mumbai_compound",
    name="Mumbai — compound flood (rain + surge + Mithi)",
    description="Worst case: intense rain, a storm-surge push at the coast, the Mithi overflowing and a high tide — a true compound flood across Kurla, BKC and Sion. Exercises the compound-risk logic to its limit.",
    hazard_focus=["coastal_flood", "flood", "urban_flood", "severe_wind"],
    focus_location_id="loc_bkc",
    tick_minutes=15,
    total_ticks=24,
    epicentre=EpicentreTrack(
        lats=[19.06, 19.06, 19.06, 19.065, 19.065, 19.07, 19.07, 19.07, 19.07, 19.07, 19.07,
              19.065, 19.065, 19.06, 19.06, 19.06, 19.06, 19.055, 19.055, 19.05, 19.05, 19.05,
              19.045, 19.045, 19.04],
        lngs=[72.86, 72.865, 72.87, 72.87, 72.875, 72.875, 72.88, 72.88, 72.88, 72.885, 72.885,
              72.885, 72.885, 72.885, 72.88, 72.88, 72.88, 72.875, 72.875, 72.875, 72.87, 72.87,
              72.87, 72.865, 72.865],
    ),
    decay_km=12.0,
    curves={
        "rain_intensity": [10, 15, 21, 28, 36, 44, 51, 56, 59, 60, 58, 54, 48, 41, 34, 28, 22, 18, 15, 13, 11, 10, 9, 8, 7],
        "rain_accumulation_3h": [20, 30, 45, 65, 90, 118, 149, 180, 208, 232, 250, 262, 268, 267, 259, 246, 227, 206, 184, 163, 143, 126, 111, 98, 87],
        "river_level_ratio": [0.48, 0.50, 0.54, 0.58, 0.63, 0.68, 0.74, 0.80, 0.86, 0.92, 0.98, 1.03, 1.07, 1.09, 1.08, 1.05, 1.00, 0.95, 0.90, 0.85, 0.81, 0.77, 0.73, 0.70, 0.67],
        "river_rate": [0.05, 0.09, 0.14, 0.20, 0.26, 0.33, 0.40, 0.47, 0.54, 0.59, 0.62, 0.62, 0.58, 0.49, 0.37, 0.23, 0.08, -0.05, -0.15, -0.22, -0.26, -0.27, -0.26, -0.23, -0.19],
        "soil_moisture": [0.30, 0.31, 0.34, 0.37, 0.40, 0.44, 0.47, 0.50, 0.52, 0.54, 0.55, 0.55, 0.55, 0.54, 0.53, 0.52, 0.50, 0.49, 0.48, 0.46, 0.45, 0.44, 0.43, 0.42, 0.41],
        "wind_speed": [22, 27, 33, 40, 48, 56, 64, 71, 76, 79, 79, 77, 72, 66, 58, 50, 43, 37, 32, 28, 25, 23, 21, 20, 19],
        "wind_gust": [34, 42, 52, 64, 78, 92, 105, 116, 124, 128, 128, 124, 115, 104, 91, 79, 68, 58, 50, 44, 39, 35, 32, 30, 28],
        "forecast_rain_3h": [34, 48, 68, 92, 118, 146, 173, 198, 220, 236, 246, 249, 246, 236, 220, 199, 177, 155, 134, 116, 100, 86, 75, 66, 58],
        "cloud_top_temp_k": [250, 243, 236, 229, 222, 216, 211, 207, 204, 203, 204, 208, 214, 222, 231, 240, 248, 255, 261, 266, 270, 273, 275, 277, 278],
        "lightning_rate": [1, 3, 6, 11, 18, 26, 35, 43, 50, 55, 57, 56, 51, 43, 34, 24, 17, 11, 7, 5, 3, 2, 1, 1, 0],
        "temperature_c": [29, 28, 27, 26, 25, 24, 23, 23, 22, 22, 22, 23, 23, 24, 25, 25, 26, 26, 27, 27, 28, 28, 29, 29, 29],
        "humidity": [78, 82, 86, 90, 93, 95, 97, 98, 98, 98, 97, 96, 95, 94, 92, 91, 89, 88, 87, 86, 85, 84, 83, 82, 81],
        "pressure_hpa": [1000, 998, 995, 992, 989, 986, 984, 982, 981, 981, 983, 986, 990, 994, 997, 1000, 1002, 1004, 1005, 1006, 1007, 1007, 1008, 1008, 1009],
        "tide_level_m": [1.0, 1.4, 1.9, 2.5, 3.1, 3.7, 4.2, 4.6, 4.8, 4.9, 4.8, 4.6, 4.3, 3.9, 3.4, 3.0, 2.5, 2.1, 1.7, 1.4, 1.2, 1.0, 0.9, 1.0, 1.1],
        "surge_m": [0.05, 0.10, 0.18, 0.30, 0.46, 0.66, 0.90, 1.15, 1.40, 1.62, 1.78, 1.86, 1.85, 1.75, 1.56, 1.32, 1.05, 0.80, 0.58, 0.40, 0.26, 0.16, 0.10, 0.06, 0.04],
    },
    narrative="Four hazards compound at once: extreme rain, Mithi overflow, storm surge and high tide. PEHRA names the interactions rather than blindly adding numbers.",
    expected_peak_tick=11,
)


MUMBAI_HEATWAVE = ScenarioDefinition(
    id="mumbai_heatwave",
    name="Mumbai — heatwave",
    description="Dry north-northeast winds and low tide keep rain away while afternoon heat builds to a dangerous apparent temperature. Demonstrates that PEHRA is not flood-only.",
    hazard_focus=["heat"],
    focus_location_id="loc_borivali",
    tick_minutes=15,
    total_ticks=24,
    epicentre=EpicentreTrack(lats=[19.22] * 25, lngs=[72.86] * 25),
    decay_km=40.0,
    curves={
        "rain_intensity": [0] * 25,
        "rain_accumulation_3h": [0] * 25,
        "river_level_ratio": [0.28] * 25,
        "river_rate": [-0.01] * 25,
        "soil_moisture": [0.15, 0.15, 0.15, 0.14, 0.14, 0.14, 0.14, 0.14, 0.13, 0.13, 0.13, 0.13, 0.13, 0.13, 0.13, 0.14, 0.14, 0.14, 0.14, 0.15, 0.15, 0.15, 0.15, 0.15, 0.16],
        "wind_speed": [8, 8, 9, 10, 11, 11, 12, 13, 13, 13, 13, 13, 12, 12, 11, 11, 10, 10, 9, 9, 9, 8, 8, 7, 7],
        "wind_gust": [13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 22, 21, 20, 19, 18, 17, 16, 15, 14, 13, 13, 12, 12, 11, 11],
        "forecast_rain_3h": [0] * 25,
        "cloud_top_temp_k": [274] * 25,
        "lightning_rate": [0] * 25,
        "temperature_c": [36, 37, 38, 39, 40, 40, 41, 42, 42, 43, 43, 44, 44, 44, 44, 44, 43, 43, 42, 41, 41, 40, 39, 38, 37],
        "humidity": [30, 31, 33, 35, 37, 40, 42, 44, 46, 48, 50, 52, 53, 53, 52, 51, 49, 47, 45, 43, 41, 39, 37, 36, 35],
        "pressure_hpa": [1001, 1000, 1000, 999, 999, 999, 998, 998, 997, 997, 997, 996, 996, 996, 996, 997, 997, 998, 998, 999, 999, 1000, 1000, 1001, 1001],
        "tide_level_m": [0.8, 0.9, 1.1, 1.3, 1.6, 1.9, 2.2, 2.5, 2.8, 3.0, 3.1, 3.1, 3.0, 2.8, 2.5, 2.2, 1.9, 1.6, 1.3, 1.1, 0.9, 0.8, 0.8, 0.9, 1.0],
        "surge_m": [0.0] * 25,
    },
    narrative="Peak apparent temperature around tick 13. The hazard model switches to the heat definition and the citizen advice changes accordingly.",
    expected_peak_tick=13,
)


SCENARIOS: Dict[str, ScenarioDefinition] = {
    s.id: s
    for s in [
        MUMBAI_NORMAL,
        MUMBAI_HEAVY_RAIN,
        MUMBAI_CLOUDBURST,
        MUMBAI_HIGH_TIDE,
        MUMBAI_STORM_SURGE,
        MUMBAI_MITHI,
        MUMBAI_COMPOUND,
        MUMBAI_HEATWAVE,
    ]
}

DEFAULT_SCENARIO_ID = "mumbai_normal"


def get_scenario(scenario_id: str) -> ScenarioDefinition:
    return SCENARIOS.get(scenario_id, SCENARIOS[DEFAULT_SCENARIO_ID])


def scenario_field_at(
    scenario: ScenarioDefinition,
    tick: int,
    lat: float,
    lng: float,
) -> Dict[str, Optional[float]]:
    """Environmental forcing at (lat,lng) for a tick, after spatial decay.

    Returns None for any feature the scenario has declared unavailable at this
    tick -- missingness is a first-class citizen (Section 65).
    """
    elat, elng = scenario.epicentre.at(tick)
    dist = haversine_km(lat, lng, elat, elng)
    # gaussian-ish decay, floored so remote sites still see background weather
    decay = math.exp(-((dist / max(scenario.decay_km, 0.5)) ** 1.6))

    unavailable: Dict[str, str] = {}
    for outage in scenario.outages:
        if outage["from_tick"] <= tick <= outage["to_tick"]:
            unavailable[outage["feature"]] = outage["reason"]

    out: Dict[str, Optional[float]] = {}
    for feature, curve in scenario.curves.items():
        if feature.endswith("_dummy"):
            continue
        if feature in unavailable:
            out[feature] = None
            continue
        peak = _sample_curve(curve, tick)
        baseline = float(curve[0])
        if feature == "tide_level_m":
            # Tides are a regional phenomenon, not a local storm cell: every
            # gauge within the bay sees the same stage, so no spatial decay.
            out[feature] = peak
        elif feature in ("temperature_c", "pressure_hpa", "cloud_top_temp_k", "humidity",
                         "river_level_ratio", "soil_moisture"):
            # these are absolute states: decay towards the scenario baseline
            out[feature] = baseline + (peak - baseline) * decay
        else:
            # these are intensities: decay towards ~zero-ish background
            out[feature] = peak * (0.12 + 0.88 * decay)
    out["_distance_km"] = dist
    out["_decay"] = decay
    out["_unavailable"] = unavailable  # type: ignore[assignment]
    return out
