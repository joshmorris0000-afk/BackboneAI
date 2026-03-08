"""
Backbone AI — Supplier Statement Reconciliation
FastAPI application entry point.
"""
import logging

import sentry_sdk
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import auth, recon
from app.core.config import get_settings

settings = get_settings()

logging.basicConfig(level=logging.DEBUG if settings.debug else logging.INFO)
logger = logging.getLogger(__name__)

if settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.app_env,
        traces_sample_rate=0.1,
        profiles_sample_rate=0.1,
    )

app = FastAPI(
    title="Backbone AI — Supplier Statement Reconciliation",
    version="1.0.0",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    openapi_url="/openapi.json" if settings.debug else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://portal.backbone-ai.com"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    import redis.asyncio as aioredis

    redis = aioredis.from_url(settings.redis_url)
    ip = request.client.host
    key = f"rl:statement-recon:{ip}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, 60)
    await redis.aclose()

    if count > settings.rate_limit_per_minute:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"detail": "Rate limit exceeded"},
            headers={"Retry-After": "60"},
        )
    return await call_next(request)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    if settings.debug:
        return JSONResponse(status_code=500, content={"detail": str(exc)})
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


API_V1 = "/statement-recon/v1"

app.include_router(auth.router, prefix=API_V1)
app.include_router(recon.router, prefix=API_V1)


@app.get("/health", include_in_schema=False)
async def health():
    return {"status": "ok", "service": "supplier-statement-recon", "version": "1.0.0"}


@app.on_event("startup")
async def startup():
    logger.info(f"Supplier Statement Reconciliation service starting — env={settings.app_env}")


@app.on_event("shutdown")
async def shutdown():
    logger.info("Supplier Statement Reconciliation service shutting down")
