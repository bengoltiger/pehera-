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

NORMAL_DAY = ScenarioDefinition(
    id="normal_day",
    name="Normal day",
    description="Baseline monsoon-season day. Light intermittent rain, rivers well below danger level. Used as the calm reference state.",
    hazard_focus=["flood"],
    focus_location_id="loc_sinhagad_road",
    tick_minutes=15,
    total_ticks=24,
    epicentre=EpicentreTrack(lats=[18.45] * 25, lngs=[73.82] * 25),
    decay_km=20.0,
    curves={
        "rain_intensity": [2, 3, 2, 4, 3, 2, 1, 2, 3, 4, 3, 2, 2, 3, 2, 1, 2, 3, 2, 2, 1, 2, 3, 2, 2],
        "rain_accumulation_3h": [6, 7, 7, 8, 9, 9, 8, 8, 9, 10, 10, 9, 8, 8, 9, 8, 7, 8, 8, 7, 7, 7, 8, 8, 7],
        "river_level_ratio": [0.42] * 25,
        "river_rate": [0.0, 0.01, 0.0, 0.01, 0.0, 0.0, -0.01, 0.0, 0.01, 0.01, 0.0, 0.0, 0.0, 0.01, 0.0, 0.0, 0.0, 0.0, 0.0, -0.01, 0.0, 0.0, 0.0, 0.0, 0.0],
        "soil_moisture": [0.24, 0.24, 0.25, 0.25, 0.25, 0.25, 0.24, 0.24, 0.25, 0.25, 0.25, 0.25, 0.24, 0.24, 0.25, 0.24, 0.24, 0.24, 0.25, 0.24, 0.24, 0.24, 0.25, 0.24, 0.24],
        "wind_speed": [11, 12, 10, 13, 12, 11, 10, 12, 13, 12, 11, 10, 11, 12, 11, 10, 11, 12, 11, 10, 10, 11, 12, 11, 10],
        "wind_gust": [18, 20, 17, 22, 20, 18, 16, 19, 21, 20, 18, 17, 18, 20, 18, 16, 18, 19, 18, 17, 16, 18, 19, 18, 17],
        "forecast_rain_3h": [8, 9, 8, 10, 9, 8, 7, 8, 9, 10, 9, 8, 8, 9, 8, 7, 8, 9, 8, 8, 7, 8, 9, 8, 8],
        "cloud_top_temp_k": [268] * 25,
        "lightning_rate": [0] * 25,
        "temperature_c": [26, 26, 27, 27, 28, 28, 29, 29, 29, 28, 28, 27, 27, 27, 26, 26, 26, 25, 25, 25, 25, 24, 24, 24, 24],
        "humidity": [78, 78, 77, 76, 75, 74, 73, 73, 74, 75, 76, 77, 78, 78, 79, 79, 80, 80, 81, 81, 82, 82, 82, 83, 83],
        "pressure_hpa": [1006] * 25,
    },
    narrative="Nothing significant is developing. PEHRA stays quiet — this demonstrates that the system does not cry wolf.",
    expected_peak_tick=None,
)


