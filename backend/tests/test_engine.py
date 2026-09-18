"""Risk-engine arithmetic invariants.

The headline property being protected: the composite severity index is exactly
the sum of the named per-feature contributions, so the explanation panel is the
arithmetic, not a decorative chart. Also: determinism (nothing is random) and
the exposure-modulates-never-invents rule.
"""
from __future__ import annotations

import math

import pytest

from app.core.risk_config import COMPOSITE, COMPOUND, OVERALL_MIX, level_for_score
from app.engine.risk_engine import (
    combine_overall,
    compute_compound,
    momentum,
    score_exposure,
    score_hazard,
)
from app.engine.normalise import normalise

# A flood hazard with all required inputs present, mid-strength.
FLOOD_NORM = {
    "rain_intensity": 0.65,
    "rain_accumulation_3h": 0.55,
    "river_level_ratio": 0.50,
    "soil_moisture": 0.45,
    "forecast_rain_3h": 0.60,
    "rain_acceleration": 0.30,
    "river_rate": 0.20,
    "terrain_vulnerability": 0.70,
    "drainage_deficiency": 0.60,
    "cloud_top_temp_k": 0.40,
}

FLOOD_RAW = {
    "rain_intensity": 40.0,
    "rain_accumulation_3h": 70.0,
    "river_level_ratio": 0.72,
    "soil_moisture": 0.31,
    "forecast_rain_3h": 55.0,
}


class _FakeLocation:
    def __init__(self, population=100_000, area_km2=10.0, vulnerable_population=10_000):
        self.population = population
        self.area_km2 = area_km2
        self.vulnerable_population = vulnerable_population


def _run_flood() -> dict:
    return score_hazard("flood", FLOOD_NORM, FLOOD_RAW).to_dict()


def test_flood_is_fully_computable():
    result = _run_flood()
    assert result["is_computable"] is True
    assert result["missing_required"] == []


def test_severity_equals_sum_of_contributions():
    result = _run_flood()
    computed = sum(c["points"] for c in result["contributions"])
    assert abs(computed - result["severity_index"]) < 0.5


def test_contributions_shares_sum_to_one():
    result = _run_flood()
    total_share = round(sum(c["share"] for c in result["contributions"]), 6)
    assert math.isclose(total_share, 1.0, rel_tol=1e-4)


def test_score_is_deterministic():
    a = _run_flood()
    b = score_hazard("flood", FLOOD_NORM, {**FLOOD_RAW}).to_dict()
    assert a == b


def test_missing_required_feature_reported_not_imputed():
    norm = {k: v for k, v in FLOOD_NORM.items() if k != "river_level_ratio"}
    result = score_hazard("flood", norm, {}).to_dict()
    assert "river_level_ratio" in result["missing_required"]


def test_exposure_modulates_but_never_invents():
    empty = _FakeLocation(population=50, area_km2=100.0, vulnerable_population=5)
    dense = _FakeLocation(population=400_000, area_km2=4.0, vulnerable_population=80_000)
    expose_empty = score_exposure(empty).score
    expose_dense = score_exposure(dense).score
    assert 0.0 <= expose_empty <= 100.0
    assert expose_dense > expose_empty
    assert combine_overall(0.0, expose_dense) == 0.0  # no exposure, no invented danger


def test_overall_is_severity_weighted_with_exposure():
    sev, exp = 80.0, 60.0
    expected = min(100.0, sev * (OVERALL_MIX["severity"] + OVERALL_MIX["exposure"] * (exp / 100.0)))
    assert math.isclose(combine_overall(sev, exp), expected, rel_tol=1e-3)


def test_compound_across_families_not_within():
    flood = score_hazard("flood", FLOOD_NORM, FLOOD_RAW)
    urban = score_hazard(
        "urban_flood", FLOOD_NORM, FLOOD_RAW
    )  # same water event family
    severe = score_hazard(
        "severe_wind",
        {
            "wind_gust": 0.9,
            "wind_speed": 0.8,
            "population_density": 0.5,
            "terrain_vulnerability": 0.5,
            "pressure_hpa": 0.4,
            "cloud_top_temp_k": 0.6,
        },
        {},
    )

    same_family = compute_compound([flood, urban])
    assert same_family.is_compound is False

    cross_family = compute_compound([flood, severe])
    assert cross_family.is_compound is True
    assert cross_family.compound_severity >= flood.severity_index


def test_compound_bonus_bounded_by_headroom():
    torn = score_hazard(
        "severe_wind",
        {
            "wind_gust": 0.99,
            "wind_speed": 0.98,
            "population_density": 0.9,
            "terrain_vulnerability": 0.9,
            "pressure_hpa": 0.9,
            "cloud_top_temp_k": 0.9,
        },
        {},
    )
    flood_high = score_hazard(
        "flood",
        {k: 0.95 for k in FLOOD_NORM},
        {k: 1.0 for k in FLOOD_RAW},
    )
    cp = compute_compound([flood_high, torn])
    assert cp.compound_severity <= 100.0
    assert cp.bonus <= COMPOUND["max_compound_bonus"]


def test_momentum_bands():
    rising = momentum(previous_risk=55.0, current_risk=65.0, minutes=30)
    assert rising["rate_per_hour"] == 20.0
    assert rising["band"] == "ACCELERATING"

    static = momentum(52.0, 53.0, 60)
    assert static["band"] == "STABLE"

    first = momentum(None, 40.0, 60)
    assert first["previous_risk"] is None
    assert first["note"].startswith("No earlier prediction")


def test_level_for_score_boundaries():
    assert level_for_score(0)["key"] == "SAFE"
    assert level_for_score(20)["key"] == "SAFE"
    assert level_for_score(21)["key"] == "LOW"
    assert level_for_score(41)["key"] == "MODERATE"
    assert level_for_score(61)["key"] == "HIGH"
    assert level_for_score(81)["key"] == "CRITICAL"
    assert level_for_score(100)["key"] == "CRITICAL"


def test_normalise_range_is_bounded():
    assert 0.0 <= normalise("rain_intensity", 0.0) <= 1.0
    assert 0.0 <= normalise("rain_intensity", 200.0) <= 1.0
    assert normalise("rain_intensity", 200.0) >= normalise("rain_intensity", 10.0)