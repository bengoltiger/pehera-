"""Live external atmospheric data — Open-Meteo (free, no API key).

PEHRA's risk engine is deliberately deterministic and simulated (that is the
honest position, and the whole product is labelled as such). This is the one
endpoint that talks to a real data source: it fetches what the atmosphere is
actually doing right now so the Predict screen can show live wind, rain and
temperature. The UI labels live values as LIVE and everything the engine
produces stays labelled SIMULATED.

Behaviour:
  * results are cached in memory for ``LIVE_CACHE_TTL`` seconds (weather at
    ward scale does not change on a 10-minute timescale, and the cache keeps
    the user's data usage low);
  * if the provider is unreachable the endpoint returns 503 with a reason,
    and the UI falls back to the clearly-labelled simulated radar.
"""
from __future__ import annotations

import math
import time
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, HTTPException, Query

from app.core.config import settings

router = APIRouter(tags=["live-data"])

LIVE_CACHE_TTL = 600  # seconds
GRID_N = 12  # 12x12 grid of wind vectors for the particle field
GRID_STEP_DEG = 0.05  # ~5 km at Pune's latitude

_cache: dict[tuple, tuple[float, dict]] = {}


def _fetch(url: str, params: dict) -> dict:
    try:
        res = httpx.get(url, params=params, timeout=12.0)
        res.raise_for_status()
        return res.json()
    except Exception as exc:  # noqa: BLE001 - provider failure is a normal state
        raise HTTPException(
            status_code=503,
            detail={
                "error": "provider_unreachable",
                "message": (
                    f"Open-Meteo could not be reached ({exc.__class__.__name__}). "
                    "The live atmospheric feed is offline — showing the simulated feed."
                ),
            },
        ) from exc


def _wind_to_uv(speed_kmh: float, direction_deg: float) -> tuple[float, float]:
    """Meteorological wind (direction it blows FROM) -> u/v in km/h.

    u = eastward component, v = northward component.
    """
    flow = math.radians((direction_deg + 180.0) % 360.0)
    return speed_kmh * math.sin(flow), speed_kmh * math.cos(flow)


def _hour_index(times: list[str], now: datetime, offset_seconds: int = 0) -> int:
    """Index of the last hourly slot that has started by `now` (UTC).

    Open-Meteo returns LOCAL wall-clock times (timezone=auto); convert each
    slot to UTC using the response's utc_offset_seconds before comparing.
    """
    offset = timedelta(seconds=offset_seconds)
    idx = 0
    for i, t in enumerate(times):
        slot_utc = datetime.fromisoformat(t).replace(tzinfo=timezone.utc) - offset
        if slot_utc <= now:
            idx = i
    return idx


