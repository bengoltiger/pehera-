"""Citizen location registry + BLE peer relay (prototype CD-08, CD-12).

In-memory registry of the demo citizen personas that the authority watches on
its People screen. Each persona is a *fictional demo record* (see the honesty
note); no fix in here is a real-world position.

Transports
----------
* ``online``  -- the citizen app is heartbeating over the network;
* ``relay``   -- the app announced it lost the network and a *nearby PEHRA
  phone is forwarding its last known fix over Bluetooth* (SIMULATED: three
  demo phones in a room do not reliably pair, so the client reports the peer
  id instead of establishing a real BLE GATT link);
* ``stale``   -- no heartbeat for a while, but the last known fix is kept;
* ``offline`` -- long silence: only the last known location remains.

Whatever a persona's connectivity, the authority always sees *a* position:
the live fix when one is fresh, or the last-known fix (with how old it is)
whenever the network dropped -- that is exactly the section-12 requirement.

Every published event carries ``is_simulated: true`` (the bus stamps it).
"""
from __future__ import annotations

import copy
import datetime as dt
import threading
from typing import Any, Dict, List, Optional

from app.realtime.bus import bus

STALE_AFTER_S = 30
OFFLINE_AFTER_S = 180
HISTORY_LIMIT = 120

STATE_META = {
    "online": {"label": "ONLINE", "color": "safe", "rank": 0},
    "relay": {"label": "ON RELAY", "color": "info", "rank": 1},
    "stale": {"label": "STALE", "color": "warn", "rank": 2},
    "offline": {"label": "OFFLINE", "color": "danger", "rank": 3},
    "unseen": {"label": "NOT PINGING", "color": "neutral", "rank": 4},
    "helped": {"label": "HELP REQUESTED", "color": "danger", "rank": -1},
}


def _utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None).isoformat() + "Z"


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def _age_s(then: str) -> Optional[float]:
    if not then:
        return None
    try:
        return (_now() - dt.datetime.fromisoformat(then.rstrip("Z"))).total_seconds()
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Fictional demo personas (Section 89: everything is labelled demo data).
# ---------------------------------------------------------------------------
PERSONAS: List[Dict[str, Any]] = [
    {
        "id": "persona_1",
        "codename": "PERSON 1",
        "full_name": "Meera Nair",
        "ward_id": "loc_kurla",
        "ward_label": "Kurla Ward",
        "phone": "+91 98200 11111",
        "kind": "family",
        "baseline_fix": {"lat": 19.0850, "lng": 72.8840, "accuracy": 28},
        "battery": 82,
    },
    {
        "id": "persona_2",
        "codename": "PERSON 2",
        "full_name": "Arjun Deshpande",
        "ward_id": "loc_colaba",
        "ward_label": "Colaba Ward",
        "phone": "+91 98200 22222",
        "kind": "neighbourhood_watch",
        "baseline_fix": {"lat": 18.9110, "lng": 72.8170, "accuracy": 31},
        "battery": 67,
    },
    {
        "id": "persona_3",
        "codename": "PERSON 3",
        "full_name": "Farhan Shaikh",
        "ward_id": "loc_mahim",
        "ward_label": "Mahim Ward",
        "phone": "+91 98200 33333",
        "kind": "elder",
        "baseline_fix": {"lat": 19.0410, "lng": 72.8450, "accuracy": 24},
        "battery": 46,
    },
]

PERSONA_BY_ID = {p["id"]: p for p in PERSONAS}
PERSONA_BY_CODE = {p["codename"].lower(): p for p in PERSONAS}