HEAVY_RAIN = ScenarioDefinition(
    id="heavy_rain",
    name="Heavy rain",
    description="A rain band builds over the western hills and drifts east. Intensity climbs steadily; rivers respond slowly.",
    hazard_focus=["extreme_rain", "flood"],
    focus_location_id="loc_sinhagad_road",
    tick_minutes=15,
    total_ticks=24,
    epicentre=EpicentreTrack(
        lats=[18.36, 18.36, 18.37, 18.37, 18.38, 18.38, 18.39, 18.40, 18.41, 18.41, 18.42, 18.43,
              18.43, 18.44, 18.44, 18.45, 18.45, 18.46, 18.46, 18.47, 18.47, 18.48, 18.48, 18.49, 18.49],
        lngs=[73.68, 73.69, 73.70, 73.71, 73.72, 73.73, 73.74, 73.75, 73.76, 73.77, 73.78, 73.79,
              73.80, 73.81, 73.82, 73.83, 73.84, 73.85, 73.86, 73.87, 73.88, 73.89, 73.90, 73.91, 73.92],
    ),
    decay_km=12.0,
    curves={
        "rain_intensity": [4, 7, 11, 16, 21, 26, 31, 36, 40, 43, 45, 46, 45, 42, 38, 33, 28, 23, 18, 14, 11, 8, 6, 5, 4],
        "rain_accumulation_3h": [10, 14, 21, 31, 43, 57, 72, 87, 101, 113, 123, 130, 134, 134, 131, 125, 116, 105, 93, 81, 70, 60, 52, 46, 41],
        "river_level_ratio": [0.44, 0.45, 0.46, 0.48, 0.50, 0.53, 0.56, 0.59, 0.62, 0.65, 0.68, 0.70, 0.72, 0.74, 0.75, 0.76, 0.76, 0.75, 0.74, 0.72, 0.70, 0.68, 0.65, 0.62, 0.60],
        "river_rate": [0.01, 0.02, 0.04, 0.06, 0.09, 0.11, 0.13, 0.14, 0.14, 0.13, 0.12, 0.10, 0.09, 0.07, 0.05, 0.03, 0.01, -0.01, -0.03, -0.05, -0.06, -0.07, -0.08, -0.09, -0.09],
        "soil_moisture": [0.26, 0.27, 0.28, 0.30, 0.32, 0.34, 0.36, 0.38, 0.40, 0.41, 0.42, 0.43, 0.44, 0.44, 0.44, 0.43, 0.42, 0.41, 0.40, 0.39, 0.38, 0.37, 0.36, 0.35, 0.34],
        "wind_speed": [14, 16, 18, 21, 23, 25, 27, 29, 30, 31, 31, 30, 29, 28, 26, 24, 22, 20, 18, 17, 16, 15, 14, 13, 13],
        "wind_gust": [22, 26, 30, 35, 39, 43, 47, 50, 52, 54, 54, 53, 51, 48, 45, 41, 37, 34, 31, 28, 26, 25, 23, 22, 21],
        "forecast_rain_3h": [18, 26, 36, 48, 60, 72, 82, 90, 95, 97, 96, 92, 85, 76, 66, 56, 47, 39, 32, 26, 22, 18, 15, 13, 12],
        "cloud_top_temp_k": [258, 253, 248, 243, 238, 233, 229, 226, 223, 221, 220, 220, 222, 225, 229, 233, 238, 243, 248, 252, 256, 259, 262, 264, 266],
        "lightning_rate": [0, 1, 2, 3, 5, 7, 9, 11, 12, 13, 13, 12, 11, 9, 7, 6, 4, 3, 2, 1, 1, 0, 0, 0, 0],
        "temperature_c": [27, 27, 26, 26, 25, 25, 24, 24, 23, 23, 23, 23, 23, 23, 24, 24, 24, 25, 25, 25, 26, 26, 26, 26, 27],
        "humidity": [80, 82, 84, 86, 88, 90, 92, 93, 94, 95, 95, 95, 94, 94, 93, 92, 91, 90, 89, 88, 87, 86, 85, 84, 84],
        "pressure_hpa": [1004, 1003, 1002, 1001, 1000, 999, 998, 997, 996, 995, 995, 995, 996, 997, 998, 999, 1000, 1001, 1002, 1003, 1003, 1004, 1004, 1005, 1005],
    },
    narrative="Rainfall intensity roughly doubles every 45 minutes for two hours, then decays. Watch the early-signal detector fire well before the peak.",
    expected_peak_tick=11,
)


