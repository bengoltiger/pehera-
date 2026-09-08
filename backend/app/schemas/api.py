"""Pydantic request/response schemas.

Response payloads from the engine are intentionally rich, nested dictionaries;
they are documented in the endpoint descriptions rather than being flattened
into rigid models, which would force the engine's vocabulary to be duplicated.
Request bodies -- the security-relevant direction -- are strictly validated.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
class LoginRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {"username": "authority", "password": "authority123"}})
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=128)


class UserOut(BaseModel):
    id: str
    username: str
    full_name: str
    role: str
    organisation: Optional[str] = None
    home_location_id: Optional[str] = None
    language: str = "en"


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: dt.datetime
    user: UserOut


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------
class GeofenceIn(BaseModel):
    kind: Literal["radius", "polygon", "admin"] = "radius"
    lat: Optional[float] = Field(default=None, ge=-90, le=90)
    lng: Optional[float] = Field(default=None, ge=-180, le=180)
    radius_km: Optional[float] = Field(default=6.0, gt=0, le=200)
    points: Optional[List[List[float]]] = None


class AlertCreate(BaseModel):
    """Authority alert composer payload (Section 31)."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "location_id": "loc_sinhagad_road",
                "hazard": "flood",
                "level": "WARNING",
                "message": "Water levels are rising near the Mutha bank.",
                "recommended_actions": ["Move away from low-lying roads"],
                "geofence": {"kind": "radius", "lat": 18.4575, "lng": 73.8237, "radius_km": 6},
                "target_audience": ["citizen", "authority"],
                "expires_in_hours": 6,
            }
        }
    )
    location_id: str = Field(min_length=1, max_length=40)
    hazard: str = Field(min_length=1, max_length=32)
    level: Literal["WATCH", "WARNING", "CRITICAL"]
    title: Optional[str] = Field(default=None, max_length=200)
    message: str = Field(min_length=10, max_length=2000)
    message_hi: Optional[str] = Field(default=None, max_length=2000)
    recommended_actions: List[str] = Field(default_factory=list, max_length=12)
    what: Optional[str] = Field(default=None, max_length=300)
    when: Optional[str] = Field(default=None, max_length=300)
    why: Optional[str] = Field(default=None, max_length=1000)
    what_to_do: Optional[str] = Field(default=None, max_length=1000)
    geofence: GeofenceIn = Field(default_factory=GeofenceIn)
    target_audience: List[Literal["citizen", "authority", "responder"]] = Field(
        default_factory=lambda: ["citizen", "authority"]
    )
    starts_at: Optional[dt.datetime] = None
    expires_in_hours: float = Field(default=6.0, gt=0, le=72)
    issue_immediately: bool = False

    @field_validator("recommended_actions")
    @classmethod
    def _clean_actions(cls, v: List[str]) -> List[str]:
        return [a.strip()[:200] for a in v if a and a.strip()][:12]


class AlertPatch(BaseModel):
    level: Optional[Literal["WATCH", "WARNING", "CRITICAL"]] = None
    message: Optional[str] = Field(default=None, min_length=10, max_length=2000)
    message_hi: Optional[str] = Field(default=None, max_length=2000)
    recommended_actions: Optional[List[str]] = Field(default=None, max_length=12)
    what_to_do: Optional[str] = Field(default=None, max_length=1000)
    status: Optional[Literal["issued", "resolved", "cancelled"]] = None
    expires_in_hours: Optional[float] = Field(default=None, gt=0, le=72)
    reason: str = Field(default="", max_length=500)


class AcknowledgeRequest(BaseModel):
    note: str = Field(default="", max_length=500)


class AlertPreviewRequest(BaseModel):
    location_id: str
    hazard: Optional[str] = None
    level: Optional[Literal["WATCH", "WARNING", "CRITICAL"]] = None
    language: Literal["en", "hi"] = "en"


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------
class SimulationStepRequest(BaseModel):
    steps: int = Field(default=1, ge=1, le=24)
    run_alerts: bool = True


class OverridesRequest(BaseModel):
    """Multiplicative factors applied to the scenario's baseline values."""

    model_config = ConfigDict(
        json_schema_extra={"example": {"rainfall": 1.3, "river_level": 1.1, "soil_moisture": 1.0,
                                       "wind": 1.0, "forecast_intensity": 1.2}}
    )
    rainfall: float = Field(default=1.0, ge=0.0, le=3.0)
    river_level: float = Field(default=1.0, ge=0.0, le=3.0)
    soil_moisture: float = Field(default=1.0, ge=0.0, le=3.0)
    wind: float = Field(default=1.0, ge=0.0, le=3.0)
    forecast_intensity: float = Field(default=1.0, ge=0.0, le=3.0)


class ConnectivityRequest(BaseModel):
    mode: Literal["online", "degraded", "offline"]


class FailureRequest(BaseModel):
    component: Literal["rainfall", "weather", "river", "satellite", "soil", "terrain",
                       "historical", "forecast", "ml_model", "database"]
    enabled: bool = True


class ScenarioRunRequest(BaseModel):
    reset_tick: bool = True
    auto_advance_to: Optional[int] = Field(default=None, ge=0, le=48)


class WhatIfRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"example": {"location_id": "loc_sinhagad_road",
                                       "rainfall": 1.3, "river_level": 1.2}}
    )
    location_id: str
    rainfall: float = Field(default=1.0, ge=0.0, le=3.0)
    river_level: float = Field(default=1.0, ge=0.0, le=3.0)
    soil_moisture: float = Field(default=1.0, ge=0.0, le=3.0)
    wind: float = Field(default=1.0, ge=0.0, le=3.0)
    forecast_intensity: float = Field(default=1.0, ge=0.0, le=3.0)


class ModelSelectRequest(BaseModel):
    model_key: Literal["demo", "statistical", "ml"]


class ResetRequest(BaseModel):
    scenario_id: Optional[str] = None


class VerifyRequest(BaseModel):
    scenario_id: str
    location_id: Optional[str] = None


class ErrorResponse(BaseModel):
    error: str
    message: str
    detail: Optional[Any] = None
