"""Threat-cell detection & tracking (Sections 17, 18).

A threat cell is a geographic concentration of risk. Cells are formed by
clustering high-risk locations, then matched frame-to-frame so that movement,
speed and bearing are *measured* from the cell's own history rather than
decorated onto the map.
"""
from __future__ import annotations

import datetime as dt
import math
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.risk_config import THREAT_CELLS, level_for_score
from app.db.models import ThreatCell, new_id
from app.simulation.scenarios import haversine_km


def _bearing(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lng2 - lng1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def _destination(lat: float, lng: float, bearing_deg: float, distance_km: float) -> Tuple[float, float]:
    r = 6371.0088
    br = math.radians(bearing_deg)
    p1, l1 = math.radians(lat), math.radians(lng)
    d = distance_km / r
    p2 = math.asin(math.sin(p1) * math.cos(d) + math.cos(p1) * math.sin(d) * math.cos(br))
    l2 = l1 + math.atan2(
        math.sin(br) * math.sin(d) * math.cos(p1), math.cos(d) - math.sin(p1) * math.sin(p2)
    )
    return round(math.degrees(p2), 6), round(math.degrees(l2), 6)


def compass(bearing: Optional[float]) -> str:
    if bearing is None:
        return "—"
    dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
            "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    return dirs[int((bearing + 11.25) % 360 / 22.5)]


def circle_polygon(lat: float, lng: float, radius_km: float, points: int = 24) -> List[List[float]]:
    return [
        list(_destination(lat, lng, i * (360.0 / points), radius_km)) for i in range(points)
    ]


def _cluster(points: List[dict], max_km: float) -> List[List[dict]]:
    """Single-linkage clustering on great-circle distance."""
    clusters: List[List[dict]] = []
    for p in sorted(points, key=lambda x: -x["risk"]):
        placed = False
        for c in clusters:
            if any(haversine_km(p["lat"], p["lng"], q["lat"], q["lng"]) <= max_km for q in c):
                c.append(p)
                placed = True
                break
        if not placed:
            clusters.append([p])
    return clusters


def detect_and_track(
    db: Session,
    *,
    location_risks: List[dict],
    field_points: Optional[List[dict]] = None,
    now: dt.datetime,
    tick: int,
    tick_minutes: int,
) -> List[ThreatCell]:
    """Detect and track threat cells.

    `field_points` are gridded hazard samples (see engine.risk_field). When
    present the cell centroid is computed from the continuous hazard field,
    which is what allows movement to be *measured*: discrete ward centroids
    cannot move, a sampled field can.

    `location_risks` items: {location_id, name, lat, lng, risk, predicted_risk,
    hazard, confidence, population}.
    """
    threshold = THREAT_CELLS["detection_risk_threshold"]

    if field_points:
        seeds = [
            {"lat": p["lat"], "lng": p["lng"], "risk": p["severity"], "hazard": p["hazard"]}
            for p in field_points
            if p["severity"] >= threshold
        ]
        cluster_km = THREAT_CELLS["merge_distance_km"] * 0.65
    else:
        seeds = [
            {"lat": r["lat"], "lng": r["lng"], "risk": r["risk"], "hazard": r["hazard"]}
            for r in location_risks
            if r["risk"] >= threshold
        ]
        cluster_km = THREAT_CELLS["merge_distance_km"]

    # cluster per hazard so a wind cell and a flood cell never merge
    by_hazard: Dict[str, List[dict]] = {}
    for c in seeds:
        by_hazard.setdefault(c["hazard"], []).append(c)

    active_cells: List[ThreatCell] = (
        db.query(ThreatCell).filter(ThreatCell.status.in_(["active", "dissipating"])).all()
    )
    matched_ids: set[str] = set()
    result: List[ThreatCell] = []

    for hazard, pts in by_hazard.items():
        for cluster in _cluster(pts, cluster_km):
            # severity-squared weighting keeps the centroid on the core of the
            # cell rather than being dragged out by its weak fringe
            wsum = sum((p["risk"] - threshold + 1) ** 2 for p in cluster) or 1.0
            clat = sum(p["lat"] * (p["risk"] - threshold + 1) ** 2 for p in cluster) / wsum
            clng = sum(p["lng"] * (p["risk"] - threshold + 1) ** 2 for p in cluster) / wsum
            severity = max(p["risk"] for p in cluster)
            extent = max((haversine_km(clat, clng, p["lat"], p["lng"]) for p in cluster), default=0.0)
            radius = max(
                THREAT_CELLS["min_radius_km"],
                min(THREAT_CELLS["max_radius_km"],
                    extent + severity * THREAT_CELLS["radius_per_risk_point_km"] * 0.35),
            )
            # attach the monitored locations that fall inside the cell
            inside = [
                r for r in location_risks
                if haversine_km(clat, clng, r["lat"], r["lng"]) <= radius
            ]
            if inside:
                severity = max(severity, max(r["risk"] for r in inside))
                predicted = max((r.get("predicted_risk") or r["risk"]) for r in inside)
                conf = sum(r.get("confidence", 70.0) for r in inside) / len(inside)
            else:
                predicted = severity
                conf = 60.0
            cluster = inside or cluster  # for location_ids below

            # match to an existing cell of the same hazard
            best: Optional[ThreatCell] = None
            best_d = 1e9
            for cell in active_cells:
                if cell.id in matched_ids or cell.hazard != hazard:
                    continue
                d = haversine_km(clat, clng, cell.center_lat, cell.center_lng)
                if d < best_d and d <= THREAT_CELLS["merge_distance_km"] * 2.2:
                    best, best_d = cell, d

            if best is None:
                cell = ThreatCell(
                    id=new_id("cell"),
                    hazard=hazard,
                    center_lat=round(clat, 6),
                    center_lng=round(clng, 6),
                    radius_km=round(radius, 2),
                    polygon=circle_polygon(clat, clng, radius),
                    current_severity=round(severity, 1),
                    predicted_severity=round(predicted, 1),
                    severity_label=level_for_score(severity)["key"],
                    movement_bearing_deg=None,
                    movement_speed_kmh=None,
                    confidence=round(conf, 1),
                    status="active",
                    location_ids=[p["location_id"] for p in cluster if "location_id" in p],
                    track=[{"lat": round(clat, 6), "lng": round(clng, 6),
                            "at": now.isoformat() + "Z", "tick": tick,
                            "severity": round(severity, 1)}],
                    predicted_track=[],
                    first_detected_at=now,
                    last_updated_at=now,
                    scenario_tick=tick,
                )
                db.add(cell)
                result.append(cell)
                continue

            matched_ids.add(best.id)
            prev_lat, prev_lng = best.center_lat, best.center_lng
            dist = haversine_km(prev_lat, prev_lng, clat, clng)
            elapsed_h = max(tick_minutes, 1) / 60.0
            if dist >= 0.25:  # ignore centroid jitter
                best.movement_bearing_deg = round(_bearing(prev_lat, prev_lng, clat, clng), 1)
                best.movement_speed_kmh = round(dist / elapsed_h, 1)
            else:
                best.movement_speed_kmh = 0.0
            best.center_lat = round(clat, 6)
            best.center_lng = round(clng, 6)
            best.radius_km = round(radius, 2)
            best.polygon = circle_polygon(clat, clng, radius)
            best.current_severity = round(severity, 1)
            best.predicted_severity = round(predicted, 1)
            best.severity_label = level_for_score(severity)["key"]
            best.confidence = round(conf, 1)
            best.status = "active"
            best.location_ids = [p["location_id"] for p in cluster if "location_id" in p]
            track = list(best.track or [])
            track.append({"lat": round(clat, 6), "lng": round(clng, 6),
                          "at": now.isoformat() + "Z", "tick": tick,
                          "severity": round(severity, 1)})
            best.track = track[-THREAT_CELLS["track_history_limit"]:]
            best.predicted_track = _project(best, tick_minutes)
            best.last_updated_at = now
            best.scenario_tick = tick
            result.append(best)

    # cells that no longer have a cluster
    for cell in active_cells:
        if cell.id in matched_ids or cell in result:
            continue
        if cell.status == "active":
            cell.status = "dissipating"
            cell.last_updated_at = now
        else:
            cell.status = "resolved"
            cell.last_updated_at = now

    db.commit()
    for c in result:
        db.refresh(c)
    return result


def _project(cell: ThreatCell, tick_minutes: int) -> List[dict]:
    """Extrapolate the observed motion vector forward. Only produced when the
    cell has actually moved -- otherwise there is nothing to project."""
    if not cell.movement_speed_kmh or cell.movement_bearing_deg is None:
        return []
    out = []
    for minutes in (30, 60, 120):
        d = cell.movement_speed_kmh * (minutes / 60.0)
        lat, lng = _destination(cell.center_lat, cell.center_lng, cell.movement_bearing_deg, d)
        out.append({"lat": lat, "lng": lng, "in_minutes": minutes})
    return out


def cell_to_dict(cell: ThreatCell) -> dict:
    return {
        "id": cell.id,
        "hazard": cell.hazard,
        "center": {"lat": cell.center_lat, "lng": cell.center_lng},
        "radius_km": cell.radius_km,
        "polygon": cell.polygon,
        "current_severity": cell.current_severity,
        "predicted_severity": cell.predicted_severity,
        "severity_label": cell.severity_label,
        "movement": {
            "bearing_deg": cell.movement_bearing_deg,
            "compass": compass(cell.movement_bearing_deg),
            "speed_kmh": cell.movement_speed_kmh,
            "is_moving": bool(cell.movement_speed_kmh and cell.movement_speed_kmh > 0.5),
            "note": "Measured from the cell's own centroid history."
            if cell.movement_speed_kmh
            else "Cell is stationary or has only one observed position.",
        },
        "confidence": cell.confidence,
        "status": cell.status,
        "location_ids": cell.location_ids,
        "track": cell.track,
        "predicted_track": cell.predicted_track,
        "first_detected_at": cell.first_detected_at.isoformat() + "Z",
        "last_updated_at": cell.last_updated_at.isoformat() + "Z",
        "age_minutes": int((cell.last_updated_at - cell.first_detected_at).total_seconds() / 60),
    }
