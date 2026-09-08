"""Alert decision, escalation, lifecycle and anti-fatigue engine.

Sections 20, 21, 22, 23, 24, 29, 30, 48.

Key principles enforced here:
  * an alert is *recommended* by AI and *issued* by a human (Section 30);
  * repeated conditions update an existing alert instead of spawning new ones;
  * every state change is logged as a transition row (audit trail).
"""
from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass
from typing import List, Optional

from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.core.risk_config import ACTION_LIBRARY, ALERTS, HAZARDS
from app.db.models import Alert, AlertTransition, Location, new_id
from app.simulation.scenarios import haversine_km

LEVEL_ORDER = {"WATCH": 1, "WARNING": 2, "CRITICAL": 3}
ACTIVE_STATUSES = ("recommended", "pending_approval", "issued", "delivered",
                   "acknowledged", "updated", "escalated")


@dataclass
class TriggerEvaluation:
    should_alert: bool
    level: Optional[str]
    reasons: List[str]
    kinds: List[str]
    blocked_reason: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "should_alert": self.should_alert,
            "level": self.level,
            "reasons": self.reasons,
            "kinds": self.kinds,
            "blocked_reason": self.blocked_reason,
        }


def level_for_risk(risk: float) -> Optional[str]:
    t = ALERTS["thresholds"]
    if risk >= t["CRITICAL"]:
        return "CRITICAL"
    if risk >= t["WARNING"]:
        return "WARNING"
    if risk >= t["WATCH"]:
        return "WATCH"
    return None


def evaluate_triggers(
    *,
    risk: float,
    momentum_rate: float,
    confidence: float,
    prediction: dict,
    threat_cell_entering: bool = False,
    river_threshold_crossed: bool = False,
) -> TriggerEvaluation:
    """Decide whether the situation warrants an alert (Section 20).

    Several independent triggers exist; the highest resulting level wins.
    """
    reasons: List[str] = []
    kinds: List[str] = []
    level: Optional[str] = None

    threshold_level = level_for_risk(risk)
    if threshold_level:
        level = threshold_level
        kinds.append("risk_threshold")
        reasons.append(
            f"Risk {risk:.0f}/100 has crossed the {threshold_level} threshold "
            f"({ALERTS['thresholds'][threshold_level]:.0f})."
        )

    # rapid acceleration can justify a WATCH before the absolute threshold
    if (
        momentum_rate >= ALERTS["momentum_trigger_points_per_hour"]
        and risk >= ALERTS["momentum_trigger_min_risk"]
    ):
        kinds.append("rapid_acceleration")
        reasons.append(
            f"Risk is accelerating at {momentum_rate:+.0f} points/hour, which warrants attention "
            "before the absolute threshold is reached."
        )
        if level is None:
            level = "WATCH"

    peak = prediction.get("peak") or {}
    if peak.get("available") and peak.get("risk", 0) >= ALERTS["thresholds"]["CRITICAL"]:
        kinds.append("forecast_escalation")
        reasons.append(
            f"The projected peak of {peak['risk']:.0f}/100 in ~{peak['in_minutes']} minutes exceeds "
            "the CRITICAL threshold."
        )
        if level is None or LEVEL_ORDER[level] < LEVEL_ORDER["WARNING"]:
            level = "WARNING"

    if river_threshold_crossed:
        kinds.append("river_threshold")
        reasons.append("River level has crossed its declared danger level.")
        if level is None or LEVEL_ORDER[level] < LEVEL_ORDER["WARNING"]:
            level = "WARNING"

    if threat_cell_entering:
        kinds.append("geofence_entry")
        reasons.append("A tracked threat cell is projected to move into this populated zone.")
        if level is None:
            level = "WATCH"

    if level is None:
        return TriggerEvaluation(False, None, ["No trigger condition is met."], [])

    if confidence < ALERTS["min_confidence_to_recommend"]:
        return TriggerEvaluation(
            False,
            level,
            reasons,
            kinds,
            blocked_reason=(
                f"Confidence is only {confidence:.0f}%, below the {ALERTS['min_confidence_to_recommend']:.0f}% "
                "minimum required to recommend an alert. PEHRA will keep monitoring instead of "
                "issuing a low-confidence warning."
            ),
        )

    return TriggerEvaluation(True, level, reasons, kinds)


