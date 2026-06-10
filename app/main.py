"""
TTS Platform — FastAPI application entry point.
Wires up routers, middleware, logging, Sentry, Prometheus, and rate limiting.
"""
import time
import uuid

import sentry_sdk
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.config import get_settings
from app.routers import admin, api_keys, auth, billing, health, team, tts, usage, webhooks

settings = get_settings()

# ── Sentry ────────────────────────────────────────────────────────────────────
if settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        traces_sample_rate=0.1,
    )

# ── Rate limiter ──────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address)

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="TTS Platform API",
    version="1.0.0",
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Request ID + structured logging middleware ────────────────────────────────
@app.middleware("http")
async def request_logging_middleware(request: Request, call_next) -> Response:
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    start = time.monotonic()

    # Pull org/user context if available (best-effort; don't fail if missing)
    org_id = None
    user_id = None

    response = await call_next(request)

    duration_ms = int((time.monotonic() - start) * 1000)
    logger.info(
        {
            "request_id": request_id,
            "method": request.method,
            "endpoint": str(request.url.path),
            "status_code": response.status_code,
            "duration_ms": duration_ms,
            "org_id": org_id,
            "user_id": user_id,
        }
    )
    response.headers["X-Request-ID"] = request_id
    return response

# ── Prometheus ────────────────────────────────────────────────────────────────
Instrumentator().instrument(app).expose(app, endpoint="/metrics")

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(tts.router)
app.include_router(api_keys.router)
app.include_router(usage.router)
app.include_router(billing.router)
app.include_router(team.router)
app.include_router(webhooks.router)
app.include_router(admin.router)
app.include_router(health.router)


@app.get("/", tags=["root"])
async def root():
    return {"service": "TTS Platform API", "version": "1.0.0", "status": "ok"}


# ── Global exception handler (attach Sentry context) ─────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", "unknown")
    logger.error(f"Unhandled exception [{request_id}]: {exc}", exc_info=True)
    if settings.sentry_dsn:
        with sentry_sdk.push_scope() as scope:
            scope.set_tag("request_id", request_id)
            sentry_sdk.capture_exception(exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "request_id": request_id},
    )
