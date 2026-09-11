"""Safe navigation: RoutingProvider abstraction (Sections MB-14, 29).

A route planner is an exchangeable component. The shipped implementation,
``HazardAwareRoutingProvider``, plans over a network derived from the same
corridor seed the traffic layer uses and scores every road sample against the
hazard field -- so a route is blocked/slowed *because* of the risk the command
centre sees, not decorated on top of it.

Honesty is structural here, not cosmetic:

  * the road network is a derived grid seeded by named Mumbai corridors, NOT an
    OSM export -- every payload states ``is_simulated: true`` and says so;
  * every route carries the provider key, so a future real router would not be
    silently substituted for the demo planner;
  * route responses are normalised per Section 29 (``route_id``, ``provider``,
    ``distance_m``, ``duration_s``, ``risk_score``, ``risk_level``,
    ``confidence``, ``hazard_factors``, ``geometry``, ``instructions``,
    ``last_evaluated_at``, ``data_mode``).

Dynamic re-route (Sections 10, 22): a stored route can be re-evaluated against
the current clock. When its risk level changes the planner publishes
``route.updated`` on the SSE bus so connected clients can be told to re-route.
"""
from __future__ import annotations

import abc
import datetime as dt
import heapq
import math
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.risk_config import ROUTING
from app.engine.risk_field import build_sites, hazard_at_point
from app.realtime.bus import bus
from app.services.clock import build_context, scenario_clock
from app.simulation.scenarios import haversine_km

# Re-export the corridor seed so the router and the traffic layer agree on what
# a "named road" is. Kept in sync with `traffic.py`.
CORRIDORS = [
    ("Western Express Hwy", 19.2290, 72.8550, 19.0178, 72.8478),
    ("Eastern Express Hwy", 19.1720, 72.9570, 19.0400, 72.8610),
    ("Sion Panvel Hwy", 19.0400, 72.8610, 19.0700, 73.0000),
    ("LBS Road", 19.0697, 72.8834, 19.1720, 72.9570),
    ("SV Road", 19.0178, 72.8478, 19.1200, 72.8480),
    ("Marine Drive", 18.9340, 72.8230, 18.9610, 72.8080),
    ("Goregaon-Mulund Link Rd", 19.1650, 72.8480, 19.1720, 72.9570),
    ("Vellard Flyover", 18.9930, 72.8360, 18.9380, 72.8290),
]

_SEV_BANDS = [
    (81, "CRITICAL", "You should not travel -- conditions are hazardous"),
    (61, "HIGH", "Dangerous -- proceed only if essential"),
    (41, "MODERATE", "Caution -- risk is elevated"),
    (21, "LOW", "Usable but watch steadily"),
    (0, "SAFE", "No significant hazard on this route"),
]


def severity_band(risk: Optional[float]) -> tuple[str, str]:
    for threshold, key, reason in _SEV_BANDS:
        if (risk or 0.0) >= threshold:
            return key, reason
    return "SAFE", "No significant hazard on this route"


@dataclass
class RoadSegment:
    id: str
    name: str
    a: Tuple[float, float]
    b: Tuple[float, float]
    distance_km: float
    severity: float = 0.0
    hazard: Optional[str] = None
    speed_kmh: float = 0.0


