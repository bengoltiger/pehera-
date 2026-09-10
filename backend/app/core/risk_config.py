"""Tunable configuration for the PEHRA risk engine.

Everything the engine "believes" is declared here so it can be audited,
version-controlled and swapped. No magic numbers inside the engine itself.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Dict, List

# ---------------------------------------------------------------------------
# Risk levels (Section 8) -- never rely on colour alone: label + icon + text.
# ---------------------------------------------------------------------------
RISK_LEVELS: List[dict] = [
    {
        "key": "SAFE",
        "label": "Safe",
        "min": 0,
        "max": 20,
        "icon": "shield-check",
        "ascii": "OK",
        "color": "#22c55e",
        "colorblind_pattern": "solid",
        "explanation": "No significant hazard signal is present in the available data.",
        "action": "No action needed. Stay aware of official updates.",
    },
    {
        "key": "LOW",
        "label": "Low",
        "min": 21,
        "max": 40,
        "icon": "info",
        "ascii": "·",
        "color": "#3b82f6",
        "colorblind_pattern": "dots",
        "explanation": "Minor hazard signals detected but impact is unlikely.",
        "action": "Stay informed. No preparation required yet.",
    },
    {
        "key": "MODERATE",
        "label": "Moderate",
        "min": 41,
        "max": 60,
        "icon": "alert-circle",
        "ascii": "▲",
        "color": "#f5b942",
        "colorblind_pattern": "diagonal",
        "explanation": "Hazard conditions are developing and could affect this area.",
        "action": "Review your plan. Avoid unnecessary travel through low-lying roads.",
    },
    {
        "key": "HIGH",
        "label": "High",
        "min": 61,
        "max": 80,
        "icon": "alert-triangle",
        "ascii": "▲▲",
        "color": "#f97316",
        "colorblind_pattern": "cross",
        "explanation": "Dangerous conditions are likely in this area within the forecast horizon.",
        "action": "Move away from low-lying areas and water channels. Follow official instructions.",
    },
    {
        "key": "CRITICAL",
        "label": "Critical",
        "min": 81,
        "max": 100,
        "icon": "siren",
        "ascii": "■■■",
        "color": "#ef4444",
        "colorblind_pattern": "hatch",
        "explanation": "Severe impact is expected. Immediate protective action is required.",
        "action": "Move to higher ground / safe shelter now and follow emergency instructions.",
    },
]


def level_for_score(score: float) -> dict:
    s = max(0.0, min(100.0, float(score)))
    for lvl in RISK_LEVELS:
        if s <= lvl["max"]:
            return lvl
    return RISK_LEVELS[-1]


# ---------------------------------------------------------------------------
# Momentum bands (Section 9): change in risk points per hour.
# ---------------------------------------------------------------------------
MOMENTUM_BANDS: List[dict] = [
    {"key": "RAPID_FALL", "label": "Rapidly decreasing", "arrow": "↓", "min": -1e9, "max": -18.0},
    {"key": "FALLING", "label": "Decreasing", "arrow": "↘", "min": -18.0, "max": -5.0},
    {"key": "STABLE", "label": "Stable", "arrow": "→", "min": -5.0, "max": 5.0},
    {"key": "RISING", "label": "Increasing", "arrow": "↗", "min": 5.0, "max": 18.0},
    {"key": "ACCELERATING", "label": "Accelerating", "arrow": "↑", "min": 18.0, "max": 1e9},
]


def momentum_for_rate(points_per_hour: float) -> dict:
    for band in MOMENTUM_BANDS:
        if band["min"] <= points_per_hour < band["max"]:
            return band
    return MOMENTUM_BANDS[2]


# ---------------------------------------------------------------------------
# Normalisation ranges. Each raw observation is mapped to 0..1 before mixing.
# ---------------------------------------------------------------------------
NORMALISATION: Dict[str, dict] = {
    # rainfall intensity mm/h -- 0 to 70 covers "nothing" to "cloudburst"
    "rain_intensity": {"min": 0.0, "max": 70.0, "unit": "mm/h", "curve": "sqrt"},
    # 3h accumulation mm
    "rain_accumulation_3h": {"min": 0.0, "max": 150.0, "unit": "mm", "curve": "linear"},
    # acceleration mm/h per hour. Only *increasing* rain adds risk, so the
    # range starts at zero: easing rainfall contributes nothing rather than
    # a spurious mid-range value.
    "rain_acceleration": {"min": 0.0, "max": 40.0, "unit": "mm/h²", "curve": "linear"},
    # river level as fraction of the gauge's declared danger level
    "river_level_ratio": {"min": 0.35, "max": 1.05, "unit": "×danger", "curve": "linear"},
    # river rise rate m/h -- falling water contributes nothing
    "river_rate": {"min": 0.0, "max": 0.85, "unit": "m/h", "curve": "linear"},
    # volumetric soil moisture fraction
    "soil_moisture": {"min": 0.12, "max": 0.50, "unit": "m³/m³", "curve": "linear"},
    # sustained wind km/h
    "wind_speed": {"min": 5.0, "max": 110.0, "unit": "km/h", "curve": "linear"},
    "wind_gust": {"min": 8.0, "max": 150.0, "unit": "km/h", "curve": "linear"},
    # forecast rainfall next 3h mm
    "forecast_rain_3h": {"min": 0.0, "max": 120.0, "unit": "mm", "curve": "sqrt"},
    # convective indicator from satellite: cloud-top brightness temp (K), colder = worse
    "cloud_top_temp_k": {"min": 200.0, "max": 275.0, "unit": "K", "curve": "inverse"},
    "lightning_rate": {"min": 0.0, "max": 55.0, "unit": "strikes/15min", "curve": "sqrt"},
    # heat risk is effectively zero below ~28 °C in this region
    "temperature_c": {"min": 28.0, "max": 48.0, "unit": "°C", "curve": "linear"},
    "humidity": {"min": 20.0, "max": 100.0, "unit": "%", "curve": "linear"},
    "pressure_hpa": {"min": 975.0, "max": 1015.0, "unit": "hPa", "curve": "inverse"},
    # static vulnerability descriptors 0..1 already
    "terrain_vulnerability": {"min": 0.0, "max": 1.0, "unit": "index", "curve": "linear"},
    "drainage_deficiency": {"min": 0.0, "max": 1.0, "unit": "index", "curve": "linear"},
    "population_density": {"min": 50.0, "max": 22000.0, "unit": "people/km²", "curve": "log"},
    "historical_similarity": {"min": 0.0, "max": 1.0, "unit": "index", "curve": "linear"},
}


# ---------------------------------------------------------------------------
# Hazard definitions (Section 46). Extensible: add a dict, get a hazard.
# Weights are applied to NORMALISED (0..1) features and are normalised to sum 1.
# ---------------------------------------------------------------------------
@dataclass
class HazardDefinition:
    key: str
    label: str
    icon: str
    unit_hint: str
    # feature -> weight for the HAZARD sub-score
    hazard_weights: Dict[str, float]
    # feature -> weight for the ENVIRONMENTAL VULNERABILITY sub-score
    vulnerability_weights: Dict[str, float]
    # feature -> weight for the TREND / MOMENTUM sub-score
    trend_weights: Dict[str, float]
    # feature -> weight for the FORECAST SEVERITY sub-score
    forecast_weights: Dict[str, float]
    # required inputs; missing ones reduce confidence (Section 65)
    required_features: List[str]
    citizen_language: Dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return asdict(self)


HAZARDS: Dict[str, HazardDefinition] = {
    "flood": HazardDefinition(
        key="flood",
        label="Flood",
        icon="waves",
        unit_hint="m above normal",
        hazard_weights={
            "rain_intensity": 0.30,
            "rain_accumulation_3h": 0.28,
            "river_level_ratio": 0.30,
            "soil_moisture": 0.12,
        },
        vulnerability_weights={
            "terrain_vulnerability": 0.55,
            "drainage_deficiency": 0.30,
            "soil_moisture": 0.15,
        },
        trend_weights={
            "rain_acceleration": 0.45,
            "river_rate": 0.45,
            "soil_moisture": 0.10,
        },
        forecast_weights={"forecast_rain_3h": 0.75, "cloud_top_temp_k": 0.25},
        required_features=[
            "rain_intensity",
            "rain_accumulation_3h",
            "river_level_ratio",
            "soil_moisture",
            "forecast_rain_3h",
        ],
        citizen_language={
            "what": "water may rise quickly in low-lying places",
            "do": "move away from low-lying roads, drains and river banks",
        },
    ),
    "urban_flood": HazardDefinition(
        key="urban_flood",
        label="Urban flooding",
        icon="building",
        unit_hint="waterlogging depth",
        hazard_weights={
            "rain_intensity": 0.45,
            "rain_accumulation_3h": 0.35,
            "soil_moisture": 0.20,
        },
        vulnerability_weights={
            "drainage_deficiency": 0.60,
            "terrain_vulnerability": 0.30,
            "population_density": 0.10,
        },
        trend_weights={"rain_acceleration": 0.75, "soil_moisture": 0.25},
        forecast_weights={"forecast_rain_3h": 0.80, "cloud_top_temp_k": 0.20},
        required_features=["rain_intensity", "rain_accumulation_3h", "forecast_rain_3h"],
        citizen_language={
            "what": "streets and underpasses may flood",
            "do": "avoid underpasses and waterlogged streets; do not drive through standing water",
        },
    ),
    "extreme_rain": HazardDefinition(
        key="extreme_rain",
        label="Extreme rainfall",
        icon="cloud-rain",
        unit_hint="mm/h",
        hazard_weights={"rain_intensity": 0.55, "rain_accumulation_3h": 0.45},
        vulnerability_weights={"terrain_vulnerability": 0.5, "drainage_deficiency": 0.5},
        trend_weights={"rain_acceleration": 1.0},
        forecast_weights={"forecast_rain_3h": 0.7, "cloud_top_temp_k": 0.3},
        required_features=["rain_intensity", "forecast_rain_3h"],
        citizen_language={
            "what": "very heavy rain is falling",
            "do": "stay indoors if possible and avoid travel",
        },
    ),
    "thunderstorm": HazardDefinition(
        key="thunderstorm",
        label="Thunderstorm",
        icon="zap",
        unit_hint="strikes/15min",
        hazard_weights={
            "lightning_rate": 0.45,
            "cloud_top_temp_k": 0.30,
            "wind_gust": 0.25,
        },
        vulnerability_weights={"population_density": 0.6, "terrain_vulnerability": 0.4},
        trend_weights={"rain_acceleration": 0.5, "pressure_hpa": 0.5},
        forecast_weights={"forecast_rain_3h": 0.5, "cloud_top_temp_k": 0.5},
        required_features=["lightning_rate", "cloud_top_temp_k"],
        citizen_language={
            "what": "lightning and squally winds are likely",
            "do": "go indoors, stay away from trees, poles and open ground",
        },
    ),
    "severe_wind": HazardDefinition(
        key="severe_wind",
        label="Severe wind",
        icon="wind",
        unit_hint="km/h",
        hazard_weights={"wind_gust": 0.60, "wind_speed": 0.40},
        vulnerability_weights={"population_density": 0.55, "terrain_vulnerability": 0.45},
        trend_weights={"pressure_hpa": 1.0},
        forecast_weights={"cloud_top_temp_k": 1.0},
        required_features=["wind_speed", "wind_gust"],
        citizen_language={
            "what": "strong winds may bring down branches, hoardings and power lines",
            "do": "secure loose objects and stay away from weak structures and trees",
        },
    ),
    "heat": HazardDefinition(
        key="heat",
        label="Extreme heat",
        icon="thermometer-sun",
        unit_hint="°C",
        hazard_weights={"temperature_c": 0.80, "humidity": 0.20},
        vulnerability_weights={"population_density": 0.7, "terrain_vulnerability": 0.3},
        trend_weights={"temperature_c": 1.0},
        forecast_weights={"temperature_c": 0.8, "humidity": 0.2},
        required_features=["temperature_c", "humidity"],
        citizen_language={
            "what": "dangerous heat and humidity are building up",
            "do": "drink water often, avoid the sun between 11:00 and 16:00, check on elderly neighbours",
        },
    ),
}


# ---------------------------------------------------------------------------
# Composite risk mix (Section 6/7).
#
#   severity = 100 · ( w_h·hazard + w_v·vulnerability + w_f·forecast )
#              + TREND_BONUS_MAX · trend
#
# Trend is deliberately additive rather than averaged in. At the peak of an
# event the rate of change is zero by definition; averaging trend in would drag
# a genuinely critical situation back down. Instead momentum *adds* up to
# TREND_BONUS_MAX points, which is also what makes an accelerating-but-not-yet-
# severe situation score higher than a static one (Section 9).
# ---------------------------------------------------------------------------
@dataclass
class CompositeWeights:
    hazard: float = 0.60
    vulnerability: float = 0.15
    forecast: float = 0.25
    trend_bonus_max: float = 12.0

    def normalised(self) -> Dict[str, float]:
        total = self.hazard + self.vulnerability + self.forecast
        return {
            "hazard": self.hazard / total,
            "vulnerability": self.vulnerability / total,
            "forecast": self.forecast / total,
            # expressed on the same 0..1 scale so the engine can treat all four
            # components uniformly; the bonus is applied as points, not a share.
            "trend": self.trend_bonus_max / 100.0,
        }


COMPOSITE = CompositeWeights()

# Overall risk = blend of the environmental severity index and exposure.
# Hazard dominates, exposure modulates. An empty valley can still be dangerous,
# but a dense settlement raises the operational priority.
OVERALL_MIX = {"severity": 0.72, "exposure": 0.28}

# Exposure sub-weights (Section 7)
EXPOSURE_WEIGHTS = {
    "population": 0.55,
    "critical_infrastructure": 0.27,
    "vulnerable_population": 0.18,
}

# ---------------------------------------------------------------------------
# Compound / multi-hazard interaction (Section 47).
#
# Compounding only happens ACROSS hazard families. flood / urban_flood /
# extreme_rain are three views of the same water event -- treating them as
# "multiple hazards" would double-count one driver. Wind, convection and heat
# are genuinely independent failure modes, so those combinations do compound.
#
# The bonus is scaled by the remaining headroom (100 - base), so a situation
# that is already near the top of the scale cannot be inflated past it.
# ---------------------------------------------------------------------------
HAZARD_FAMILIES = {
    "flood": "water",
    "urban_flood": "water",
    "extreme_rain": "water",
    "thunderstorm": "convective",
    "severe_wind": "wind",
    "heat": "thermal",
}

COMPOUND = {
    "secondary_damping": 0.30,
    "max_compound_bonus": 14.0,
    "secondary_min_severity": 35.0,
    "interactions": [
        {
            "pair": ["flood", "severe_wind"],
            "bonus": 7.0,
            "reason": "Flooding combined with strong wind slows rescue movement and increases structural damage.",
        },
        {
            "pair": ["urban_flood", "severe_wind"],
            "bonus": 6.0,
            "reason": "Waterlogged streets plus wind damage block evacuation routes with debris.",
        },
        {
            "pair": ["urban_flood", "thunderstorm"],
            "bonus": 6.0,
            "reason": "Waterlogged streets plus lightning create electrocution and drowning risk together.",
        },
        {
            "pair": ["flood", "thunderstorm"],
            "bonus": 5.0,
            "reason": "Lightning during a flood response endangers rescue crews working in the open.",
        },
        {
            "pair": ["severe_wind", "thunderstorm"],
            "bonus": 5.0,
            "reason": "Squall-line winds with intense lightning threaten power infrastructure on two fronts.",
        },
    ],
}

# ---------------------------------------------------------------------------
# Confidence model (Section 11 / 71).
# ---------------------------------------------------------------------------
# Confidence presentation bands. The backend owns these so the UI never invents
# its own thresholds for "high" or "low" confidence (Section 11, Section 96).
CONFIDENCE_BANDS = [
    {"key": "very_low", "label": "Very low confidence", "min": 0.0, "max": 34.9,
     "note": "Treat this as a weak indication only; verify with another source before acting."},
    {"key": "low", "label": "Low confidence", "min": 35.0, "max": 54.9,
     "note": "Inputs are incomplete, stale or disagreeing. The number may move sharply."},
    {"key": "moderate", "label": "Moderate confidence", "min": 55.0, "max": 74.9,
     "note": "Usable for planning, but keep monitoring for changes."},
    {"key": "high", "label": "High confidence", "min": 75.0, "max": 89.9,
     "note": "Inputs are complete and recent and the model agrees with the trend."},
    {"key": "very_high", "label": "Very high confidence", "min": 90.0, "max": 100.0,
     "note": "All required inputs are present, fresh and mutually consistent."},
]


def confidence_band(value: float) -> dict:
    """Return the band a confidence percentage falls into."""
    for band in CONFIDENCE_BANDS:
        if band["min"] <= value <= band["max"]:
            return band
    return CONFIDENCE_BANDS[-1] if value > 100 else CONFIDENCE_BANDS[0]


CONFIDENCE = {
    "components": {
        "data_quality": 0.32,
        "model_confidence": 0.30,
        "forecast_agreement": 0.20,
        "historical_support": 0.18,
    },
    # penalty per missing required feature (percentage points)
    "missing_feature_penalty": 9.0,
    "stale_penalty": 7.0,
    "floor": 22.0,
    "ceiling": 96.0,
    # Uncertainty grows as confidence falls and as the forecast horizon lengthens.
    "uncertainty_base": 3.0,
    "uncertainty_confidence_factor": 22.0,
    "uncertainty_horizon_factor": 1.6,  # extra ± per hour of horizon
    "fallback_confidence_multiplier": 0.78,
}

# ---------------------------------------------------------------------------
# Data freshness (Section 13). Seconds.
# ---------------------------------------------------------------------------
FRESHNESS = {
    "rainfall": {"fresh": 600, "aging": 1800, "stale": 3600},
    "weather": {"fresh": 900, "aging": 2700, "stale": 5400},
    "river": {"fresh": 1200, "aging": 3600, "stale": 7200},
    "satellite": {"fresh": 1800, "aging": 3600, "stale": 9000},
    "soil": {"fresh": 3600, "aging": 10800, "stale": 21600},
    "terrain": {"fresh": 31536000, "aging": 63072000, "stale": 94608000},
    "forecast": {"fresh": 3600, "aging": 7200, "stale": 14400},
    "default": {"fresh": 900, "aging": 3600, "stale": 7200},
}

DATA_QUALITY_GRADES = [
    {"key": "EXCELLENT", "label": "Excellent", "min": 90},
    {"key": "GOOD", "label": "Good", "min": 75},
    {"key": "FAIR", "label": "Fair", "min": 55},
    {"key": "POOR", "label": "Poor", "min": 30},
    {"key": "UNUSABLE", "label": "Unusable", "min": 0},
]

# ---------------------------------------------------------------------------
# Alert decision engine (Sections 20, 21, 48).
# ---------------------------------------------------------------------------
ALERTS = {
    "levels": ["WATCH", "WARNING", "CRITICAL"],
    "thresholds": {"WATCH": 41.0, "WARNING": 61.0, "CRITICAL": 81.0},
    # de-escalation needs a margin so alerts do not flap around a threshold
    "hysteresis": 6.0,
    # a rapid climb can trigger a WATCH even below the absolute threshold
    "momentum_trigger_points_per_hour": 20.0,
    "momentum_trigger_min_risk": 33.0,
    "min_confidence_to_recommend": 45.0,
    # anti-spam
    "cooldown_seconds": 900,
    "dedup_window_seconds": 3600,
    "update_instead_of_new_delta": 8.0,
    "max_active_per_location": 2,
    "resolve_below": 35.0,
    "resolve_sustained_seconds": 1800,
    "geofence_default_radius_km": 6.0,
}

# Recommended actions per hazard x severity (Section 29). AI-ASSISTED, not orders.
ACTION_LIBRARY: Dict[str, Dict[str, List[str]]] = {
    "flood": {
        "WATCH": [
            "Monitor low-lying roads and known waterlogging points",
            "Check upstream river gauge readings every 30 minutes",
            "Verify shelter readiness and contact lists",
        ],
        "WARNING": [
            "Notify vulnerable communities in low-lying wards",
            "Prepare evacuation transport and rescue resources",
            "Inspect drainage channels and remove blockages",
            "Position teams near bridges and causeways",
        ],
        "CRITICAL": [
            "Issue public warning through all channels",
            "Restrict access to causeways, riverbanks and flooded roads",
            "Activate response teams and open shelters",
            "Begin evacuation of the lowest-lying settlements",
            "Coordinate with upstream dam/barrage operators",
        ],
    },
    "urban_flood": {
        "WATCH": [
            "Deploy pump readiness checks at chronic waterlogging points",
            "Alert traffic control about vulnerable underpasses",
        ],
        "WARNING": [
            "Close vulnerable underpasses to traffic",
            "Dispatch de-watering pumps to priority points",
            "Warn residents of basement and ground-floor flooding",
        ],
        "CRITICAL": [
            "Issue public warning and stop non-essential movement",
            "Cut power to flooded low-lying feeders after safety checks",
            "Activate rescue boats for stranded residents",
            "Open community shelters on higher ground",
        ],
    },
    "extreme_rain": {
        "WATCH": ["Monitor rainfall radar and gauge trend", "Alert field teams to stand by"],
        "WARNING": [
            "Advise citizens to postpone non-essential travel",
            "Pre-position teams in the highest-intensity cells",
        ],
        "CRITICAL": [
            "Issue public warning to stay indoors",
            "Suspend outdoor work and public gatherings",
            "Activate emergency operations centre",
        ],
    },
    "thunderstorm": {
        "WATCH": ["Warn outdoor worksites and schools", "Check lightning arrestor status at key sites"],
        "WARNING": [
            "Advise the public to move indoors",
            "Suspend outdoor events and crane/scaffold work",
        ],
        "CRITICAL": [
            "Issue immediate take-shelter warning",
            "Halt outdoor operations and rail/overhead-line work",
            "Prepare for power interruptions",
        ],
    },
    "severe_wind": {
        "WATCH": ["Inspect hoardings, scaffolding and temporary structures"],
        "WARNING": [
            "Secure or remove loose structures and hoardings",
            "Warn residents of weak or temporary housing",
            "Alert power utility to line-fault response",
        ],
        "CRITICAL": [
            "Issue public warning to remain indoors",
            "Close parks, open grounds and hoarding-heavy corridors",
            "Deploy tree-clearing and line-repair crews",
        ],
    },
    "heat": {
        "WATCH": ["Publish hydration advisory", "Check water supply at public points"],
        "WARNING": [
            "Open cooling centres and shaded rest points",
            "Adjust outdoor work timings",
            "Alert hospitals to heat-illness preparedness",
        ],
        "CRITICAL": [
            "Issue public heat warning",
            "Suspend outdoor labour in peak hours",
            "Activate cooling centres and ambulance readiness",
            "Conduct welfare checks on elderly and isolated residents",
        ],
    },
}

# ---------------------------------------------------------------------------
# Threat cell detection (Section 17).
# ---------------------------------------------------------------------------
THREAT_CELLS = {
    "detection_risk_threshold": 45.0,
    "merge_distance_km": 9.0,
    "min_radius_km": 2.0,
    "max_radius_km": 18.0,
    "radius_per_risk_point_km": 0.16,
    "track_history_limit": 24,
    "dissipate_below": 32.0,
}

# Verification (Section 41)
VERIFICATION = {
    "event_threshold": 61.0,       # actual observed risk >= this counts as a real event
    "predicted_threshold": 61.0,   # predicted risk >= this counts as a positive prediction
    "correct_tolerance": 12.0,     # |predicted-actual| within this = "Correct"
}

DEFAULT_HORIZONS_MIN = [0, 30, 60, 120, 180, 360]
