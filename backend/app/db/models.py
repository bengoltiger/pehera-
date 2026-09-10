"""SQLAlchemy ORM models -- the persistent source of truth (Section 53, 96).

All timestamps are stored in UTC (Section 97).
"""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )


# ---------------------------------------------------------------------------
# Identity & access
# ---------------------------------------------------------------------------
class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("usr"))
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, index=True)  # citizen|authority|administrator
    organisation: Mapped[Optional[str]] = mapped_column(String(120))
    # Citizen privacy (Section 67): only a coarse location reference is kept.
    home_location_id: Mapped[Optional[str]] = mapped_column(ForeignKey("locations.id"))
    language: Mapped[str] = mapped_column(String(8), default="en")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime)

    home_location = relationship("Location", foreign_keys=[home_location_id])


# ---------------------------------------------------------------------------
# Geography
# ---------------------------------------------------------------------------
class Location(Base, TimestampMixin):
    """A hyper-local monitored zone (ward / village / block)."""

    __tablename__ = "locations"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    name_hi: Mapped[Optional[str]] = mapped_column(String(160))
    admin_type: Mapped[str] = mapped_column(String(32), default="ward")  # ward|village|block|district
    district: Mapped[str] = mapped_column(String(80), index=True)
    state: Mapped[str] = mapped_column(String(80), index=True)
    # WGS84 / EPSG:4326 everywhere (Section 98)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    elevation_m: Mapped[float] = mapped_column(Float, default=0.0)
    area_km2: Mapped[float] = mapped_column(Float, default=1.0)
    population: Mapped[int] = mapped_column(Integer, default=0)
    vulnerable_population: Mapped[int] = mapped_column(Integer, default=0)
    households: Mapped[int] = mapped_column(Integer, default=0)
    terrain_vulnerability: Mapped[float] = mapped_column(Float, default=0.4)  # 0..1
    drainage_deficiency: Mapped[float] = mapped_column(Float, default=0.4)  # 0..1
    river_id: Mapped[Optional[str]] = mapped_column(String(40))
    polygon: Mapped[Optional[list]] = mapped_column(JSON)  # [[lat,lng], ...]
    primary_hazards: Mapped[list] = mapped_column(JSON, default=list)
    data_origin: Mapped[str] = mapped_column(String(32), default="demo_seed")

    __table_args__ = (
        Index("ix_locations_geo", "latitude", "longitude"),
        Index("ix_locations_admin", "state", "district"),
    )


class Infrastructure(Base, TimestampMixin):
    __tablename__ = "infrastructure"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    location_id: Mapped[str] = mapped_column(ForeignKey("locations.id"), index=True)
    name: Mapped[str] = mapped_column(String(140), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), index=True)  # hospital|school|shelter|bridge|road|power|water
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    capacity: Mapped[Optional[int]] = mapped_column(Integer)
    criticality: Mapped[float] = mapped_column(Float, default=0.5)  # 0..1
    data_origin: Mapped[str] = mapped_column(String(32), default="demo_seed")
    # Contact / siting details surfaced to citizens (demo dataset).
    address: Mapped[Optional[str]] = mapped_column(String(200))
    phone: Mapped[Optional[str]] = mapped_column(String(40))


class Hazard(Base):
    """Registry row mirroring the extensible hazard definitions."""

    __tablename__ = "hazards"

    key: Mapped[str] = mapped_column(String(32), primary_key=True)
    label: Mapped[str] = mapped_column(String(80))
    icon: Mapped[str] = mapped_column(String(40))
    definition: Mapped[dict] = mapped_column(JSON)