@dataclass
class RoutePlan:
    route_id: str
    provider_key: str
    provider_name: str
    from_: Tuple[float, float]
    to: Tuple[float, float]
    preference: str
    polyline: List[Tuple[float, float]]
    distance_m: float
    duration_s: float
    risk_score: float
    risk_level: str
    risk_reason: str
    confidence: float
    hazard_factors: List[dict]
    instructions: List[dict]
    last_evaluated_at: str
    weights: Dict[str, float]
    #: raw segments (kept for re-route diffing)
    segments: List[RoadSegment] = field(default_factory=list)

    def to_dict(self, db: Session, *, include_geometry: bool = True) -> dict:
        from_ = {"lat": round(self.from_[0], 5), "lng": round(self.from_[1], 5)}
        to = {"lat": round(self.to[0], 5), "lng": round(self.to[1], 5)}
        geometry = (
            {"type": "LineString",
             "coordinates": [[round(lat, 5), round(lng, 5)] for lat, lng in self.polyline]}
            if include_geometry else None
        )
        return {
            "route_id": self.route_id,
            "provider": {
                "key": self.provider_key,
                "name": self.provider_name,
                "kind": "demo",
                "mode": "SIMULATED",
            },
            "from": from_,
            "to": to,
            "preference": self.preference,
            "distance_m": round(self.distance_m, 1),
            "duration_s": int(round(self.duration_s)),
            "risk_score": round(self.risk_score, 1),
            "risk_level": self.risk_level,
            "risk_reason": self.risk_reason,
            "confidence": round(self.confidence, 1),
            "hazard_factors": self.hazard_factors,
            "instructions": self.instructions,
            "geometry": geometry,
            "last_evaluated_at": self.last_evaluated_at,
            "cost_weights": self.weights,
            "data_mode": {
                "is_simulated": True,
                "label": "SIMULATED route -- road layer derived from corridor seed, "
                         "not an OSM road network",
            },
            "clock": scenario_clock(db),
        }


class RoutingProvider(abc.ABC):
    """Exchangeable route planner.

    ``describe`` states what a provider is and what it is not. ``plan`` returns
    a normalised :class:`RoutePlan`. New providers (e.g. an OSM-backed router)
    implement this contract and are selected by key; the demo planner is never
    silently swapped for another.
    """

    key: str = "abstract"
    display_name: str = "Abstract router"
    version: str = "0.0"

    def describe(self) -> dict:
        return {
            "key": self.key,
            "name": self.display_name,
            "version": self.version,
            "is_simulated": True,
            "note": "See the provider's own describe() for honesty notes.",
        }

    @abc.abstractmethod
    def plan(self, db: Session, *, from_lat: float, from_lng: float,
             to_lat: float, to_lng: float, preference: str = "balanced") -> RoutePlan:
        ...

    def re_evaluate(self, db: Session, plan: RoutePlan) -> dict:
        """Re-score the stored route against the current hazard field.

        Returns a dict describing whether the route's risk level changed and,
        if it did, publishes ``route.updated`` on the SSE bus so connected
        clients can offer to re-route (Section 22).
        """
        ctx = build_context(db)
        from app.db.models import Location
        sites = build_sites(db.query(Location).all())
        worst = 0.0
        for seg in plan.segments:
            lat, lng = seg.a
            p = hazard_at_point(ctx, lat, lng, sites)
            seg.severity = p["severity"]
            seg.hazard = p["hazard"]
            worst = max(worst, p["severity"])
        new_level, new_reason = severity_band(worst)
        prev_level = plan.risk_level
        changed = new_level != prev_level
        if changed:
            bus.publish("route.updated", {
                "route_id": plan.route_id,
                "previous_level": plan.risk_level,
                "risk_level": new_level,
                "risk_reason": new_reason,
                "recommendation": (
                    "re-route" if new_level in ("HIGH", "CRITICAL") else "continue"
                ),
                "message": (
                    f"Conditions on your route have changed to {new_level}. "
                    + (new_reason + "." if new_level in ("HIGH", "CRITICAL")
                       else " No action needed yet.")
                ),
            })
        plan.risk_level, plan.risk_reason = new_level, new_reason
        plan.risk_score = worst
        plan.last_evaluated_at = _utc_now()
        return {
            "route_id": plan.route_id,
            "changed": changed,
            "previous_level": prev_level,
            "risk_level": new_level,
            "risk_reason": new_reason,
            "recommendation": "re-route" if new_level in ("HIGH", "CRITICAL") else "continue",
        }


