"""Alert decision engine tests: triggers, anti-fatigue dedup, priority.

Protects Sections 20/48 behaviour: alerts are recommended by AI and issued by
humans; repeated conditions update an existing alert instead of spawning new
ones; level escalation/de-escalation respects hysteresis so alerts do not flap.
"""
from __future__ import annotations

import datetime as dt

import pytest

from app.alerts.engine import (
    TriggerEvaluation,
    decide_dedup,
    evaluate_triggers,
    level_for_risk,
    priority_score,
    should_resolve,
)
from app.core.timeutil import utcnow
from app.db.models import Alert

LOCATION = "loc_sinhagad_road"
HAZARD = "flood"


def test_level_for_risk_thresholds():
    assert level_for_risk(30) is None
    assert level_for_risk(41) == "WATCH"
    assert level_for_risk(61) == "WARNING"
    assert level_for_risk(81) == "CRITICAL"


def test_trigger_risk_threshold():
    ev = evaluate_triggers(risk=70, momentum_rate=0, confidence=80, prediction={})
    assert ev.should_alert is True
    assert ev.level == "WARNING"
    assert "risk_threshold" in ev.kinds
    assert ev.reasons


def test_trigger_low_confidence_blocks():
    ev = evaluate_triggers(risk=70, momentum_rate=0, confidence=20, prediction={})
    assert ev.should_alert is False
    assert ev.blocked_reason is not None


def test_trigger_momentum_before_threshold():
    ev = evaluate_triggers(risk=45, momentum_rate=25, confidence=80, prediction={})
    assert ev.should_alert is True
    assert ev.level == "WATCH"
    assert "rapid_acceleration" in ev.kinds


def test_trigger_nothing_met():
    ev = evaluate_triggers(risk=10, momentum_rate=0, confidence=95, prediction={})
    assert ev.should_alert is False
    assert ev.level is None


def test_trigger_peak_escalation():
    prediction = {
        "peak": {"available": True, "in_minutes": 30, "risk": 88},
    }
    ev = evaluate_triggers(risk=50, momentum_rate=0, confidence=80, prediction=prediction)
    assert ev.should_alert is True
    assert ev.level == "WARNING"
    assert "forecast_escalation" in ev.kinds


def test_priority_score_ordering():
    low = priority_score(risk=40, exposure=30, momentum_rate=0, confidence=50)
    high = priority_score(risk=90, exposure=90, momentum_rate=30, confidence=95)
    assert high["score"] > low["score"]
    assert 0 <= low["score"] <= 100
    assert 0 <= high["score"] <= 100
    for factor in ("risk", "exposure", "urgency", "confidence"):
        assert factor in high["factors"]


# ---------------------------------------------------------------------------
# Anti-fatigue dedup (needs a real DB session)
# ---------------------------------------------------------------------------
def _insert_alert(db, *, level="WARNING", risk=65.0, status="issued", minutes_ago=5):
    alert = Alert(
        id=f"alert_test_{dt.datetime.now(dt.timezone.utc).microsecond}",
        location_id=LOCATION,
        hazard=HAZARD,
        level=level,
        status=status,
        title=f"{level} flood risk",
        message="test message",
        risk_score=risk,
        confidence=75.0,
        dedup_key=f"{LOCATION}:{HAZARD}",
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert


def test_dedup_create_when_none_exists(db):
    db.query(Alert).filter(Alert.hazard == HAZARD).delete()
    db.commit()
    dec = decide_dedup(
        db, location_id=LOCATION, hazard=HAZARD, level="WATCH", risk=45, now=utcnow()
    )
    assert dec.action == "create"


def test_dedup_escalates_on_higher_level(db):
    db.query(Alert).filter(Alert.hazard == HAZARD).delete()
    db.commit()
    existing = _insert_alert(db, level="WATCH", risk=45)
    dec = decide_dedup(
        db, location_id=LOCATION, hazard=HAZARD, level="CRITICAL", risk=85, now=utcnow()
    )
    assert dec.action == "escalate"
    assert dec.existing is not None
    db.delete(existing)
    db.commit()


def test_dedup_suppresses_when_level_falls_inside_hysteresis(db):
    db.query(Alert).filter(Alert.hazard == HAZARD).delete()
    db.commit()
    existing = _insert_alert(db, level="WARNING", risk=65)
    dec = decide_dedup(
        db, location_id=LOCATION, hazard=HAZARD, level="WATCH", risk=60, now=utcnow()
    )
    assert dec.action == "suppress"
    db.delete(existing)
    db.commit()


def test_dedup_update_when_risk_moves_inside_cooldown(db):
    db.query(Alert).filter(Alert.hazard == HAZARD).delete()
    db.commit()
    existing = _insert_alert(db, level="WARNING", risk=65)
    dec = decide_dedup(
        db, location_id=LOCATION, hazard=HAZARD, level="WARNING", risk=80, now=utcnow()
    )
    assert dec.action == "update"
    db.delete(existing)
    db.commit()


def test_dedup_suppresses_when_barely_moved(db):
    db.query(Alert).filter(Alert.hazard == HAZARD).delete()
    db.commit()
    existing = _insert_alert(db, level="WARNING", risk=65)
    dec = decide_dedup(
        db, location_id=LOCATION, hazard=HAZARD, level="WARNING", risk=67, now=utcnow()
    )
    assert dec.action == "suppress"
    db.delete(existing)
    db.commit()


def test_should_resolve_below_threshold(db):
    db.query(Alert).filter(Alert.hazard == HAZARD).delete()
    db.commit()
    existing = _insert_alert(db, level="WARNING", risk=20)
    reason = should_resolve(existing, risk=10, now=utcnow())
    assert reason is not None
    assert "resolve threshold" in reason
    db.delete(existing)
    db.commit()


def test_should_resolve_keeps_above_threshold(db):
    db.query(Alert).filter(Alert.hazard == HAZARD).delete()
    db.commit()
    existing = _insert_alert(db, level="WARNING", risk=80)
    assert should_resolve(existing, risk=80, now=utcnow()) is None
    db.delete(existing)
    db.commit()