# ---------------------------------------------------------------------------
# Sensing layer
# ---------------------------------------------------------------------------
class Observation(Base):
    """A single measured environmental value with full provenance (Section 3)."""

    __tablename__ = "observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    location_id: Mapped[str] = mapped_column(ForeignKey("locations.id"), index=True)
    feature: Mapped[str] = mapped_column(String(48), index=True)
    value: Mapped[Optional[float]] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(24), default="")
    source: Mapped[str] = mapped_column(String(64))
    source_kind: Mapped[str] = mapped_column(String(24))  # rainfall|weather|river|satellite|soil|terrain
    observed_or_predicted: Mapped[str] = mapped_column(String(12), default="observed")
    quality: Mapped[float] = mapped_column(Float, default=1.0)  # 0..1 sensor quality
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=True)
    observed_at: Mapped[dt.datetime] = mapped_column(DateTime, index=True)
    ingested_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    scenario_tick: Mapped[Optional[int]] = mapped_column(Integer, index=True)

    __table_args__ = (
        Index("ix_obs_loc_feature_time", "location_id", "feature", "observed_at"),
    )


class Forecast(Base):
    __tablename__ = "forecasts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    location_id: Mapped[str] = mapped_column(ForeignKey("locations.id"), index=True)
    feature: Mapped[str] = mapped_column(String(48), index=True)
    value: Mapped[Optional[float]] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(24), default="")
    horizon_minutes: Mapped[int] = mapped_column(Integer, index=True)
    source: Mapped[str] = mapped_column(String(64))
    model_agreement: Mapped[float] = mapped_column(Float, default=0.8)  # 0..1 ensemble agreement
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=True)
    issued_at: Mapped[dt.datetime] = mapped_column(DateTime, index=True)
    valid_at: Mapped[dt.datetime] = mapped_column(DateTime, index=True)
    scenario_tick: Mapped[Optional[int]] = mapped_column(Integer, index=True)


# ---------------------------------------------------------------------------
# Intelligence layer
# ---------------------------------------------------------------------------
class ModelVersion(Base, TimestampMixin):
    __tablename__ = "model_versions"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), index=True)
    version: Mapped[str] = mapped_column(String(24))
    kind: Mapped[str] = mapped_column(String(24))  # demo|statistical|ml
    description: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    trained_on: Mapped[Optional[str]] = mapped_column(String(120))
    # Never fabricate accuracy: null until measured by the verification service.
    measured_metrics: Mapped[Optional[dict]] = mapped_column(JSON)

    __table_args__ = (UniqueConstraint("name", "version", name="uq_model_name_version"),)


class RiskPrediction(Base):
    __tablename__ = "risk_predictions"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("rp"))
    location_id: Mapped[str] = mapped_column(ForeignKey("locations.id"), index=True)
    hazard: Mapped[str] = mapped_column(String(32), index=True)
    horizon_minutes: Mapped[int] = mapped_column(Integer, index=True, default=0)

    hazard_score: Mapped[float] = mapped_column(Float)
    exposure_score: Mapped[float] = mapped_column(Float)
    overall_risk: Mapped[float] = mapped_column(Float, index=True)
    severity: Mapped[str] = mapped_column(String(16), index=True)

    confidence: Mapped[float] = mapped_column(Float)
    uncertainty: Mapped[float] = mapped_column(Float)
    range_low: Mapped[float] = mapped_column(Float)
    range_high: Mapped[float] = mapped_column(Float)

    momentum_rate: Mapped[float] = mapped_column(Float, default=0.0)
    momentum_band: Mapped[str] = mapped_column(String(20), default="STABLE")

    model_name: Mapped[str] = mapped_column(String(64))
    model_version: Mapped[str] = mapped_column(String(24))
    is_fallback: Mapped[bool] = mapped_column(Boolean, default=False)
    degraded_reason: Mapped[Optional[str]] = mapped_column(Text)

    contributors: Mapped[list] = mapped_column(JSON, default=list)
    confidence_breakdown: Mapped[dict] = mapped_column(JSON, default=dict)
    data_health: Mapped[dict] = mapped_column(JSON, default=dict)
    explanation: Mapped[list] = mapped_column(JSON, default=list)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, index=True)
    scenario_tick: Mapped[Optional[int]] = mapped_column(Integer, index=True)

    __table_args__ = (
        Index("ix_pred_loc_time", "location_id", "created_at"),
        Index("ix_pred_active", "location_id", "horizon_minutes", "created_at"),
    )