def dedup_key(location_id: str, hazard: str) -> str:
    return f"{location_id}:{hazard}"


def find_active_alert(db: Session, location_id: str, hazard: str) -> Optional[Alert]:
    return (
        db.query(Alert)
        .filter(
            and_(
                Alert.location_id == location_id,
                Alert.hazard == hazard,
                Alert.status.in_(ACTIVE_STATUSES),
            )
        )
        .order_by(Alert.created_at.desc())
        .first()
    )


def record_transition(
    db: Session,
    alert: Alert,
    *,
    to_status: str,
    to_level: Optional[str] = None,
    actor: str = "system",
    actor_role: str = "system",
    reason: str = "",
    at: Optional[dt.datetime] = None,
) -> AlertTransition:
    tr = AlertTransition(
        alert_id=alert.id,
        from_status=alert.status,
        to_status=to_status,
        from_level=alert.level,
        to_level=to_level or alert.level,
        actor=actor,
        actor_role=actor_role,
        reason=reason,
        at=at or dt.datetime.now(dt.timezone.utc).replace(tzinfo=None),
    )
    db.add(tr)
    alert.status = to_status
    if to_level:
        alert.level = to_level
    return tr


# ---------------------------------------------------------------------------
# Message composition (Sections 23, 31)
# ---------------------------------------------------------------------------
def compose_alert_content(
    *, location: Location, prediction: dict, level: str, hazard_key: str, triggers: TriggerEvaluation
) -> dict:
    hz = HAZARDS.get(hazard_key)
    hazard_label = hz.label if hz else hazard_key
    risk = prediction["risk"]["overall"]
    conf = prediction["risk"]["confidence"]["value"]
    peak = prediction.get("peak") or {}
    expl = prediction.get("explanation", [])

    when = "Conditions are already at this level."
    if peak.get("available"):
        when = f"Expected to peak within about {peak['in_minutes']} minutes."
    dw = prediction.get("decision_window") or {}
    if dw.get("available") and dw.get("minutes"):
        when = f"Risk is projected to reach critical levels in about {dw['minutes']} minutes."

    why_bits = [e["text"] for e in expl[:3]]
    why = " ".join(why_bits) if why_bits else "Environmental conditions have crossed configured thresholds."

    actions = ACTION_LIBRARY.get(hazard_key, {}).get(level, [])
    citizen_do = prediction["narrative"]["what_to_do"] if prediction.get("narrative") else ""

    title = f"{level} — {hazard_label} risk in {location.name}"
    message = (
        f"{level}: {hazard_label} risk in {location.name} is {risk:.0f}/100 "
        f"(confidence {conf:.0f}%). {prediction.get('narrative', {}).get('whats_happening', '')} "
        f"{when} {citizen_do}"
    ).strip()

    message_hi = ""
    if prediction.get("narrative"):
        hi = prediction["narrative"]["hi"]
        message_hi = (
            f"{level}: {location.name_hi or location.name} में जोखिम {risk:.0f}/100 है। "
            f"{hi['whats_happening']} {hi['whats_next']} {hi['what_to_do']}"
        )

    return {
        "title": title,
        "message": message,
        "message_hi": message_hi,
        "what": f"{hazard_label} risk",
        "where": f"{location.name}, {location.district}, {location.state}",
        "when": when,
        "why": why,
        "what_to_do": citizen_do or (hz.citizen_language.get("do") if hz else ""),
        "recommended_actions": actions,
        "confidence": conf,
    }


