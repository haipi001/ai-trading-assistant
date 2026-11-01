from fastapi import APIRouter
from fastapi import Body
from fastapi import Depends
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import ExportArtifact
from app.models import LocalUserConfig
from app.models import Reminder
from app.models import WatchlistItem
from app.schemas import DailyExportRequest
from app.schemas import DailyActionQueueRead
from app.schemas import DailyUseOverviewRead
from app.schemas import ExportArtifactRead
from app.schemas import LocalUserConfigRead
from app.schemas import LocalUserConfigUpsert
from app.schemas import ReminderCreate
from app.schemas import ReminderRead
from app.schemas import ReminderUpdate
from app.schemas import WatchlistItemCreate
from app.schemas import WatchlistItemRead
from app.schemas import WatchlistItemUpdate
from app.services.daily_use import DailyUseError
from app.services.daily_use import DailyUseService

router = APIRouter(prefix="/daily-use", tags=["daily-use"])


@router.get("/overview", response_model=DailyUseOverviewRead)
def get_daily_use_overview(user_id: str = "default-user", db: Session = Depends(get_db)) -> dict:
    return DailyUseService(db).overview(user_id=user_id)


@router.get("/action-queue", response_model=DailyActionQueueRead)
def get_daily_action_queue(
    user_id: str = "default-user",
    limit: int = 20,
    source: str | None = None,
    priority: str | None = None,
    action_type: str | None = None,
    db: Session = Depends(get_db),
) -> dict:
    return DailyUseService(db).action_queue(
        user_id=user_id,
        limit=limit,
        source=source,
        priority=priority,
        action_type=action_type,
    )


@router.get("/onboarding")
def get_daily_onboarding(user_id: str = "default-user", db: Session = Depends(get_db)) -> dict:
    return DailyUseService(db).onboarding_status(user_id=user_id)


@router.get("/local-start")
def get_local_start(user_id: str = "default-user", db: Session = Depends(get_db)) -> dict:
    return DailyUseService(db).local_start_status(user_id=user_id)


@router.get("/scheduler-status")
def get_runtime_scheduler_status(user_id: str = "default-user", db: Session = Depends(get_db)) -> dict:
    return DailyUseService(db).scheduler_status(user_id=user_id)


@router.post("/scheduler-tick")
def run_runtime_scheduler_tick(
    payload: dict | None = None,
    user_id: str = "default-user",
    db: Session = Depends(get_db),
) -> dict:
    try:
        return DailyUseService(db).run_scheduler_tick(user_id=user_id, action=(payload or {}).get("action"))
    except DailyUseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/workspace-status")
def get_local_workspace_status(user_id: str = "default-user", db: Session = Depends(get_db)) -> dict:
    return DailyUseService(db).workspace_status(user_id=user_id)


@router.get("/self-use-readiness")
def get_self_use_readiness(user_id: str = "default-user", db: Session = Depends(get_db)) -> dict:
    return DailyUseService(db).self_use_readiness(user_id=user_id)


@router.get("/investment-workflow-status")
def get_investment_workflow_status(user_id: str = "default-user", db: Session = Depends(get_db)) -> dict:
    return DailyUseService(db).investment_workflow_status(user_id=user_id)


@router.post("/local-handoff-packet")
def create_local_handoff_packet(user_id: str = "default-user", db: Session = Depends(get_db)) -> dict:
    return DailyUseService(db).local_handoff_packet(user_id=user_id)


@router.post("/local-start")
def initialize_local_start(
    payload: dict,
    user_id: str = "default-user",
    db: Session = Depends(get_db),
) -> dict:
    try:
        return DailyUseService(db).initialize_local_start(user_id=user_id, payload=payload)
    except DailyUseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/onboarding")
def update_daily_onboarding(
    payload: dict = Body(...),
    user_id: str = "default-user",
    db: Session = Depends(get_db),
) -> dict:
    try:
        return DailyUseService(db).update_onboarding(user_id=user_id, state=payload)
    except DailyUseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/daily-open")
def create_daily_open(user_id: str = "default-user", db: Session = Depends(get_db)) -> dict:
    return DailyUseService(db).daily_open(user_id=user_id)


@router.post("/daily-close")
def create_daily_close(
    payload: dict | None = Body(default=None),
    user_id: str = "default-user",
    db: Session = Depends(get_db),
) -> dict:
    try:
        return DailyUseService(db).daily_close(user_id=user_id, review_json=payload or {})
    except DailyUseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/daily-history")
def get_daily_history(user_id: str = "default-user", limit: int = 30, db: Session = Depends(get_db)) -> dict:
    return DailyUseService(db).daily_history(user_id=user_id, limit=limit)


@router.post("/action-queue/batch-actions")
def apply_daily_queue_batch_action(
    payload: dict,
    user_id: str = "default-user",
    db: Session = Depends(get_db),
) -> dict:
    try:
        return DailyUseService(db).apply_queue_batch_action(
            queue_item_ids=list(payload.get("queue_item_ids") or []),
            user_id=user_id,
            action=str(payload.get("action") or ""),
            assignee_id=payload.get("assignee_id"),
            snooze_minutes=int(payload.get("snooze_minutes") or 60),
        )
    except DailyUseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/drilldown/{queue_item_id:path}")
def get_daily_drilldown(queue_item_id: str, user_id: str = "default-user", db: Session = Depends(get_db)) -> dict:
    try:
        return DailyUseService(db).drilldown(queue_item_id=queue_item_id, user_id=user_id)
    except DailyUseError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/action-queue/{queue_item_id:path}/actions")
