from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.auth import AuthenticatedUser
from app.core.auth import get_current_user
from app.core.auth import require_permission
from app.db.session import get_db
from app.models import ExportArtifact
from app.models import OperationalEvent
from app.models import SecretReference
from app.models import UserAccount
from app.schemas import BetaAccessCheckRead
from app.schemas import BetaReadinessRead
from app.schemas import BetaWhoAmIRead
from app.schemas import ExportArtifactRead
from app.schemas import ExternalBetaLaunchReportRead
from app.schemas import OperationalEventCreate
from app.schemas import OperationalEventRead
from app.schemas import SecretReferenceCreate
from app.schemas import SecretReferenceRead
from app.schemas import UserAccountCreate
from app.schemas import UserAccountRead
from app.services.beta_readiness import BetaReadinessError
from app.services.beta_readiness import BetaReadinessService

router = APIRouter(prefix="/beta", tags=["beta-readiness"])


@router.get("/whoami", response_model=BetaWhoAmIRead)
def whoami(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return BetaReadinessService(db).whoami(current_user)


@router.get("/access-check", response_model=BetaAccessCheckRead)
def access_check(
    permission: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return BetaReadinessService(db).access_check(current_user=current_user, permission=permission)


@router.get("/readiness", response_model=BetaReadinessRead)
def readiness(
    current_user: AuthenticatedUser = Depends(require_permission("readiness:read")),
    db: Session = Depends(get_db),
) -> dict:
    return BetaReadinessService(db).readiness(current_user=current_user)


@router.get("/external-launch-report", response_model=ExternalBetaLaunchReportRead)
def external_launch_report(
    current_user: AuthenticatedUser = Depends(require_permission("readiness:read")),
    db: Session = Depends(get_db),
) -> dict:
    return BetaReadinessService(db).external_launch_report(current_user=current_user)


@router.get("/release-control-report")
def release_control_report(
    current_user: AuthenticatedUser = Depends(require_permission("readiness:read")),
    db: Session = Depends(get_db),
) -> dict:
    return BetaReadinessService(db).release_control_report(current_user=current_user)


@router.get("/invitation-packet")
def invitation_packet(
    current_user: AuthenticatedUser = Depends(require_permission("readiness:read")),
    db: Session = Depends(get_db),
) -> dict:
    return BetaReadinessService(db).invitation_packet(current_user=current_user)


@router.get("/users", response_model=list[UserAccountRead])
def list_users(
    limit: int = 100,
    current_user: AuthenticatedUser = Depends(require_permission("users:read")),
    db: Session = Depends(get_db),
) -> list[UserAccount]:
    _ = current_user
    return BetaReadinessService(db).list_users(limit=limit)


@router.post("/users", response_model=UserAccountRead, status_code=201)
def upsert_user(
    payload: UserAccountCreate,
    current_user: AuthenticatedUser = Depends(require_permission("users:write")),
    db: Session = Depends(get_db),
) -> UserAccount:
    _ = current_user
    try:
        return BetaReadinessService(db).upsert_user(**payload.model_dump())
    except BetaReadinessError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/secrets/references", response_model=list[SecretReferenceRead])
def list_secret_references(
    user_id: str | None = None,
    limit: int = 100,
    current_user: AuthenticatedUser = Depends(require_permission("secrets:read")),
    db: Session = Depends(get_db),
) -> list[SecretReference]:
    _ = current_user
    return BetaReadinessService(db).list_secret_references(user_id=user_id, limit=limit)


@router.post("/secrets/references", response_model=SecretReferenceRead, status_code=201)
def create_secret_reference(
    payload: SecretReferenceCreate,
    current_user: AuthenticatedUser = Depends(require_permission("secrets:write")),
    db: Session = Depends(get_db),
) -> SecretReference:
    try:
        return BetaReadinessService(db).create_secret_reference(
            current_user=current_user,
            **payload.model_dump(),
        )
    except BetaReadinessError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/events", response_model=list[OperationalEventRead])
def list_events(
    severity: str | None = None,
    status: str | None = None,
    query: str | None = None,
    limit: int = 100,
    current_user: AuthenticatedUser = Depends(require_permission("events:read")),
    db: Session = Depends(get_db),
) -> list[dict]:
    _ = current_user
    return BetaReadinessService(db).list_events(severity=severity, status=status, search_query=query, limit=limit)


@router.post("/events", response_model=OperationalEventRead, status_code=201)
def create_event(
    payload: OperationalEventCreate,
    current_user: AuthenticatedUser = Depends(require_permission("events:write")),
    db: Session = Depends(get_db),
) -> OperationalEvent:
    try:
        return BetaReadinessService(db).create_event(current_user=current_user, **payload.model_dump())
    except BetaReadinessError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/backup-manifest", response_model=ExportArtifactRead, status_code=201)
def create_backup_manifest(
    current_user: AuthenticatedUser = Depends(require_permission("backups:write")),
    db: Session = Depends(get_db),
) -> ExportArtifact:
    return BetaReadinessService(db).create_backup_manifest(current_user=current_user)