class HazardAwareRoutingProvider(RoutingProvider):
    """Route planner over the hazard field (Sections MB-14, 29).

    Builds a road graph once per (scenario, tick) by overlaying a lattice on
    the Mumbai bounding box and naming edges after the nearest seeded corridor.
    Every edge is then scored by sampling ``hazard_at_point`` every
    ``ROUTING.sample_every_km`` km; cost weights implement the requested
    preference (fastest / balanced / safest).

    The lattice is *not* a real street map. The API says so in every response.
    """

    key = "hazard_aware"
    display_name = "PEHRA Hazard-Aware Router (demo)"
    version = "0.1"

    def __init__(self) -> None:
        self._graph: Optional[dict] = None
        self._graph_key: Optional[tuple] = None

    def describe(self) -> dict:
        d = super().describe()
        d["note"] = (
            "Road network is a lattice seeded by the Mumbai corridor list, not an "
            "OSM export. Segments are scored against the simulated hazard field; "
            "no real-time traffic or road closure feed is used."
        )
        d["weights"] = ROUTING["preferences"]
        d["sample_every_km"] = ROUTING["sample_every_km"]
        return d

    # ------------------------------------------------------------------ graph
    def _bbox(self, locations) -> dict:
        lats = [l.latitude for l in locations]
        lngs = [l.longitude for l in locations]
        return {
            "min_lat": min(lats) - 0.06,
            "max_lat": max(lats) + 0.06,
            "min_lng": min(lngs) - 0.06,
            "max_lng": max(lngs) + 0.06,
        }

    def _node_id(self, i: int, j: int) -> Tuple[int, int]:
        return (i, j)

    def _nearest_corridor(self, lat: float, lng: float,
                          max_km: float = 6.0) -> Optional[Tuple[str, float]]:
        best: Optional[Tuple[str, float]] = None
        for name, a_lat, a_lng, b_lat, b_lng in CORRIDORS:
            d = _point_segment_km(lat, lng, a_lat, a_lng, b_lat, b_lng)
            if best is None or d < best[1]:
                best = (name, d)
        if best and best[1] <= max_km:
            return best
        return None

    def _graph_for(self, db: Session, ctx) -> dict:
        from app.db.models import Location

        key = (ctx.scenario_id, ctx.tick)
        if self._graph and self._graph_key == key:
            return self._graph

        locations = db.query(Location).all()
        bbox = self._bbox(locations)
        sites = build_sites(locations)

        # lattice spacing ~2 km in both axes
        step_lat = 0.022
        n_lat = int((bbox["max_lat"] - bbox["min_lat"]) / step_lat) + 1
        n_lng = int((bbox["max_lng"] - bbox["min_lng"]) / step_lat) + 1
        lat_of = [bbox["min_lat"] + i * step_lat for i in range(n_lat)]
        lng_of = [bbox["min_lng"] + j * step_lat for j in range(n_lng)]

        # nodes: only lattice points that sit within 5 km of a corridor keep a
        # road name; others are still passable (secondary streets)
        nodes: List[tuple] = []
        idx: Dict[Tuple[int, int], int] = {}
        segs: Dict[Tuple[int, int], List[dict]] = {}
        for i in range(n_lat):
            for j in range(n_lng):
                lat, lng = lat_of[i], lng_of[j]
                if not (bbox["min_lat"] <= lat <= bbox["max_lat"] and
                        bbox["min_lng"] <= lng <= bbox["max_lng"]):
                    continue
                idx[(i, j)] = len(nodes)
                nodes.append((lat, lng))
                segs[(i, j)] = []
        if not nodes:
            self._graph = {"nodes": [], "adj": {}, "names": {}}
            self._graph_key = key
            return self._graph

        adj: Dict[int, List[Tuple[int, float, RoadSegment]]] = {k: [] for k in range(len(nodes))}

        def edge_cost(a_pt, b_pt, name: str) -> RoadSegment:
            dist = haversine_km(a_pt[0], a_pt[1], b_pt[0], b_pt[1])
            # sample mid + ends
            worst, w_hz = 0.0, None
            n_pts = max(2, int(math.ceil(dist / max(ROUTING["sample_every_km"], 0.1))))
            for k in range(n_pts + 1):
                t = k / n_pts
                lat = a_pt[0] + (b_pt[0] - a_pt[0]) * t
                lng = a_pt[1] + (b_pt[1] - a_pt[1]) * t
                p = hazard_at_point(ctx, lat, lng, sites)
                if p["severity"] > worst:
                    worst = p["severity"]; w_hz = p["hazard"]
            if worst >= ROUTING["block_severity"]:
                speed = ROUTING["blocked_speed_kmh"]
            elif worst >= ROUTING["slow_severity"]:
                speed = ROUTING["slow_speed_kmh"]
            else:
                speed = ROUTING["free_speed_kmh"]
            return RoadSegment(
                id=f"seg_{str(uuid.uuid4())[:8]}",
                name=name, a=a_pt, b=b_pt, distance_km=dist,
                severity=worst, hazard=w_hz, speed_kmh=speed,
            )

        # connect right and down neighbours -- a conservative grid, so routes
        # never "teleport": each hop is a scored road segment.
        for i in range(n_lat):
            for j in range(n_lng):
                if (i, j) not in idx:
                    continue
                cur = idx[(i, j)]
                for (di, dj) in ((0, 1), (1, 0)):
                    nb = (i + di, j + dj)
                    if nb not in idx:
                        continue
                    nid = idx[nb]
                    nearest = self._nearest_corridor(
                        (lat_of[i] + lat_of[i + di]) / 2,
                        (lng_of[j] + lng_of[j + dj]) / 2,
                    )
                    name = nearest[0] if nearest else "local road"
                    seg = edge_cost(nodes[cur], nodes[nid], name)
                    d = seg.distance_km
                    adj[cur].append((nid, d, seg))
                    adj[nid].append((cur, d, seg))

        self._graph = {"nodes": nodes, "adj": adj, "names": {}}
        self._graph_key = key
        return self._graph

    def _snap(self, lat: float, lng: float, nodes: List[tuple]) -> int:
        best, bd = None, float("inf")
        for i, (a, b) in enumerate(nodes):
            d = haversine_km(lat, lng, a, b)
            if d < bd:
                bd, best = d, i
        return best

    # ---------------------------------------------------------------- planner
    def plan(self, db: Session, *, from_lat: float, from_lng: float,
             to_lat: float, to_lng: float, preference: str = "balanced") -> RoutePlan:
        if preference not in ROUTING["preferences"]:
            preference = "balanced"
        weights = dict(ROUTING["preferences"][preference])
        ctx = build_context(db)
        g = self._graph_for(db, ctx)
        nodes, adj = g["nodes"], g["adj"]
        if not nodes:
            raise ValueError("Routing network could not be built for this region")

        start = self._snap(from_lat, from_lng, nodes)
        goal = self._snap(to_lat, to_lng, nodes)

        def cost(seg: RoadSegment) -> float:
            time_s = (seg.distance_km / max(seg.speed_kmh, 1.0)) * 3600.0
            # blocked segments are effectively unusable under risk preferences
            risk_pen = seg.severity / 100.0 * 3600.0
            return (weights["time_s"] * time_s
                    + weights["risk"] * risk_pen
                    + weights["distance_km"] * seg.distance_km * 3600.0)

        dist: Dict[int, float] = {start: 0.0}
        prev: Dict[int, Tuple[int, float, RoadSegment]] = {}
        closed: set = set()
        heap = [(0.0, start)]
        while heap:
            d, u = heapq.heappop(heap)
            if u in closed:
                continue
            closed.add(u)
            if u == goal:
                break
            for v, _, seg in adj.get(u, []):
                if v in closed:
                    continue
                nd = d + cost(seg)
                if nd < dist.get(v, float("inf")):
                    dist[v] = nd
                    prev[v] = (u, seg.distance_km, seg)
                    heapq.heappush(heap, (nd, v))

        if goal not in dist:
            raise ValueError("No route found between the requested points")

        node_ids: List[int] = [goal]
        segs: List[RoadSegment] = []
        cur = goal
        while cur != start:
            parent, _dkm, seg = prev[cur]
            node_ids.append(parent)
            segs.append(seg)
            cur = parent
        node_ids.reverse()
        segs.reverse()

        poly = [nodes[i] for i in node_ids]
        distance_m = sum((s.distance_km * 1000.0) for s in segs)
        duration_s = sum((s.distance_km / max(s.speed_kmh, 1.0)) * 3600.0 for s in segs)
        worst = max((s.severity for s in segs), default=0.0)
        level, reason = severity_band(worst)

        hazards: Dict[str, float] = {}
        for s in segs:
            if s.hazard:
                hazards[s.hazard] = max(hazards.get(s.hazard, 0.0), s.severity)
        hazard_factors = [
            {"hazard": hz, "severity": round(sev, 1),
             "label": f"{hz.replace('_', ' ')} up to severity {round(sev, 1)}"}
            for hz, sev in sorted(hazards.items(), key=lambda t: -t[1])
        ][:3]

        # instructions: turn each named run into a "head along X for Y km"
        instructions: List[dict] = []
        run_name = None
        run_dist = 0.0
        for s in segs:
            if s.name != run_name:
                if run_name is not None:
                    instructions.append({
                        "index": len(instructions),
                        "text": f"Continue on {run_name} for {_fmt_km(run_dist)}",
                        "distance_m": round(run_dist * 1000.0, 1),
                        "road": run_name,
                    })
                run_name, run_dist = s.name, 0.0
            run_dist += s.distance_km
        if run_name is not None:
            instructions.append({
                "index": len(instructions),
                "text": f"Continue on {run_name} for {_fmt_km(run_dist)}",
                "distance_m": round(run_dist * 1000.0, 1),
                "road": run_name,
            })

        # confidence: how much of the route sits below the slow threshold
        free = sum(s.distance_km for s in segs if s.severity < ROUTING["slow_severity"])
        conf = 100.0 if not segs else free / sum(s.distance_km for s in segs) * 100.0

        return RoutePlan(
            route_id="rte_" + uuid.uuid4().hex[:10],
            provider_key=self.key,
            provider_name=self.display_name,
            from_=(from_lat, from_lng),
            to=(to_lat, to_lng),
            preference=preference,
            polyline=poly,
            distance_m=distance_m,
            duration_s=duration_s,
            risk_score=worst,
            risk_level=level,
            risk_reason=reason,
            confidence=conf,
            hazard_factors=hazard_factors,
            instructions=instructions,
            last_evaluated_at=_utc_now(),
            weights=weights,
            segments=segs,
        )


def _point_segment_km(px: float, py: float, ax: float, ay: float,
                      bx: float, by: float) -> float:
    """Distance in km from point to a great-circle segment (approximate, planar
    enough at Mumbai scale)."""
    # degrees -> km projected
    def to_kmx(lat, lng) -> Tuple[float, float]:
        return lat * 110.574, lng * 111.320 * math.cos(math.radians(lat))

    px, py = to_kmx(px, py)
    ax, ay = to_kmx(ax, ay)
    bx, by = to_kmx(bx, by)
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    cx, cy = ax + t * dx, ay + t * dy
    return math.hypot(px - cx, py - cy)


def _fmt_km(km: float) -> str:
    if km >= 1:
        return f"{km:.1f} km"
    return f"{int(round(km * 1000))} m"


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None).isoformat() + "Z"


_provider = HazardAwareRoutingProvider()


def get_provider(key: Optional[str] = None) -> RoutingProvider:
    if key and key != "hazard_aware":
        raise KeyError(f"Unknown routing provider '{key}'")
    return _provider


def providers() -> List[RoutingProvider]:
    return [_provider]