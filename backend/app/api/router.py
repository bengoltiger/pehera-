"""Aggregate API router — every PEHRA endpoint under a single /api prefix."""
from __future__ import annotations

from fastapi import APIRouter

from app.api.routers import alerts, analytics, auth, live, risk, simulation, system

api_router = APIRouter(prefix="/api")
api_router.include_router(system.router)
api_router.include_router(auth.router)
api_router.include_router(risk.router)
api_router.include_router(alerts.router)
api_router.include_router(simulation.router)
api_router.include_router(analytics.router)
api_router.include_router(live.router)

__all__ = ["api_router"]
