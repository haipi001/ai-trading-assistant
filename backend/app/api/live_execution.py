from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from fastapi import Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas import BrokerHealthResponse
from app.schemas import KillSwitchCheckResponse
from app.schemas import KillSwitchDisengageRequest
from app.schemas import KillSwitchEngageRequest
from app.schemas import KillSwitchEntry
from app.schemas import LiveExecutionApprovalRequest
from app.schemas import LiveExecutionApprovalResponse
from app.schemas import LiveExecutionConfigCreate
from app.schemas import LiveExecutionConfigRead
from app.schemas import LiveExecutionExecuteRequest
from app.schemas import LiveExecutionExecuteResponse
from app.schemas import LiveExecutionHistoryEntry
from app.schemas import LiveExecutionPrepareRequest
from app.schemas import LiveExecutionPrepareResponse
from app.schemas import LiveExecutionSandboxRequest
from app.schemas import LiveExecutionSandboxResponse
from app.schemas import LiveExecutionSmallPilotReadinessRequest
from app.schemas import LiveExecutionSmallPilotReadinessResponse
from app.services.live_execution import KillSwitchService
from app.services.live_execution import LiveExecutionError
from app.services.live_execution import LiveExecutionNotFoundError
from app.services.live_execution import LiveExecutionService

router = APIRouter(prefix="/live-execution", tags=["live-execution"])
kill_switch_router = APIRouter(prefix="/kill-switch", tags=["kill-switch"])


@router.get("/configs", response_model=list[LiveExecutionConfigRead])
def list_live_execution_configs(limit: int = 100, db: Session = Depends(get_db)):
    return LiveExecutionService(db).list_configs(limit=limit)


@router.post("/configs", response_model=LiveExecutionConfigRead, status_code=201)
def create_live_execution_config(payload: LiveExecutionConfigCreate, db: Session = Depends(get_db)):
    try:
        return LiveExecutionService(db).create_config(**payload.model_dump())
    except LiveExecutionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/configs/{config_id}", status_code=204)
def delete_live_execution_config(config_id: str, db: Session = Depends(get_db)) -> Response:
    try:
        LiveExecutionService(db).disable_config(config_id)
    except LiveExecutionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=204)


@router.post("/configs/{config_id}/health-check", response_model=BrokerHealthResponse)
def broker_health_check(config_id: str, db: Session = Depends(get_db)):
    try:
        return LiveExecutionService(db).broker_health_check(config_id)
    except LiveExecutionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/prepare", response_model=LiveExecutionPrepareResponse)
def prepare_live_execution(payload: LiveExecutionPrepareRequest, db: Session = Depends(get_db)):
    try:
        return LiveExecutionService(db).prepare(payload.order_draft_id)
    except LiveExecutionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/approve", response_model=LiveExecutionApprovalResponse)
def approve_live_execution(payload: LiveExecutionApprovalRequest, db: Session = Depends(get_db)):
    try:
        return LiveExecutionService(db).approve(**payload.model_dump())
    except LiveExecutionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/execute", response_model=LiveExecutionExecuteResponse, status_code=201)
def execute_live_order(payload: LiveExecutionExecuteRequest, db: Session = Depends(get_db)):
    try:
        return LiveExecutionService(db).execute(**payload.model_dump())
    except LiveExecutionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/sandbox-run", response_model=LiveExecutionSandboxResponse)
def sandbox_live_execution(payload: LiveExecutionSandboxRequest, db: Session = Depends(get_db)):
    try:
        return LiveExecutionService(db).sandbox_run(**payload.model_dump())
    except LiveExecutionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/sandbox-certification")
def sandbox_certification(payload: LiveExecutionSandboxRequest, db: Session = Depends(get_db)):
    try:
        return LiveExecutionService(db).sandbox_certification(
            order_draft_id=payload.order_draft_id,
            approver_id=payload.approver_id,
            force_fill_price=payload.force_fill_price,
        )
    except LiveExecutionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/sandbox-drill-report")
def sandbox_drill_report(payload: LiveExecutionSandboxRequest, db: Session = Depends(get_db)):
    try:
        return LiveExecutionService(db).sandbox_drill_report(
            order_draft_id=payload.order_draft_id,
            approver_id=payload.approver_id,
            force_fill_price=payload.force_fill_price,
        )
    except LiveExecutionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/small-pilot-readiness", response_model=LiveExecutionSmallPilotReadinessResponse)
def small_pilot_readiness(payload: LiveExecutionSmallPilotReadinessRequest, db: Session = Depends(get_db)):
    try:
        return LiveExecutionService(db).small_pilot_readiness(**payload.model_dump())
    except LiveExecutionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/broker-reconciliation-plan")
def broker_reconciliation_plan(payload: LiveExecutionSandboxRequest, db: Session = Depends(get_db)):
    try:
        return LiveExecutionService(db).broker_reconciliation_plan(
            order_draft_id=payload.order_draft_id,
            approver_id=payload.approver_id,
            force_fill_price=payload.force_fill_price,
        )
    except LiveExecutionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/broker-sandbox-proof-packet")
def broker_sandbox_proof_packet(payload: LiveExecutionSandboxRequest, db: Session = Depends(get_db)):
    try:
        return LiveExecutionService(db).sandbox_proof_packet(
            order_draft_id=payload.order_draft_id,
            approver_id=payload.approver_id or "sandbox-proof-reviewer",
            force_fill_price=payload.force_fill_price,
        )
    except LiveExecutionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/small-pilot-approval-packet")
def small_pilot_approval_packet(payload: LiveExecutionSmallPilotReadinessRequest, db: Session = Depends(get_db)):
    try:
        return LiveExecutionService(db).small_pilot_approval_packet(**payload.model_dump())
    except LiveExecutionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/small-pilot-go-no-go")
def small_pilot_go_no_go(payload: LiveExecutionSmallPilotReadinessRequest, db: Session = Depends(get_db)):
    try:
        return LiveExecutionService(db).small_pilot_go_no_go(**payload.model_dump())
    except LiveExecutionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/history", response_model=list[LiveExecutionHistoryEntry])
def live_execution_history(limit: int = 50, db: Session = Depends(get_db)):
    return LiveExecutionService(db).history(limit=limit)


@kill_switch_router.get("/active", response_model=list[KillSwitchEntry])
def active_kill_switches(db: Session = Depends(get_db)):
    return KillSwitchService(db).active()


@kill_switch_router.post("/engage", response_model=KillSwitchEntry, status_code=201)
def engage_kill_switch(payload: KillSwitchEngageRequest, db: Session = Depends(get_db)):
    try:
        return KillSwitchService(db).engage(**payload.model_dump())
    except LiveExecutionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@kill_switch_router.post("/disengage")
def disengage_kill_switch(payload: KillSwitchDisengageRequest, db: Session = Depends(get_db)):
    return {"disengaged": KillSwitchService(db).disengage(**payload.model_dump())}


@kill_switch_router.post("/check", response_model=KillSwitchCheckResponse)
def check_kill_switch(
    account_id: str | None = None,
    asset_id: str | None = None,
    db: Session = Depends(get_db),
):
    return KillSwitchService(db).check(account_id=account_id, asset_id=asset_id)


@kill_switch_router.get("/history", response_model=list[KillSwitchEntry])
def kill_switch_history(limit: int = 100, db: Session = Depends(get_db)):
    return KillSwitchService(db).history(limit=limit)