def estimate_exposed_population(
    db: Session, *, location: Location, geofence_kind: str, geofence: dict
) -> tuple[int, List[str]]:
    """Population inside a geofence (Section 24). Clearly an estimate."""
    if geofence_kind == "admin":
        return int(location.population), [location.id]

    if geofence_kind == "radius":
        radius = float(geofence.get("radius_km", ALERTS["geofence_default_radius_km"]))
        clat = float(geofence.get("lat", location.latitude))
        clng = float(geofence.get("lng", location.longitude))
        total = 0
        ids: List[str] = []
        for loc in db.query(Location).all():
            d = haversine_km(clat, clng, loc.latitude, loc.longitude)
            if d <= radius:
                total += loc.population
                ids.append(loc.id)
            else:
                # partial overlap: approximate by area intersection of the
                # location's footprint disc with the geofence disc
                loc_r = math.sqrt(max(loc.area_km2, 0.01) / math.pi)
                if d < radius + loc_r:
                    overlap = max(0.0, (radius + loc_r - d) / (2 * loc_r))
                    if overlap > 0.05:
                        total += int(loc.population * min(1.0, overlap))
                        ids.append(loc.id)
        return int(total), ids

    if geofence_kind == "polygon":
        poly = geofence.get("points") or []
        if len(poly) < 3:
            return int(location.population), [location.id]
        total, ids = 0, []
        for loc in db.query(Location).all():
            if _point_in_polygon(loc.latitude, loc.longitude, poly):
                total += loc.population
                ids.append(loc.id)
        return int(total), ids

    return int(location.population), [location.id]