def apply_daily_queue_action(
    queue_item_id: str,
    payload: dict,
    user_id: str = "default-user",
    db: Session = Depends(get_db),
) -> dict:
    try:
        return DailyUseService(db).apply_queue_action(
            queue_item_id=queue_item_id,
            user_id=user_id,
            action=str(payload.get("action") or ""),
            assignee_id=payload.get("assignee_id"),
            snooze_minutes=int(payload.get("snooze_minutes") or 60),
        )
    except DailyUseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/action-queue/{queue_item_id:path}/run")
def run_daily_queue_item(
    queue_item_id: str,
    payload: dict | None = None,
    user_id: str = "default-user",
    db: Session = Depends(get_db),
) -> dict:
    try:
        return DailyUseService(db).run_queue_item(queue_item_id=queue_item_id, user_id=user_id, payload=payload or {})
    except DailyUseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/watchlist", response_model=list[WatchlistItemRead])
def list_watchlist(
    user_id: str = "default-user",
    active_only: bool = True,
    limit: int = 100,
    db: Session = Depends(get_db),
) -> list[WatchlistItem]:
    return DailyUseService(db).list_watchlist(user_id=user_id, active_only=active_only, limit=limit)


@router.post("/watchlist", response_model=WatchlistItemRead, status_code=201)
def create_watchlist_item(payload: WatchlistItemCreate, db: Session = Depends(get_db)) -> WatchlistItem:
    try:
        return DailyUseService(db).create_watchlist_item(**payload.model_dump())
    except DailyUseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.patch("/watchlist/{item_id}", response_model=WatchlistItemRead)
def update_watchlist_item(item_id: str, payload: WatchlistItemUpdate, db: Session = Depends(get_db)) -> WatchlistItem:
    try:
        return DailyUseService(db).update_watchlist_item(item_id, **payload.model_dump(exclude_unset=True))
    except DailyUseError as exc:
        raise HTTPException(status_code=404 if "not found" in str(exc) else 422, detail=str(exc)) from exc


@router.delete("/watchlist/{item_id}", response_model=WatchlistItemRead)
def deactivate_watchlist_item(item_id: str, db: Session = Depends(get_db)) -> WatchlistItem:
    try:
        return DailyUseService(db).deactivate_watchlist_item(item_id)
    except DailyUseError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/reminders", response_model=list[ReminderRead])
def list_reminders(
    user_id: str = "default-user",
    status: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
) -> list[Reminder]:
    return DailyUseService(db).list_reminders(user_id=user_id, status=status, limit=limit)


@router.post("/reminders", response_model=ReminderRead, status_code=201)
def create_reminder(payload: ReminderCreate, db: Session = Depends(get_db)) -> Reminder:
    try:
        return DailyUseService(db).create_reminder(**payload.model_dump())
    except DailyUseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.patch("/reminders/{reminder_id}", response_model=ReminderRead)
def update_reminder(reminder_id: str, payload: ReminderUpdate, db: Session = Depends(get_db)) -> Reminder:
    try:
        return DailyUseService(db).update_reminder(reminder_id, **payload.model_dump(exclude_unset=True))
    except DailyUseError as exc:
        raise HTTPException(status_code=404 if "not found" in str(exc) else 422, detail=str(exc)) from exc


@router.post("/reminders/{reminder_id}/complete", response_model=ReminderRead)
def complete_reminder(reminder_id: str, db: Session = Depends(get_db)) -> Reminder:
    try:
        return DailyUseService(db).complete_reminder(reminder_id)
    except DailyUseError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/local-cleanup/e2e-artifacts")
def cleanup_local_test_artifacts(
    payload: dict | None = Body(default=None),
    user_id: str = "default-user",
    db: Session = Depends(get_db),
) -> dict:
    try:
        return DailyUseService(db).cleanup_local_test_artifacts(user_id=user_id, dry_run=bool((payload or {}).get("dry_run")))
    except DailyUseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/local-config", response_model=list[LocalUserConfigRead])
def list_local_config(user_id: str = "default-user", db: Session = Depends(get_db)) -> list[LocalUserConfig]:
    return DailyUseService(db).list_local_config(user_id=user_id)


@router.put("/local-config/{config_key}", response_model=LocalUserConfigRead)
def upsert_local_config(config_key: str, payload: LocalUserConfigUpsert, db: Session = Depends(get_db)) -> LocalUserConfig:
    try:
        return DailyUseService(db).upsert_local_config(
            config_key=config_key,
            user_id=payload.user_id,
            value_json=payload.value_json,
            description=payload.description,
        )
    except DailyUseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/exports", response_model=list[ExportArtifactRead])
def list_exports(user_id: str = "default-user", limit: int = 50, db: Session = Depends(get_db)) -> list[ExportArtifact]:
    return DailyUseService(db).list_exports(user_id=user_id, limit=limit)


@router.get("/exports/{artifact_id}", response_model=ExportArtifactRead)
def get_export(artifact_id: str, db: Session = Depends(get_db)) -> ExportArtifact:
    try:
        return DailyUseService(db).get_export(artifact_id)
    except DailyUseError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/exports", response_model=ExportArtifactRead, status_code=201)
def create_export(payload: DailyExportRequest, db: Session = Depends(get_db)) -> ExportArtifact:
    try:
        return DailyUseService(db).create_export(
            user_id=payload.user_id,
            export_type=payload.export_type,
            include_sections=payload.include_sections,
        )
    except DailyUseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/backup-manifest", response_model=ExportArtifactRead, status_code=201)
def create_backup_manifest(user_id: str = "default-user", db: Session = Depends(get_db)) -> ExportArtifact:
    return DailyUseService(db).create_backup_manifest(user_id=user_id)
