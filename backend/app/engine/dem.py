"""Digital-elevation-model derived terrain intelligence (MB-3).

Mumbai's flood problem is mostly a *terrain* problem: large parts of the city
(Colaba, BKC, Sion, Kurla, Mahim) sit a few metres above sea level on flat,
reclaimed, poorly-drained ground. Elevation, slope and drainage must therefore
feed the risk engine directly -- not just render as a map colour.

The single derived quantity the engine trusts is ``flood_susceptibility``.
Every caller (provider, grid sampler, risk engine) uses this module so the
number can never disagree between the map and the model.
"""
from __future__ import annotations

import math


def elevation_danger(elevation_m: float) -> float:
    """Lower ground = closer to flood water. 0 m → 1.0, 60 m → ~0."""
    return max(0.0, min(1.0, 1.0 - max(0.0, float(elevation_m)) / 60.0))


def slope_danger(slope_deg: float) -> float:
    """Flat reclaimed ground ponds water; 0° → 1.0, 18° → ~0."""
    return max(0.0, min(1.0, 1.0 - max(0.0, float(slope_deg)) / 18.0))


def flood_susceptibility(elevation_m: float, slope_deg: float, drainage_deficiency: float) -> float:
    """Composite 0..1 DEM-derived flood susceptibility.

    Elevation dominates (low ground collects both rainfall and river water),
    slope is next (it controls whether water sheds or ponds), and deficient
    drainage is the urban multiplier that turns both into standing water.
    """
    e = elevation_danger(elevation_m)
    s = slope_danger(slope_deg)
    d = max(0.0, min(1.0, float(drainage_deficiency)))
    return round(0.40 * e + 0.30 * s + 0.30 * d, 4)


def terrain_snapshot(
    elevation_m: float,
    slope_deg: float,
    drainage_deficiency: float,
    coastal_exposure: float,
) -> dict:
    """Human-readable DEM breakdown for the 'why is this area high risk?'
    panel. The arithmetic here is the arithmetic the engine used."""
    sus = flood_susceptibility(elevation_m, slope_deg, drainage_deficiency)
    return {
        "elevation_m": round(elevation_m, 1),
        "slope_deg": round(slope_deg, 2),
        "drainage_deficiency": round(drainage_deficiency, 3),
        "coastal_exposure": round(coastal_exposure, 3),
        "flood_susceptibility": sus,
        "contributors": {
            "elevation": round(elevation_danger(elevation_m), 4),
            "slope": round(slope_danger(slope_deg), 4),
            "drainage": round(drainage_deficiency, 4),
        },
        "model": "0.40·elevation + 0.30·slope + 0.30·drainage",
    }