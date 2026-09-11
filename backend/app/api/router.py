"""Aggregate API router — every PEHRA endpoint under a single /api prefix."""
from __future__ import annotations

from fastapi import APIRouter

from app.api.routers import (
    alerts,
    analytics,
    auth,
    citizens,
    hospitals,
    live,
    navigation,
    rainfall,
    risk,
    routes,
    shelters,
    simulation,
    storm,
    system,
    terrain,
    traffic,
)

api_router = APIRouter(prefix="/api")
api_router.include_router(system.router)
api_router.include_router(auth.router)
api_router.include_router(risk.router)
api_router.include_router(alerts.router)
api_router.include_router(simulation.router)
api_router.include_router(analytics.router)
api_router.include_router(live.router)
api_router.include_router(terrain.router)
api_router.include_router(storm.router)
api_router.include_router(rainfall.router)
api_router.include_router(traffic.router)
api_router.include_router(citizens.router)
api_router.include_router(routes.router)
api_router.include_router(navigation.router)
api_router.include_router(shelters.router)
api_router.include_router(hospitals.router)

__all__ = ["api_router"]