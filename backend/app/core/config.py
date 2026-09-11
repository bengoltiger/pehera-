"""PEHRA configuration.

All tunable behaviour of the system lives here or in `risk_config.py`.
Secrets are read from the environment only -- never hardcoded.
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="PEHRA_", extra="ignore")

    # --- application ---
    app_name: str = "PEHRA"
    app_full_name: str = "Predictive Early-warning for Hyperlocal Risk Assessment"
    version: str = "0.1.0"
    environment: str = "development"
    debug: bool = True

    # --- data honesty ---
    # When true, ALL environmental data is deterministic simulation, not real feeds.
    demo_mode: bool = True
    data_mode_label: str = "DEMO / SIMULATED DATA"

    # --- database ---
    database_url: str = "sqlite:///./pehra.db"

    # --- security ---
    # In production this MUST be provided via the environment.
    jwt_secret: str = os.getenv("PEHRA_JWT_SECRET", "dev-only-insecure-secret-change-me")
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 720
    password_min_length: int = 8

    # --- rate limiting (in-process token bucket) ---
    rate_limit_enabled: bool = True
    rate_limit_requests: int = 240
    rate_limit_window_seconds: int = 60
    rate_limit_write_requests: int = 40

    # --- providers ---
    weather_provider: str = "demo"
    rainfall_provider: str = "demo"
    river_provider: str = "demo"
    satellite_provider: str = "demo"
    terrain_provider: str = "demo"
    historical_provider: str = "demo"
    tide_provider: str = "demo"

    # --- Mumbai grid configuration (MB-3) ---
    # Default cell size for the DEM/risk grid (metres). 500 m matches the SIHP
    # demo spec for hyper-local Mumbai cells.
    grid_cell_size_m: int = 500

    # --- notification channels ---
    notification_push_enabled: bool = True
    notification_sms_enabled: bool = True
    notification_email_enabled: bool = True
    notification_inapp_enabled: bool = True
    # No real gateway is configured in the prototype -> deliveries are SIMULATED.
    sms_gateway_url: str | None = None
    smtp_host: str | None = None

    # --- model provider ---
    active_risk_model: str = "demo"  # demo | statistical | ml
    ml_model_path: str | None = None

    # --- map ---
    map_tile_url: str = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
    map_attribution: str = "© OpenStreetMap contributors"

    # --- live external data (Predict screen) ---
    # Open-Meteo: free, no API key. Override to test with a mock or mirror.
    open_meteo_url: str = "https://api.open-meteo.com/v1/forecast"

    # --- CORS ---
    cors_origins: List[str] = ["*"]

    @property
    def is_secret_default(self) -> bool:
        return self.jwt_secret == "dev-only-insecure-secret-change-me"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
