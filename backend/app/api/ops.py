from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from fastapi.responses import JSONResponse
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.core.auth import AuthenticatedUser
from app.core.auth import require_permission
from app.core.config import get_settings
from app.core.observability import ObservabilityUnavailable
from app.core.observability import RedisRequestMetrics
from app.db.session import get_db
from app.models import ProductionReadinessTarget
from app.schemas import OpsRestoreDrillReportRead
from app.schemas import OpsStabilityReportRead
from app.schemas import ProductionReadinessTargetCreate
from app.schemas import ProductionReadinessTargetRead
from app.services.ops_readiness import OpsReadinessService

router = APIRouter(prefix="/ops", tags=["ops-readiness"])


@router.get("/observability")
def observability_report(
    current_user: AuthenticatedUser = Depends(require_permission("readiness:read")),
) -> dict:
    _ = current_user
    settings = get_settings()
    try:
        return RedisRequestMetrics(settings).snapshot(window_hours=24)
    except ObservabilityUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/metrics", response_class=PlainTextResponse)
def prometheus_metrics(
    current_user: AuthenticatedUser = Depends(require_permission("readiness:read")),
) -> str:
    _ = current_user
    settings = get_settings()
    metrics = RedisRequestMetrics(settings)
    try:
        snapshot = metrics.snapshot(window_hours=24)
    except ObservabilityUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return metrics.prometheus(snapshot)


@router.post("/observability/evaluate", status_code=201)
def evaluate_observability_alert(
    current_user: AuthenticatedUser = Depends(require_permission("events:write")),
    db: Session = Depends(get_db),
) -> dict:
    return OpsReadinessService(db).evaluate_observability_alert(user_id=current_user.user_id)


@router.post("/observability/fault-injection")
def inject_staging_observability_failure(
    current_user: AuthenticatedUser = Depends(require_permission("users:write")),
) -> JSONResponse:
    """Return a controlled 503 so staging can prove the real monitoring path."""
    _ = current_user
    settings = get_settings()
    if not (
        settings.staging_fault_injection_enabled
        and settings.environment == "staging"
        and settings.deployment_target == "managed-staging"
    ):
        raise HTTPException(status_code=404, detail="not found")
    return JSONResponse(
        {
            "status": "injected_staging_failure",
            "contains_customer_data": False,
            "execution_available": False,
        },
        status_code=503,
        headers={"Cache-Control": "no-store"},
    )


@router.get("/stability-report", response_model=OpsStabilityReportRead)
def stability_report(
    current_user: AuthenticatedUser = Depends(require_permission("readiness:read")),
    db: Session = Depends(get_db),
) -> dict:
    return OpsReadinessService(db).stability_report(user_id=current_user.user_id)


@router.get("/product-stability-packet")
def product_stability_packet(
    current_user: AuthenticatedUser = Depends(require_permission("readiness:read")),
    db: Session = Depends(get_db),
) -> dict:
    return OpsReadinessService(db).product_stability_packet(user_id=current_user.user_id)


@router.get("/notification-channels")
def notification_channel_status(
    current_user: AuthenticatedUser = Depends(require_permission("readiness:read")),
    db: Session = Depends(get_db),
) -> dict:
    return OpsReadinessService(db).notification_channel_status(user_id=current_user.user_id)


@router.post("/notification-channels/dry-run", status_code=201)
def notification_dry_run(
    payload: dict | None = None,
    current_user: AuthenticatedUser = Depends(require_permission("readiness:write")),
    db: Session = Depends(get_db),
) -> dict:
    try:
        return OpsReadinessService(db).notification_dry_run(
            user_id=current_user.user_id,
            channel=str((payload or {}).get("channel") or "in_app"),
            subject=str((payload or {}).get("subject") or "AI Trading OS test"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/notification-channels/webhook/test", status_code=201)
def notification_webhook_test(
    current_user: AuthenticatedUser = Depends(require_permission("readiness:write")),
    db: Session = Depends(get_db),
) -> dict:
    try:
        return OpsReadinessService(db).notification_webhook_test(user_id=current_user.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/security-control-plane")
def security_control_plane(
    current_user: AuthenticatedUser = Depends(require_permission("readiness:read")),
    db: Session = Depends(get_db),
) -> dict:
    return OpsReadinessService(db).security_control_plane(user_id=current_user.user_id)


@router.get("/production-targets", response_model=list[ProductionReadinessTargetRead])
def list_production_targets(
    current_user: AuthenticatedUser = Depends(require_permission("readiness:read")),
    db: Session = Depends(get_db),
) -> list[ProductionReadinessTarget]:
    return OpsReadinessService(db).list_production_targets(user_id=current_user.user_id)


@router.post("/production-targets", response_model=ProductionReadinessTargetRead, status_code=201)
def upsert_production_target(
    payload: ProductionReadinessTargetCreate,
    current_user: AuthenticatedUser = Depends(require_permission("readiness:write")),
    db: Session = Depends(get_db),
) -> ProductionReadinessTarget:
    try:
        return OpsReadinessService(db).upsert_production_target(
            **{**payload.model_dump(), "user_id": current_user.user_id},
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/restore-drill", response_model=OpsRestoreDrillReportRead, status_code=201)
def restore_drill(
    current_user: AuthenticatedUser = Depends(require_permission("readiness:write")),
    db: Session = Depends(get_db),
) -> dict:
    return OpsReadinessService(db).restore_drill(user_id=current_user.user_id)
