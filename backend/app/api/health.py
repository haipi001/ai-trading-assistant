from datetime import datetime
from datetime import timezone
from typing import Literal

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from redis import Redis
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import get_engine

router = APIRouter(tags=["health"])

DependencyStatus = Literal["ok", "unavailable"]


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    service: Literal["ai-trading-os-backend"]
    database: DependencyStatus
    redis: DependencyStatus


def check_database() -> DependencyStatus:
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
        return "ok"
    except Exception:
        return "unavailable"


def check_redis() -> DependencyStatus:
    settings = get_settings()
    try:
        client = Redis.from_url(
            str(settings.redis_url),
            socket_connect_timeout=settings.dependency_check_timeout_seconds,
            socket_timeout=settings.dependency_check_timeout_seconds,
        )
        return "ok" if client.ping() else "unavailable"
    except Exception:
        return "unavailable"


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    database = check_database()
    redis = check_redis()
    return HealthResponse(
        status="ok" if database == "ok" else "degraded",
        service="ai-trading-os-backend",
        database=database,
        redis=redis,
    )


def authentication_configuration(settings) -> dict:
    required = settings.managed_auth_required or settings.environment.lower() in {'production','staging'}
    configured = settings.managed_auth_required and all(str(value or '').strip() for value in (
        settings.oidc_issuer, settings.oidc_userinfo_url, settings.oidc_client_id,
        settings.auth_session_secret_ref,
    ))
    return {'required': bool(required), 'status': 'configuration_present' if configured else
            'configuration_required' if required else 'not_required'}


@router.get("/health/ready")
def readiness():
    settings = get_settings()
    database = check_database()
    redis = check_redis()
    redis_required = bool(settings.api_rate_limit_enabled or settings.observability_metrics_enabled or settings.runtime_scheduler_enabled)
    authentication = authentication_configuration(settings)
    ready = database == "ok" and (redis == "ok" or not redis_required) and authentication["status"] != "configuration_required"
    payload = {
        "status": "ready" if ready else "not_ready",
        "service": settings.service_name,
        "release_id": settings.release_id,
        "components": {
            "database": {"status": database, "required": True},
            "redis": {"status": redis, "required": redis_required},
            "authentication": authentication,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    return JSONResponse(payload, status_code=200 if ready else 503, headers={"Cache-Control": "no-store"})


@router.get("/health/status")
def public_status() -> dict:
    authentication = authentication_configuration(get_settings())
    database = check_database()
    redis = check_redis()
    return {
        "service": get_settings().service_name,
        "release_id": get_settings().release_id,
        "status": "operational" if database == "ok" and redis == "ok" and authentication["status"] != "configuration_required" else "degraded",
        "components": {
            "api": "operational",
            "authentication": authentication["status"],
            "database": "operational" if database == "ok" else "degraded",
            "background_services": "operational" if redis == "ok" else "degraded",
        },
        "generated_at": datetime.now(timezone.utc),
        "contains_customer_data": False,
    }