class PredictionSnapshot(Base):
    """Full input snapshot for reproducibility / later evaluation (Section 40)."""

    __tablename__ = "prediction_snapshots"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("snap"))
    prediction_id: Mapped[str] = mapped_column(ForeignKey("risk_predictions.id"), index=True)
    location_id: Mapped[str] = mapped_column(ForeignKey("locations.id"), index=True)
    inputs_raw: Mapped[dict] = mapped_column(JSON)
    inputs_normalised: Mapped[dict] = mapped_column(JSON)
    feature_metadata: Mapped[dict] = mapped_column(JSON)
    weights_used: Mapped[dict] = mapped_column(JSON)
    output: Mapped[dict] = mapped_column(JSON)
    model_name: Mapped[str] = mapped_column(String(64))
    model_version: Mapped[str] = mapped_column(String(24))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, index=True)


class ThreatCell(Base, TimestampMixin):
    __tablename__ = "threat_cells"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    hazard: Mapped[str] = mapped_column(String(32), index=True)
    center_lat: Mapped[float] = mapped_column(Float)
    center_lng: Mapped[float] = mapped_column(Float)
    radius_km: Mapped[float] = mapped_column(Float)
    polygon: Mapped[Optional[list]] = mapped_column(JSON)
    current_severity: Mapped[float] = mapped_column(Float, index=True)
    predicted_severity: Mapped[float] = mapped_column(Float)
    severity_label: Mapped[str] = mapped_column(String(16))
    movement_bearing_deg: Mapped[Optional[float]] = mapped_column(Float)
    movement_speed_kmh: Mapped[Optional[float]] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)  # active|dissipating|resolved
    location_ids: Mapped[list] = mapped_column(JSON, default=list)
    track: Mapped[list] = mapped_column(JSON, default=list)  # historical positions
    predicted_track: Mapped[list] = mapped_column(JSON, default=list)
    first_detected_at: Mapped[dt.datetime] = mapped_column(DateTime, index=True)
    last_updated_at: Mapped[dt.datetime] = mapped_column(DateTime)
    scenario_tick: Mapped[Optional[int]] = mapped_column(Integer)


class EarlySignal(Base):
    """Subtle precursor patterns detected before severity (Section 70)."""

    __tablename__ = "early_signals"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("sig"))
    location_id: Mapped[str] = mapped_column(ForeignKey("locations.id"), index=True)
    kind: Mapped[str] = mapped_column(String(48), index=True)
    label: Mapped[str] = mapped_column(String(140))
    detail: Mapped[str] = mapped_column(Text)
    magnitude: Mapped[float] = mapped_column(Float)
    risk_at_detection: Mapped[float] = mapped_column(Float)
    detected_at: Mapped[dt.datetime] = mapped_column(DateTime, index=True)
    scenario_tick: Mapped[Optional[int]] = mapped_column(Integer)