URBAN_FLOOD = ScenarioDefinition(
    id="urban_flood",
    name="Urban flood",
    description="Short, extremely intense convective cell parks over a dense ward with poor drainage. Rivers barely respond — the danger is entirely drainage failure.",
    hazard_focus=["urban_flood", "extreme_rain"],
    focus_location_id="loc_katraj",
    tick_minutes=15,
    total_ticks=24,
    epicentre=EpicentreTrack(
        lats=[18.44, 18.44, 18.45, 18.45, 18.45, 18.45, 18.45, 18.45, 18.45, 18.45, 18.45, 18.45,
              18.46, 18.46, 18.46, 18.46, 18.47, 18.47, 18.47, 18.48, 18.48, 18.49, 18.49, 18.50, 18.50],
        lngs=[73.85, 73.85, 73.86, 73.86, 73.86, 73.86, 73.86, 73.86, 73.86, 73.87, 73.87, 73.87,
              73.87, 73.88, 73.88, 73.88, 73.89, 73.89, 73.90, 73.90, 73.91, 73.91, 73.92, 73.93, 73.93],
    ),
    decay_km=7.0,
    curves={
        "rain_intensity": [3, 6, 12, 22, 34, 46, 56, 63, 68, 70, 69, 64, 56, 46, 36, 27, 20, 14, 10, 7, 5, 4, 3, 3, 2],
        "rain_accumulation_3h": [8, 12, 21, 37, 58, 83, 108, 131, 150, 165, 174, 177, 174, 165, 152, 137, 121, 105, 91, 78, 67, 58, 50, 44, 39],
        "river_level_ratio": [0.40, 0.40, 0.41, 0.41, 0.42, 0.43, 0.44, 0.45, 0.47, 0.48, 0.49, 0.50, 0.51, 0.51, 0.52, 0.52, 0.51, 0.51, 0.50, 0.49, 0.48, 0.47, 0.46, 0.45, 0.44],
        "river_rate": [0.0, 0.01, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.06, 0.06, 0.05, 0.05, 0.04, 0.03, 0.02, 0.01, 0.0, -0.01, -0.02, -0.03, -0.03, -0.04, -0.04, -0.04, -0.04],
        "soil_moisture": [0.28, 0.29, 0.31, 0.34, 0.37, 0.40, 0.43, 0.45, 0.47, 0.48, 0.49, 0.49, 0.48, 0.47, 0.46, 0.45, 0.44, 0.42, 0.41, 0.40, 0.39, 0.38, 0.37, 0.36, 0.35],
        "wind_speed": [12, 14, 17, 21, 25, 29, 32, 34, 35, 35, 34, 32, 29, 26, 23, 20, 18, 16, 15, 14, 13, 12, 12, 11, 11],
        "wind_gust": [20, 24, 29, 36, 43, 50, 56, 60, 62, 62, 60, 56, 51, 45, 40, 35, 31, 28, 25, 23, 22, 20, 19, 19, 18],
        "forecast_rain_3h": [22, 34, 52, 74, 96, 115, 128, 134, 133, 126, 114, 99, 83, 68, 55, 44, 35, 28, 23, 19, 16, 14, 12, 11, 10],
        "cloud_top_temp_k": [255, 248, 240, 231, 222, 214, 208, 203, 200, 199, 200, 204, 210, 217, 225, 233, 240, 246, 251, 255, 258, 261, 263, 265, 266],
        "lightning_rate": [1, 3, 7, 14, 23, 33, 42, 49, 53, 54, 51, 45, 37, 29, 21, 15, 10, 7, 4, 3, 2, 1, 1, 0, 0],
        "temperature_c": [29, 28, 27, 26, 25, 24, 23, 23, 22, 22, 22, 22, 23, 23, 24, 24, 25, 25, 26, 26, 27, 27, 27, 28, 28],
        "humidity": [76, 79, 83, 87, 91, 94, 96, 97, 98, 98, 97, 96, 95, 94, 92, 91, 89, 88, 86, 85, 84, 83, 82, 81, 80],
        "pressure_hpa": [1005, 1004, 1002, 1000, 998, 996, 994, 992, 991, 990, 991, 992, 994, 996, 998, 1000, 1001, 1002, 1003, 1004, 1004, 1005, 1005, 1006, 1006],
    },
    narrative="Peak rainfall of ~70 mm/h over 90 minutes. Hazard is high but the river stays calm — this scenario proves PEHRA separates drainage risk from river risk.",
    expected_peak_tick=9,
)


