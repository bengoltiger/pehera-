"""PEHRA application factory.

Wires the API, CORS, rate limiting, structured error handling, request
observability, the SSE bus and (in production builds) the static SPA.

Run with:  uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
"""
from __future__ import annotations

import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.router import api_router
from app.core.config import settings
from app.db.seed import seed_all
from app.db.session import init_db, session_scope
from app.security.ratelimit import check_rate_limit
from app.services.observability import log_event, trim_logs

DESCRIPTION = """
**PEHRA — Predictive Early-warning for Hyperlocal Risk Assessment**

A decision-support system that turns environmental signals into *hyper-local,
explained, prioritised, actionable* warnings.

The full chain is implemented and observable through this API:

`SIGNAL → EARLY SIGNAL → PREDICTION → CONFIDENCE → EXPLANATION → RISK →
PRIORITY → WARNING → ACTION → OUTCOME → LEARNING`

---

### ⚠️ Data honesty

This prototype runs on **deterministic simulated data**. There is no live
weather, satellite, river-gauge or notification integration. Every response
that carries environmental values also carries a `is_simulated` / `data_origin`
marker, every notification delivery is labelled `SIMULATED DELIVERY`, and every
accuracy figure states exactly what it was measured on. No metric in this API
is presented as real-world disaster-prediction accuracy.

The provider layer is an adapter architecture: replacing a simulated feed with
a real one is an implementation of `DataProvider`, registered in a slot. No
engine or API code changes.
"""

TAGS_METADATA = [
    {"name": "system", "description": "Health, configuration, models, providers and logs."},
    {"name": "auth", "description": "Authentication and role-based access control."},
    {"name": "risk", "description": "Locations, observations, forecasts, risk assessments, "
                                    "threat cells and map data."},
    {"name": "alerts", "description": "Alert decision engine, composer, approval and lifecycle."},
    {"name": "simulation", "description": "Scenario library, simulation clock, what-if lab, "
                                          "replay, verification and the realtime stream."},
    {"name": "analytics", "description": "Command-centre overview, analytics, model performance "
                                         "and the audit log."},
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    with session_scope() as db:
        seed_all(db)
        log_event(db, level="info", component="startup", event="boot",
                  message=f"{settings.app_name} {settings.version} started in "
                          f"{settings.environment} mode.",
                  context={"demo_mode": settings.demo_mode})
        trim_logs(db)
    if settings.is_secret_default:
        print("[PEHRA] WARNING: using the insecure development JWT secret. "
              "Set PEHRA_JWT_SECRET before any real deployment.")
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title=f"{settings.app_name} — {settings.app_full_name}",
        version=settings.version,
        description=DESCRIPTION,
        openapi_tags=TAGS_METADATA,
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Process-Time", "X-Data-Mode"],
    )

    # ------------------------------------------------------------------
    # Middleware: rate limiting + timing + data-honesty header
    # ------------------------------------------------------------------
    @app.middleware("http")
    async def _guard(request: Request, call_next):
        if request.url.path.startswith("/api") and not request.url.path.startswith("/api/events"):
            try:
                check_rate_limit(request)
            except HTTPException as exc:
                return JSONResponse(status_code=exc.status_code, content=exc.detail,
                                    headers=exc.headers or {})
        started = time.perf_counter()
        response = await call_next(request)
        elapsed = (time.perf_counter() - started) * 1000
        response.headers["X-Process-Time"] = f"{elapsed:.1f}ms"
        if settings.demo_mode:
            response.headers["X-Data-Mode"] = "simulated"
        return response

    # ------------------------------------------------------------------
    # Structured, honest error handling (Sections 62, 63)
    # ------------------------------------------------------------------
    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException):
        detail = exc.detail
        if isinstance(detail, dict):
            payload = detail
        else:
            payload = {"error": _slug(exc.status_code), "message": str(detail)}
        payload.setdefault("status_code", exc.status_code)
        payload.setdefault("path", request.url.path)
        return JSONResponse(status_code=exc.status_code, content=payload,
                            headers=getattr(exc, "headers", None))

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError):
        problems = [
            {
                "field": ".".join(str(p) for p in err["loc"][1:]) or str(err["loc"][0]),
                "message": err["msg"],
                "type": err["type"],
            }
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={
                "error": "validation_failed",
                "message": "The request could not be accepted because some fields are invalid.",
                "problems": problems,
                "path": request.url.path,
            },
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        try:
            with session_scope() as db:
                log_event(db, level="error", component="api", event="unhandled_exception",
                          message=f"{type(exc).__name__}: {exc}",
                          context={"path": request.url.path, "method": request.method})
        except Exception:
            pass
        return JSONResponse(
            status_code=500,
            content={
                "error": "internal_error",
                "message": "Something went wrong on our side. The prediction shown may be "
                           "out of date — please retry.",
                "detail": f"{type(exc).__name__}: {exc}" if settings.debug else None,
                "path": request.url.path,
            },
        )

    app.include_router(api_router)

    # ------------------------------------------------------------------
    # Static SPA (built frontend). Optional: absent in dev, where Vite serves it.
    # ------------------------------------------------------------------
    dist = Path(__file__).resolve().parent.parent / "static"
    if dist.is_dir():
        assets = dist / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def _spa(full_path: str):
            candidate = dist / full_path
            if full_path and candidate.is_file():
                return FileResponse(str(candidate))
            return FileResponse(str(dist / "index.html"))
    else:
        @app.get("/", include_in_schema=False)
        async def _root():
            return {
                "app": settings.app_name,
                "full_name": settings.app_full_name,
                "version": settings.version,
                "docs": "/api/docs",
                "health": "/api/health",
                "note": "The built frontend is not present. In development the Vite dev server "
                        "serves the UI and proxies /api to this process. Run "
                        "`npm run build` in ../frontend and copy dist/ to backend/static "
                        "to serve everything from one port.",
                "data_mode": {"is_simulated": settings.demo_mode,
                              "label": settings.data_mode_label},
            }

    return app


def _slug(code: int) -> str:
    return {
        400: "bad_request", 401: "unauthenticated", 403: "forbidden", 404: "not_found",
        409: "conflict", 422: "validation_failed", 429: "rate_limited",
    }.get(code, "error")


app = create_app()