# ---------------------------------------------------------------------------
# Action layer
# ---------------------------------------------------------------------------
class Alert(Base, TimestampMixin):
    __tablename__ = "alerts"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("alt"))
    location_id: Mapped[str] = mapped_column(ForeignKey("locations.id"), index=True)
    incident_id: Mapped[Optional[str]] = mapped_column(ForeignKey("incidents.id"), index=True)
    hazard: Mapped[str] = mapped_column(String(32), index=True)
    level: Mapped[str] = mapped_column(String(16), index=True)  # WATCH|WARNING|CRITICAL
    status: Mapped[str] = mapped_column(String(20), index=True, default="recommended")
    # recommended|pending_approval|issued|delivered|acknowledged|updated|escalated|resolved|cancelled|expired

    title: Mapped[str] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(Text)
    message_hi: Mapped[Optional[str]] = mapped_column(Text)
    recommended_actions: Mapped[list] = mapped_column(JSON, default=list)

    # the five citizen questions (Section 23)
    what: Mapped[str] = mapped_column(Text, default="")
    where: Mapped[str] = mapped_column(Text, default="")
    when: Mapped[str] = mapped_column(Text, default="")
    why: Mapped[str] = mapped_column(Text, default="")
    what_to_do: Mapped[str] = mapped_column(Text, default="")

    risk_score: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    prediction_id: Mapped[Optional[str]] = mapped_column(ForeignKey("risk_predictions.id"))
    threat_cell_id: Mapped[Optional[str]] = mapped_column(ForeignKey("threat_cells.id"))

    geofence_kind: Mapped[str] = mapped_column(String(20), default="radius")  # radius|polygon|admin
    geofence: Mapped[dict] = mapped_column(JSON, default=dict)
    estimated_exposed_population: Mapped[int] = mapped_column(Integer, default=0)
    target_audience: Mapped[list] = mapped_column(JSON, default=list)  # citizen|authority|responder

    trigger_reason: Mapped[str] = mapped_column(Text, default="")
    trigger_kinds: Mapped[list] = mapped_column(JSON, default=list)

    is_ai_generated: Mapped[bool] = mapped_column(Boolean, default=True)
    approved_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime)
    issued_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, index=True)
    expires_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, index=True)
    resolved_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime)
    update_count: Mapped[int] = mapped_column(Integer, default=0)
    supersedes_id: Mapped[Optional[str]] = mapped_column(String(40))
    dedup_key: Mapped[str] = mapped_column(String(120), index=True, default="")
    lead_time_seconds: Mapped[Optional[int]] = mapped_column(Integer)
    scenario_tick: Mapped[Optional[int]] = mapped_column(Integer)

    __table_args__ = (Index("ix_alerts_active", "status", "level", "location_id"),)


class AlertTransition(Base):
    __tablename__ = "alert_transitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alert_id: Mapped[str] = mapped_column(ForeignKey("alerts.id"), index=True)
    from_status: Mapped[Optional[str]] = mapped_column(String(20))
    to_status: Mapped[str] = mapped_column(String(20))
    from_level: Mapped[Optional[str]] = mapped_column(String(16))
    to_level: Mapped[Optional[str]] = mapped_column(String(16))
    actor: Mapped[str] = mapped_column(String(64), default="system")
    actor_role: Mapped[str] = mapped_column(String(20), default="system")
    reason: Mapped[str] = mapped_column(Text, default="")
    at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, index=True)


class AlertDelivery(Base):
    __tablename__ = "alert_deliveries"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("dlv"))
    alert_id: Mapped[str] = mapped_column(ForeignKey("alerts.id"), index=True)
    channel: Mapped[str] = mapped_column(String(16), index=True)  # push|sms|email|inapp
    recipient_kind: Mapped[str] = mapped_column(String(20), default="citizen")
    recipient_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued|sent|delivered|failed
    # Prototype: nothing actually leaves the machine.
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=True)
    provider: Mapped[str] = mapped_column(String(48), default="SimulatedChannel")
    detail: Mapped[Optional[str]] = mapped_column(Text)
    opened_count: Mapped[int] = mapped_column(Integer, default=0)
    sent_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    delivered_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime)


class AlertAcknowledgement(Base):
    __tablename__ = "alert_acknowledgements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alert_id: Mapped[str] = mapped_column(ForeignKey("alerts.id"), index=True)
    user_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"))
    actor_role: Mapped[str] = mapped_column(String(20), default="citizen")
    note: Mapped[Optional[str]] = mapped_column(Text)
    acknowledged_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, index=True)

    __table_args__ = (UniqueConstraint("alert_id", "user_id", name="uq_ack_alert_user"),)


class Incident(Base, TimestampMixin):
    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("inc"))
    location_id: Mapped[str] = mapped_column(ForeignKey("locations.id"), index=True)
    hazard: Mapped[str] = mapped_column(String(32), index=True)
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)  # open|resolved|evaluated
    peak_risk: Mapped[float] = mapped_column(Float, default=0.0)
    peak_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime)
    detected_at: Mapped[dt.datetime] = mapped_column(DateTime, index=True)
    first_warning_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime)
    resolved_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime)
    lead_time_seconds: Mapped[Optional[int]] = mapped_column(Integer)
    story: Mapped[list] = mapped_column(JSON, default=list)      # risk story entries
    timeline: Mapped[list] = mapped_column(JSON, default=list)   # lifecycle stages
    scenario_id: Mapped[Optional[str]] = mapped_column(String(48))