RIVER_FLOOD = ScenarioDefinition(
    id="river_flood",
    name="River flood",
    description="Sustained upstream catchment rainfall drives the Mutha past its danger level. The default SIH demonstration scenario: 'Rapid Flood Risk Escalation'.",
    hazard_focus=["flood"],
    focus_location_id="loc_sinhagad_road",
    tick_minutes=15,
    total_ticks=24,
    epicentre=EpicentreTrack(
        lats=[18.40, 18.40, 18.41, 18.41, 18.42, 18.42, 18.43, 18.43, 18.44, 18.44, 18.44, 18.45,
              18.45, 18.45, 18.46, 18.46, 18.46, 18.47, 18.47, 18.47, 18.48, 18.48, 18.48, 18.49, 18.49],
        lngs=[73.74, 73.75, 73.76, 73.77, 73.78, 73.79, 73.79, 73.80, 73.81, 73.81, 73.82, 73.82,
              73.83, 73.83, 73.84, 73.84, 73.85, 73.85, 73.86, 73.86, 73.87, 73.87, 73.88, 73.88, 73.89],
    ),
    decay_km=16.0,
    curves={
        # Opens at 18 mm/h exactly as specified in Section 78.
        "rain_intensity": [18, 19, 21, 23, 25, 27, 29, 32, 35, 38, 41, 43, 45, 46, 47, 48, 48, 45, 40, 35, 30, 25, 21, 17, 14],
        "rain_accumulation_3h": [16, 20, 25, 31, 38, 46, 55, 65, 76, 87, 98, 109, 120, 130, 139, 147, 152, 153, 149, 141, 131, 120, 108, 96, 85],
        "river_level_ratio": [0.44, 0.45, 0.46, 0.48, 0.50, 0.53, 0.56, 0.60, 0.64, 0.69, 0.74, 0.80, 0.86, 0.92, 0.98, 1.04, 1.09, 1.10, 1.07, 1.03, 0.98, 0.92, 0.87, 0.82, 0.78],
        "river_rate": [0.02, 0.03, 0.05, 0.07, 0.10, 0.13, 0.16, 0.19, 0.23, 0.27, 0.31, 0.35, 0.38, 0.41, 0.43, 0.44, 0.42, 0.36, 0.25, 0.13, 0.00, -0.12, -0.22, -0.28, -0.32],
        "soil_moisture": [0.26, 0.27, 0.28, 0.30, 0.31, 0.33, 0.35, 0.36, 0.38, 0.40, 0.42, 0.43, 0.45, 0.46, 0.47, 0.48, 0.48, 0.48, 0.47, 0.46, 0.45, 0.44, 0.43, 0.42, 0.41],
        "wind_speed": [12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 22, 23, 23, 23, 22, 22, 21, 20, 19, 18, 17, 16, 15, 14],
        "wind_gust": [19, 21, 22, 24, 26, 27, 29, 31, 32, 34, 35, 36, 37, 37, 37, 36, 35, 34, 32, 30, 28, 27, 25, 24, 22],
        "forecast_rain_3h": [16, 20, 25, 31, 38, 46, 54, 61, 68, 74, 79, 82, 84, 84, 82, 79, 75, 68, 60, 52, 44, 37, 31, 26, 22],
        "cloud_top_temp_k": [262, 260, 258, 256, 253, 250, 247, 244, 241, 238, 235, 232, 229, 227, 225, 224, 224, 227, 231, 235, 239, 243, 247, 251, 255],
        "lightning_rate": [1, 1, 2, 2, 3, 3, 4, 5, 5, 6, 6, 7, 7, 7, 7, 6, 6, 5, 4, 4, 3, 2, 2, 1, 1],
        "temperature_c": [26, 26, 25, 25, 24, 24, 24, 23, 23, 23, 22, 22, 22, 23, 23, 23, 24, 24, 24, 25, 25, 25, 26, 26, 26],
        "humidity": [82, 84, 86, 88, 90, 91, 92, 93, 94, 95, 95, 96, 96, 95, 95, 94, 93, 92, 91, 90, 89, 88, 87, 86, 85],
        "pressure_hpa": [1003, 1002, 1001, 1000, 999, 998, 997, 996, 995, 994, 993, 993, 993, 994, 995, 996, 997, 998, 999, 1000, 1001, 1002, 1003, 1003, 1004],
    },
    # Section 65 demo: the upstream river gauge drops out for 45 minutes.
    outages=[
        {
            "feature": "river_level_ratio",
            "from_tick": 5,
            "to_tick": 7,
            "reason": "Upstream river gauge telemetry unavailable",
        },
        {
            "feature": "river_rate",
            "from_tick": 5,
            "to_tick": 7,
            "reason": "Upstream river gauge telemetry unavailable",
        },
    ],
    narrative="Starts at risk ≈32 (LOW) and escalates through MODERATE → HIGH → CRITICAL as the river crosses its danger level around tick 12. Includes a deliberate 45-minute gauge outage so you can watch confidence drop honestly.",
    expected_peak_tick=16,
)