def _point_in_polygon(lat: float, lng: float, poly: List[List[float]]) -> bool:
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        yi, xi = poly[i][0], poly[i][1]
        yj, xj = poly[j][0], poly[j][1]
        if ((yi > lat) != (yj > lat)) and (lng < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def validate_geofence(kind: str, geofence: dict) -> Optional[str]:
    """Geo-spatial validation before anything is drawn or stored (Section 98)."""
    if kind == "radius":
        try:
            lat = float(geofence.get("lat"))
            lng = float(geofence.get("lng"))
            r = float(geofence.get("radius_km", ALERTS["geofence_default_radius_km"]))
        except (TypeError, ValueError):
            return "Radius geofence requires numeric lat, lng and radius_km."
        if not (-90 <= lat <= 90):
            return f"Latitude {lat} is out of range (-90..90)."
        if not (-180 <= lng <= 180):
            return f"Longitude {lng} is out of range (-180..180)."
        if not (0.1 <= r <= 200):
            return f"Radius {r} km is out of range (0.1..200)."
        return None
    if kind == "polygon":
        pts = geofence.get("points") or []
        if len(pts) < 3:
            return "Polygon geofence requires at least 3 points."
        for p in pts:
            if len(p) != 2:
                return "Each polygon point must be [latitude, longitude]."
            if not (-90 <= float(p[0]) <= 90) or not (-180 <= float(p[1]) <= 180):
                return f"Polygon point {p} is outside valid WGS84 bounds."
        return None
    if kind == "admin":
        return None
    return f"Unknown geofence kind '{kind}'."


# ---------------------------------------------------------------------------
# Anti-fatigue (Section 48)
# ---------------------------------------------------------------------------
@dataclass
class DedupDecision:
    action: str  # "create" | "update" | "escalate" | "suppress"
    existing: Optional[Alert]
    reason: str


def decide_dedup(
    db: Session, *, location_id: str, hazard: str, level: str, risk: float, now: dt.datetime
) -> DedupDecision:
    existing = find_active_alert(db, location_id, hazard)
    if not existing:
        return DedupDecision("create", None, "No active alert exists for this location and hazard.")

    age = (now - (existing.updated_at or existing.created_at)).total_seconds()

    if LEVEL_ORDER[level] > LEVEL_ORDER[existing.level]:
        return DedupDecision(
            "escalate",
            existing,
            f"Existing {existing.level} alert escalates to {level} because risk reached {risk:.0f}.",
        )

    if LEVEL_ORDER[level] < LEVEL_ORDER[existing.level]:
        # de-escalate only past the hysteresis band, to stop flapping
        band = ALERTS["thresholds"][existing.level] - ALERTS["hysteresis"]
        if risk < band:
            return DedupDecision(
                "escalate",
                existing,
                f"Risk {risk:.0f} fell below {band:.0f} (threshold minus {ALERTS['hysteresis']:.0f} "
                f"hysteresis), so the alert de-escalates to {level}.",
            )
        return DedupDecision(
            "suppress",
            existing,
            f"Risk {risk:.0f} is still inside the hysteresis band of the active {existing.level} alert; "
            "no change issued to avoid flapping.",
        )

    if age < ALERTS["cooldown_seconds"]:
        delta = abs(risk - existing.risk_score)
        if delta < ALERTS["update_instead_of_new_delta"]:
            return DedupDecision(
                "suppress",
                existing,
                f"An active {existing.level} alert was updated {int(age / 60)} min ago and risk has moved "
                f"only {delta:.0f} points — inside the {ALERTS['cooldown_seconds'] // 60}-minute cooldown.",
            )
        return DedupDecision(
            "update",
            existing,
            f"Risk moved {delta:.0f} points; the existing alert is updated rather than duplicated.",
        )

    return DedupDecision(
        "update",
        existing,
        "An active alert already covers this location and hazard, so it is updated instead of duplicated.",
    )


def should_resolve(alert: Alert, risk: float, now: dt.datetime) -> Optional[str]:
    if alert.status in ("resolved", "cancelled", "expired"):
        return None
    if risk < ALERTS["resolve_below"]:
        return (
            f"Risk has fallen to {risk:.0f}/100, below the configured resolve threshold of "
            f"{ALERTS['resolve_below']:.0f}."
        )
    if alert.expires_at and now > alert.expires_at:
        return "The alert's validity period has expired."
    return None


def priority_score(*, risk: float, exposure: float, momentum_rate: float, confidence: float) -> dict:
    """Priority = Risk × Exposure × Urgency × Confidence (Sections 25, 26, 27)."""
    r = risk / 100.0
    e = 0.35 + 0.65 * (exposure / 100.0)
    urgency = 0.6 + 0.4 * max(0.0, min(1.0, (momentum_rate + 10) / 40.0))
    c = 0.55 + 0.45 * (confidence / 100.0)
    score = r * e * urgency * c * 100.0
    return {
        "score": round(score, 1),
        "factors": {
            "risk": round(r, 3),
            "exposure": round(e, 3),
            "urgency": round(urgency, 3),
            "confidence": round(c, 3),
        },
    }


def explain_priority(
    *, rank: int, risk: float, exposure_people: int, momentum_label: str,
    momentum_rate: float, confidence: float, hazard_label: str, location_name: str
) -> str:
    """Section 27 -- why is this at the top?"""
    bits = [f"Ranked #{rank}"]
    if risk >= 81:
        bits.append(f"risk is CRITICAL at {risk:.0f}/100")
    elif risk >= 61:
        bits.append(f"risk is HIGH at {risk:.0f}/100")
    else:
        bits.append(f"risk is {risk:.0f}/100")
    if momentum_rate >= 5:
        bits.append(f"and {momentum_label.lower()} at {momentum_rate:+.0f} points per hour")
    elif momentum_rate <= -5:
        bits.append(f"though it is {momentum_label.lower()}")
    bits.append(f"with an estimated {exposure_people:,} people inside the projected impact zone")
    bits.append(f"and {confidence:.0f}% confidence in the prediction")
    return (
        f"{bits[0]}: {' '.join(bits[1:])}. "
        f"{location_name} therefore outranks other {hazard_label.lower()} areas on the "
        "risk × exposure × urgency × confidence ordering."
    )