class PredictionVerification(Base):
    __tablename__ = "prediction_verifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Nullable: replay-based verification compares forecasts made inside a replay,
    # which are deliberately not persisted as RiskPrediction rows.
    prediction_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("risk_predictions.id"), index=True, nullable=True
    )
    incident_id: Mapped[Optional[str]] = mapped_column(ForeignKey("incidents.id"), index=True)
    location_id: Mapped[str] = mapped_column(ForeignKey("locations.id"), index=True)
    predicted_risk: Mapped[float] = mapped_column(Float)
    actual_risk: Mapped[Optional[float]] = mapped_column(Float)
    actual_event_occurred: Mapped[bool] = mapped_column(Boolean, default=False)
    outcome: Mapped[str] = mapped_column(String(24), index=True)
    # CORRECT|UNDERPREDICTED|OVERPREDICTED|FALSE_POSITIVE|MISSED_EVENT|PENDING
    horizon_minutes: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[Optional[float]] = mapped_column(Float)
    lead_time_seconds: Mapped[Optional[int]] = mapped_column(Integer)
    model_name: Mapped[str] = mapped_column(String(64), default="")
    model_version: Mapped[str] = mapped_column(String(24), default="")
    verified_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, index=True)
    source: Mapped[str] = mapped_column(String(32), default="simulated_replay")


class Scenario(Base, TimestampMixin):
    __tablename__ = "scenarios"

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text)
    hazard_focus: Mapped[list] = mapped_column(JSON, default=list)
    focus_location_id: Mapped[Optional[str]] = mapped_column(String(40))
    tick_minutes: Mapped[int] = mapped_column(Integer, default=15)
    total_ticks: Mapped[int] = mapped_column(Integer, default=24)
    definition: Mapped[dict] = mapped_column(JSON, default=dict)
    is_deterministic: Mapped[bool] = mapped_column(Boolean, default=True)


class SimulationState(Base):
    """Single-row table holding the live simulation clock (Section 77/80)."""

    __tablename__ = "simulation_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    scenario_id: Mapped[str] = mapped_column(String(48), default="normal_day")
    tick: Mapped[int] = mapped_column(Integer, default=0)
    running: Mapped[bool] = mapped_column(Boolean, default=False)
    speed: Mapped[float] = mapped_column(Float, default=1.0)
    # manual overrides from the What-If lab / Simulation Lab sliders
    overrides: Mapped[dict] = mapped_column(JSON, default=dict)
    connectivity: Mapped[str] = mapped_column(String(16), default="online")  # online|degraded|offline
    forced_failures: Mapped[dict] = mapped_column(JSON, default=dict)
    started_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor_id: Mapped[Optional[str]] = mapped_column(String(40), index=True)
    actor_name: Mapped[str] = mapped_column(String(64), default="system")
    actor_role: Mapped[str] = mapped_column(String(20), default="system")
    action: Mapped[str] = mapped_column(String(48), index=True)
    entity_type: Mapped[str] = mapped_column(String(32), index=True)
    entity_id: Mapped[Optional[str]] = mapped_column(String(48), index=True)
    from_state: Mapped[Optional[str]] = mapped_column(String(32))
    to_state: Mapped[Optional[str]] = mapped_column(String(32))
    detail: Mapped[Optional[dict]] = mapped_column(JSON)
    ip_address: Mapped[Optional[str]] = mapped_column(String(64))
    at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, index=True)


class SystemLog(Base):
    """Internal observability log (Section 87)."""

    __tablename__ = "system_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    level: Mapped[str] = mapped_column(String(12), index=True)  # info|warning|error
    component: Mapped[str] = mapped_column(String(40), index=True)
    event: Mapped[str] = mapped_column(String(80), index=True)
    message: Mapped[str] = mapped_column(Text)
    context: Mapped[Optional[dict]] = mapped_column(JSON)
    duration_ms: Mapped[Optional[float]] = mapped_column(Float)
    at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, index=True)