EXTREME_WEATHER = ScenarioDefinition(
    id="extreme_weather",
    name="Extreme weather (compound)",
    description="Severe squall line: extreme rain, damaging wind, intense lightning and a rising river all at once. Exercises compound-risk logic.",
    hazard_focus=["flood", "severe_wind", "thunderstorm", "urban_flood"],
    focus_location_id="loc_pimpri",
    tick_minutes=15,
    total_ticks=24,
    epicentre=EpicentreTrack(
        lats=[18.55, 18.56, 18.57, 18.58, 18.59, 18.60, 18.61, 18.61, 18.62, 18.62, 18.63, 18.63,
              18.63, 18.64, 18.64, 18.64, 18.65, 18.65, 18.65, 18.66, 18.66, 18.66, 18.67, 18.67, 18.67],
        lngs=[73.72, 73.73, 73.74, 73.75, 73.76, 73.77, 73.78, 73.79, 73.80, 73.81, 73.82, 73.83,
              73.84, 73.85, 73.86, 73.87, 73.88, 73.89, 73.90, 73.91, 73.92, 73.93, 73.94, 73.95, 73.96],
    ),
    decay_km=18.0,
    curves={
        "rain_intensity": [8, 14, 22, 32, 42, 52, 60, 66, 70, 72, 71, 67, 61, 53, 45, 37, 30, 24, 19, 15, 12, 10, 8, 7, 6],
        "rain_accumulation_3h": [16, 26, 42, 64, 90, 118, 145, 168, 187, 200, 208, 210, 207, 199, 187, 173, 157, 141, 126, 112, 99, 88, 78, 70, 63],
        "river_level_ratio": [0.48, 0.51, 0.55, 0.59, 0.64, 0.69, 0.75, 0.80, 0.86, 0.91, 0.96, 1.00, 1.04, 1.07, 1.09, 1.10, 1.09, 1.07, 1.04, 1.01, 0.97, 0.93, 0.89, 0.85, 0.81],
        "river_rate": [0.06, 0.10, 0.15, 0.20, 0.26, 0.32, 0.38, 0.44, 0.50, 0.55, 0.59, 0.62, 0.63, 0.61, 0.55, 0.46, 0.34, 0.20, 0.05, -0.09, -0.20, -0.29, -0.35, -0.39, -0.41],
        "soil_moisture": [0.31, 0.33, 0.35, 0.38, 0.41, 0.43, 0.46, 0.48, 0.49, 0.50, 0.51, 0.52, 0.52, 0.52, 0.51, 0.51, 0.50, 0.49, 0.48, 0.47, 0.46, 0.45, 0.44, 0.43, 0.42],
        "wind_speed": [22, 28, 36, 45, 55, 65, 74, 81, 86, 89, 90, 88, 84, 78, 71, 63, 55, 48, 42, 37, 33, 30, 27, 25, 23],
        "wind_gust": [34, 43, 55, 69, 84, 99, 112, 122, 130, 134, 135, 132, 126, 117, 107, 95, 84, 74, 65, 57, 51, 46, 42, 39, 36],
        "forecast_rain_3h": [30, 45, 65, 88, 110, 128, 140, 146, 145, 138, 127, 113, 98, 84, 71, 60, 50, 42, 35, 30, 26, 22, 19, 17, 15],
        "cloud_top_temp_k": [250, 242, 233, 224, 215, 207, 201, 197, 194, 192, 192, 195, 200, 207, 215, 223, 231, 238, 244, 249, 253, 257, 260, 262, 264],
        "lightning_rate": [3, 7, 14, 23, 34, 44, 52, 57, 59, 58, 54, 47, 39, 31, 23, 17, 12, 8, 6, 4, 3, 2, 1, 1, 1],
        "temperature_c": [31, 30, 28, 27, 25, 24, 23, 22, 21, 21, 21, 21, 22, 22, 23, 24, 25, 25, 26, 27, 27, 28, 28, 29, 29],
        "humidity": [74, 78, 82, 87, 91, 94, 96, 97, 98, 98, 98, 97, 96, 95, 94, 92, 91, 89, 88, 87, 85, 84, 83, 82, 81],
        "pressure_hpa": [1002, 1000, 998, 995, 992, 989, 987, 985, 983, 982, 982, 984, 986, 989, 992, 995, 997, 999, 1001, 1002, 1003, 1004, 1005, 1005, 1006],
    },
    outages=[
        {
            "feature": "cloud_top_temp_k",
            "from_tick": 9,
            "to_tick": 11,
            "reason": "Satellite ingest gap during peak convection",
        }
    ],
    narrative="Four hazards interact. Compound risk exceeds any single hazard score, and PEHRA names the interaction instead of blindly adding numbers.",
    expected_peak_tick=10,
)