@router.get(
    "/live/weather",
    summary="Live atmospheric data (Open-Meteo)",
    description=(
        "Real temperature, humidity, wind and precipitation for a point, plus a "
        "12×12 grid of wind vectors used to animate the wind-particle field on the "
        "Predict screen. Data: Open-Meteo (no key required). Cached server-side."
    ),
    responses={503: {"description": "Provider unreachable — UI falls back to simulated"}},
)
def live_weather(
    lat: float = Query(..., ge=-90, le=90, alias="lat"),
    lng: float = Query(..., ge=-180, le=180, alias="lng"),
    grid: int = Query(1, ge=0, le=1, description="1 = include the wind-vector grid"),
) -> dict:
    key = (round(lat, 3), round(lng, 3), grid)
    hit = _cache.get(key)
    now = time.time()
    if hit and now - hit[0] < LIVE_CACHE_TTL:
        return hit[1]

    url = settings.open_meteo_url
    point = _fetch(
        url,
        {
            "latitude": f"{lat:.4f}",
            "longitude": f"{lng:.4f}",
            "current": ",".join(
                [
                    "temperature_2m",
                    "relative_humidity_2m",
                    "wind_speed_10m",
                    "wind_direction_10m",
                    "precipitation",
                    "cloud_cover",
                ]
            ),
            "hourly": "temperature_2m,precipitation,wind_speed_10m,wind_direction_10m",
            "forecast_days": 2,  # 2 days so "next 12h" survives a late request hour
            "timezone": "auto",
        },
    )

    cur = point.get("current", {})
    times = point.get("hourly", {}).get("time", [])
    precip_h = point.get("hourly", {}).get("precipitation", [])
    ws_h = point.get("hourly", {}).get("wind_speed_10m", [])
    wd_h = point.get("hourly", {}).get("wind_direction_10m", [])
    offset_s = int(point.get("utc_offset_seconds", 0) or 0)
    now_utc = datetime.now(timezone.utc)
    i = _hour_index(times, now_utc, offset_s) if times else 0

    # next 3h rain = sum of the current + next two hourly slots
    next3 = [p for p in precip_h[i : i + 3] if p is not None]
    next12 = [
        {"time": times[j], "precip_mm": precip_h[j], "wind_kmh": ws_h[j], "wind_dir_deg": wd_h[j]}
        for j in range(i, min(len(times), i + 12))
    ]

    field = None
    if grid == 1:
        origin_lat = lat - (GRID_N / 2 - 0.5) * GRID_STEP_DEG
        origin_lng = lng - (GRID_N / 2 - 0.5) * GRID_STEP_DEG
        lats = [origin_lat + r * GRID_STEP_DEG for r in range(GRID_N)]
        lngs = [origin_lng + c * GRID_STEP_DEG for c in range(GRID_N)]
        grid_data = _fetch(
            url,
            {
                "latitude": ",".join(f"{a:.4f}" for a in lats for _ in lats),
                "longitude": ",".join(f"{b:.4f}" for b in lngs for _ in lats),
                "hourly": "wind_speed_10m,wind_direction_10m",
                "forecast_days": 1,
                "timezone": "auto",
            },
        )
        u: list[float] = []
        v: list[float] = []
        for loc in grid_data:
            gt = loc.get("hourly", {}).get("time", [])
            go = int(loc.get("utc_offset_seconds", 0) or 0)
            gi = _hour_index(gt, now_utc, go) if gt else 0
            gws = loc.get("hourly", {}).get("wind_speed_10m", [None] * max(1, len(gt)))
            gwd = loc.get("hourly", {}).get("wind_direction_10m", [None] * max(1, len(gt)))
            sp = gws[gi] if gi < len(gws) else None
            dd = gwd[gi] if gi < len(gwd) else None
            if sp is None or dd is None:
                u.append(0.0)
                v.append(0.0)
            else:
                uu, vv = _wind_to_uv(sp, dd)
                u.append(uu)
                v.append(vv)
        field = {
            "origin_lat": origin_lat,
            "origin_lng": origin_lng,
            "step_deg": GRID_STEP_DEG,
            "rows": GRID_N,
            "cols": GRID_N,
            "u": u,
            "v": v,
            "hour": times[i] if i < len(times) else None,
        }

    payload = {
        "provider": "open-meteo",
        "provider_url": "https://open-meteo.com/",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "ttl_seconds": LIVE_CACHE_TTL,
        "point": {
            "time": cur.get("time"),
            "temperature_c": cur.get("temperature_2m"),
            "humidity_pct": cur.get("relative_humidity_2m"),
            "wind_speed_kmh": cur.get("wind_speed_10m"),
            "wind_direction_deg": cur.get("wind_direction_10m"),
            "precipitation_mm": cur.get("precipitation"),
            "cloud_cover_pct": cur.get("cloud_cover"),
            "next_3h_rain_mm": round(sum(next3), 2) if next3 else None,
            "next_12h": next12,
        },
        "field": field,
        "note": (
            "Live global weather model data (Open-Meteo). Ward-level risk, river "
            "levels and shelter details on this screen remain PEHRA's simulated "
            "demo dataset."
        ),
    }
    _cache[key] = (now, payload)
    return payload