class CitizenEntry:
    def __init__(self, spec: Dict[str, Any]) -> None:
        self.spec = spec
        self.fix: Optional[Dict[str, Any]] = None  # live / last-known fix
        self.last_fix_at: Optional[str] = None
        self.last_seen_at: Optional[str] = None
        self.announced: str = "online"  # what the app last declared: online|offline|relay
        self.via_relay: Optional[str] = None  # persona id relaying this fix (BLE)
        self.relayed_at: Optional[str] = None
        self.ble_enabled: bool = False
        self.bt_mode: str = "simulated"
        self.battery: Optional[float] = None
        self.heading_deg: Optional[float] = None
        self.speed_kmh: Optional[float] = None
        self.note: Optional[str] = None
        self.history: List[Dict[str, Any]] = []
        self.help: Optional[Dict[str, Any]] = None  # None | requested | acknowledged | resolved

    @property
    def id(self) -> str:
        return self.spec["id"]

    def reset(self) -> None:
        self.fix = None
        self.last_fix_at = None
        self.last_seen_at = None
        self.announced = "online"
        self.via_relay = None
        self.relayed_at = None
        self.ble_enabled = False
        self.bt_mode = "simulated"
        self.battery = float(self.spec.get("battery") or 0)
        self.heading_deg = None
        self.speed_kmh = None
        self.note = None
        self.history = []
        self.help = None

    def state(self) -> str:
        if self.help and self.help.get("status") == "requested":
            return "helped"
        if not self.last_seen_at:
            return "unseen"
        age = _age_s(self.last_seen_at)
        if age is None:
            return "unseen"
        if age <= STALE_AFTER_S:
            if self.announced == "relay":
                return "relay"
            return "online" if self.announced == "online" else "offline"
        if age <= OFFLINE_AFTER_S:
            return "stale"
        return "offline"

    def snapshot(self, include_history: bool = False) -> Dict[str, Any]:
        state = self.state()
        meta = STATE_META[state]
        return {
            "id": self.id,
            "codename": self.spec["codename"],
            "full_name": self.spec["full_name"],
            "ward_id": self.spec["ward_id"],
            "ward_label": self.spec["ward_label"],
            "phone": self.spec["phone"],
            "kind": self.spec["kind"],
            "state": state,
            "state_label": meta["label"],
            "color": meta["color"],
            "help": self.help,
            "fix": self.fix if self.fix else copy.deepcopy(self.spec["baseline_fix"]),
            "is_baseline": not self.fix,
            "last_fix_at": self.last_fix_at,
            "last_seen_at": self.last_seen_at,
            "age_s": _age_s(self.last_seen_at),
            "announced": self.announced,
            "via_relay": self.via_relay,
            "relayed_at": self.relayed_at,
            "ble_enabled": self.ble_enabled,
            "bt_mode": self.bt_mode,
            "battery": self.battery,
            "heading_deg": self.heading_deg,
            "speed_kmh": self.speed_kmh,
            "note": self.note,
            "history": self.history[-10:] if include_history else None,
        }


class CitizenRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: Dict[str, CitizenEntry] = {}
        self._priors: Dict[str, str] = {}
        for p in PERSONAS:
            e = CitizenEntry(p)
            e.battery = float(p.get("battery") or 0)
            self._entries[p["id"]] = e
            self._priors[p["id"]] = "unseen"

    def _entry(self, persona_id: Optional[str] = None, codename: Optional[str] = None) -> CitizenEntry:
        key = None
        if persona_id:
            key = persona_id if persona_id in self._entries else None
            if not key and persona_id.lower() in PERSONA_BY_CODE:
                key = PERSONA_BY_CODE[persona_id.lower()]["id"]
        if not key and codename:
            key = PERSONA_BY_CODE.get(codename.lower(), {}).get("id")
        if not key:
            raise KeyError(persona_id or codename or "unknown persona")
        return self._entries[key]

    def personas(self) -> List[Dict[str, Any]]:
        out = []
        for p in PERSONAS:
            item = {
                "id": p["id"],
                "codename": p["codename"],
                "full_name": p["full_name"],
                "ward_id": p["ward_id"],
                "ward_label": p["ward_label"],
                "phone": p["phone"],
                "kind": p["kind"],
            }
            e = self._entries[p["id"]]
            item["baseline_fix"] = copy.deepcopy(p["baseline_fix"])
            item["demo_label"] = "Fictional demo persona for the prototype."
            item["last_seen_at"] = e.last_seen_at
            out.append(item)
        return out

    def heartbeat(self, persona_id: Optional[str], payload: Dict[str, Any]) -> Dict[str, Any]:
        """Accept a heartbeat from the citizen app (direct or BLE-relayed)."""
        codename = payload.get("codename")
        fix = payload.get("fix")
        announced: str = payload.get("announced", "online")
        if announced not in ("online", "offline", "relay"):
            announced = "online"
        ble = bool(payload.get("ble_enabled", False))
        bt_mode = str(payload.get("bt_mode", "simulated"))
        battery = payload.get("battery")
        heading = payload.get("heading_deg")
        speed = payload.get("speed_kmh")
        note = payload.get("note")
        via_relay = payload.get("via_relay")
        if via_relay and via_relay not in self._entries and via_relay.lower() in PERSONA_BY_CODE:
            via_relay = PERSONA_BY_CODE[via_relay.lower()]["id"]

        with self._lock:
            try:
                e = self._entry(persona_id, codename)
            except KeyError as exc:
                raise ValueError(f"Unknown persona {exc}") from exc

            now_s = _utc()
            prior = self._priors[e.id]
            was = e.state()

            e.last_seen_at = now_s
            e.announced = announced
            e.ble_enabled = ble
            e.bt_mode = bt_mode
            if battery is not None:
                e.battery = float(battery)
            if heading is not None:
                e.heading_deg = float(heading)
            if speed is not None:
                e.speed_kmh = float(speed)
            if note:
                e.note = str(note)[:200]

            events_published = []
            if announced == "relay" and via_relay:
                e.via_relay = via_relay
                e.relayed_at = now_s
                events_published.append(
                    bus.publish(
                        "citizen.connection",
                        {
                            "persona_id": e.id,
                            "codename": e.spec["codename"],
                            "state": "relay",
                            "via_relay": via_relay,
                            "message": f"{e.spec['codename']} is offline and relayed over "
                                       f"Bluetooth via {self._entries[via_relay].spec['codename']}.",
                        },
                    )
                )
            elif announced == "offline":
                e.via_relay = None
                e.relayed_at = None
                if prior != "offline" or was != "offline":
                    events_published.append(
                        bus.publish(
                            "citizen.connection",
                            {
                                "persona_id": e.id,
                                "codename": e.spec["codename"],
                                "state": "offline",
                                "message": f"{e.spec['codename']} lost its network connection. "
                                           "Showing the last known location.",
                            },
                        )
                    )
            else:
                e.via_relay = None
                e.relayed_at = None

            if fix and announced in ("online", "relay"):
                fix = {
                    "lat": float(fix.get("lat")),
                    "lng": float(fix.get("lng")),
                    "accuracy": float(fix.get("accuracy", 25)),
                }
                e.fix = fix
                e.last_fix_at = now_s
                e.history.append({"at": now_s, "lat": fix["lat"], "lng": fix["lng"],
                                  "state": e.state()})
                e.history = e.history[-HISTORY_LIMIT:]
                if announced == "online":
                    events_published.append(
                        bus.publish(
                            "citizen.location",
                            {
                                "persona_id": e.id,
                                "codename": e.spec["codename"],
                                "state": "online",
                                "lat": fix["lat"],
                                "lng": fix["lng"],
                                "accuracy": fix["accuracy"],
                            },
                        )
                    )

            if not events_published:
                events_published.append(bus.publish("citizen.heartbeat",
                                                   {"persona_id": e.id, "state": e.state()}))
            self._priors[e.id] = e.state()
            return {"persona": e.snapshot(), "published_events": len(events_published)}

    def request_help(self, persona_id: Optional[str], message: str = "") -> Dict[str, Any]:
        with self._lock:
            try:
                e = self._entry(persona_id)
            except KeyError as exc:
                raise ValueError(f"Unknown persona {exc}") from exc
            e.help = {
                "status": "requested",
                "requested_at": _utc(),
                "message": (message or "")[:300],
                "fix": e.fix if e.fix else copy.deepcopy(e.spec["baseline_fix"]),
                "is_baseline": not e.fix,
                "ack_by": None,
                "ack_at": None,
                "resolved_by": None,
                "resolved_at": None,
            }
            bus.publish(
                "citizen.help",
                {
                    "persona_id": e.id,
                    "codename": e.spec["codename"],
                    "status": "requested",
                    "message": e.help["message"],
                    "at": _utc(),
                    "message_out": f"{e.spec['codename']} is asking for help at their location.",
                },
            )
            self._priors[e.id] = e.state()
            return e.snapshot()

    def ack_help(self, persona_id: Optional[str], ack_by: str) -> Dict[str, Any]:
        with self._lock:
            try:
                e = self._entry(persona_id)
            except KeyError as exc:
                raise ValueError(f"Unknown persona {exc}") from exc
            if not e.help or e.help.get("status") != "requested":
                raise ValueError("No pending help request for this persona")
            e.help["status"] = "acknowledged"
            e.help["ack_by"] = ack_by
            e.help["ack_at"] = _utc()
            bus.publish(
                "citizen.help",
                {
                    "persona_id": e.id,
                    "codename": e.spec["codename"],
                    "status": "acknowledged",
                    "ack_by": ack_by,
                    "message_out": f"{ack_by} acknowledged {e.spec['codename']}'s help request.",
                },
            )
            self._priors[e.id] = e.state()
            return e.snapshot()

    def resolve_help(self, persona_id: Optional[str], resolved_by: str) -> Dict[str, Any]:
        with self._lock:
            try:
                e = self._entry(persona_id)
            except KeyError as exc:
                raise ValueError(f"Unknown persona {exc}") from exc
            if not e.help or e.help.get("status") not in ("requested", "acknowledged"):
                raise ValueError("No active help request for this persona")
            e.help["status"] = "resolved"
            e.help["resolved_by"] = resolved_by
            e.help["resolved_at"] = _utc()
            bus.publish(
                "citizen.help",
                {
                    "persona_id": e.id,
                    "codename": e.spec["codename"],
                    "status": "resolved",
                    "resolved_by": resolved_by,
                    "message_out": f"{resolved_by} resolved {e.spec['codename']}'s help request.",
                },
            )
            self._priors[e.id] = e.state()
            return e.snapshot()

    def snapshot(self, include_history: bool = False) -> List[Dict[str, Any]]:
        with self._lock:
            return [e.snapshot(include_history) for e in self._entries.values()]

    def reset(self) -> None:
        with self._lock:
            for e in self._entries.values():
                e.reset()
                self._priors[e.id] = "unseen"


registry = CitizenRegistry()


def get_registry() -> CitizenRegistry:
    return registry