HEATWAVE = ScenarioDefinition(
    id="heatwave",
    name="Heatwave",
    description="Dry, hot air mass with rising humidity in the afternoon. Demonstrates that PEHRA is not flood-only.",
    hazard_focus=["heat"],
    focus_location_id="loc_daund",
    tick_minutes=15,
    total_ticks=24,
    epicentre=EpicentreTrack(lats=[18.46] * 25, lngs=[74.58] * 25),
    decay_km=40.0,
    curves={
        "rain_intensity": [0] * 25,
        "rain_accumulation_3h": [0] * 25,
        "river_level_ratio": [0.28] * 25,
        "river_rate": [-0.01] * 25,
        "soil_moisture": [0.14, 0.14, 0.14, 0.13, 0.13, 0.13, 0.13, 0.13, 0.12, 0.12, 0.12, 0.12, 0.12, 0.12, 0.12, 0.13, 0.13, 0.13, 0.13, 0.14, 0.14, 0.14, 0.14, 0.14, 0.15],
        "river_rate_dummy": [0] * 25,
        "wind_speed": [8, 8, 9, 9, 10, 10, 11, 11, 12, 12, 12, 12, 11, 11, 10, 10, 9, 9, 8, 8, 8, 7, 7, 7, 7],
        "wind_gust": [13, 13, 14, 15, 16, 17, 18, 18, 19, 20, 20, 19, 18, 17, 16, 15, 14, 14, 13, 13, 12, 12, 11, 11, 11],
        "forecast_rain_3h": [0] * 25,
        "cloud_top_temp_k": [274] * 25,
        "lightning_rate": [0] * 25,
        "temperature_c": [36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 46, 47, 47, 46, 46, 45, 44, 43, 42, 41, 40, 39, 38, 37],
        "humidity": [30, 31, 32, 33, 35, 37, 39, 41, 43, 45, 47, 49, 51, 52, 53, 53, 52, 51, 49, 47, 45, 43, 41, 39, 37],
        "pressure_hpa": [1001, 1001, 1000, 1000, 999, 999, 998, 998, 997, 997, 997, 996, 996, 996, 997, 997, 998, 998, 999, 999, 1000, 1000, 1001, 1001, 1002],
    },
    narrative="Peak apparent temperature around tick 13. The hazard model switches to the heat definition and the citizen advice changes accordingly.",
    expected_peak_tick=13,
)


SCENARIOS: Dict[str, ScenarioDefinition] = {
    s.id: s
    for s in [NORMAL_DAY, HEAVY_RAIN, URBAN_FLOOD, RIVER_FLOOD, EXTREME_WEATHER, HEATWAVE]
}

DEFAULT_SCENARIO_ID = "river_flood"


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
        if feature in ("temperature_c", "pressure_hpa", "cloud_top_temp_k", "humidity",
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
