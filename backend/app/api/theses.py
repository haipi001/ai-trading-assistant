from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas import InvestmentThesisRead
from app.schemas import ThesisContextRead
from app.schemas import ThesisCaptureRequest
from app.schemas import ThesisCheckpointRead
from app.schemas import ThesisEventCreate
from app.schemas import ThesisEventRead
from app.schemas import ThesisMonitorRequest
from app.schemas import ThesisViolationMessageRequest
from app.schemas import ThesisViolationMessageResponse
from app.services.theses import AssetNotFoundError
from app.services.theses import InvalidThesisOutputError
from app.services.theses import ThesisCaptureService
from app.services.theses import ThesisMonitorService
from app.services.theses import ThesisNotFoundError
from app.api.production import production_user
from app.core.auth import AuthenticatedUser
from app.services.data_catalog import DataTrustGateError

from pydantic import BaseModel, ConfigDict, Field
from typing import Annotated
from app.core.auth import require_permission
from app.models import Account, Asset, AuditLog, InvestmentThesis
from app.services.account_identity import account_markets

router = APIRouter(prefix="/theses", tags=["theses"])

class ManualPaperThesisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)
    asset_id: str = Field(min_length=1,max_length=128)
    account_id: str = Field(min_length=1,max_length=128)
    entry_reason: str = Field(min_length=8,max_length=4000)
    key_drivers: list[Annotated[str, Field(min_length=1,max_length=500)]] = Field(min_length=1,max_length=20)
    invalidation_conditions: list[Annotated[str, Field(min_length=1,max_length=500)]] = Field(min_length=1,max_length=20)
    expected_horizon: str = Field(min_length=1,max_length=64)
    target_condition: str = Field(min_length=8,max_length=2000)
    max_loss_tolerance_pct: float = Field(gt=0,le=1,strict=True)
    confidence: float = Field(ge=0,le=1,strict=True)


class ManualPaperThesisResponse(BaseModel):
    thesis: InvestmentThesisRead
    execution_available: bool = False


@router.post("/manual-paper",response_model=ManualPaperThesisResponse,status_code=201)
def create_manual_paper_thesis(payload: ManualPaperThesisRequest,
    actor: AuthenticatedUser = Depends(require_permission("proposal:create")),
    db: Session = Depends(get_db)):
    account = db.get(Account,payload.account_id)
    asset = db.get(Asset,payload.asset_id)
    if account is None or account.user_id != actor.user_id or asset is None:
        raise HTTPException(404,detail="account or asset not found")
    market = "stocks" if asset.asset_type in {"stock","etf"} else "cex" if asset.asset_type == "crypto" else None
    if account.mode != "paper" or account.live_trading_enabled or market not in account_markets(account) or asset.chain_id or asset.contract_address:
        raise HTTPException(422,detail="manual Paper thesis requires compatible Paper account and stock/ETF or CEX asset")
    thesis = InvestmentThesis(user_id=actor.user_id,asset_id=asset.id,account_id=account.id,
        entry_reason=payload.entry_reason,key_drivers_json={"items":payload.key_drivers},
        invalidation_conditions_json={"items":payload.invalidation_conditions},
        expected_horizon=payload.expected_horizon,target_condition=payload.target_condition,
        max_loss_tolerance_pct=payload.max_loss_tolerance_pct,confidence=payload.confidence,
        position_plan_json={"execution_available":False,"human_authored":True},source="terminal_manual",status="active")
    db.add(thesis);db.flush()
    db.add(AuditLog(user_id=actor.user_id,actor_type="user",actor_id=actor.user_id,
        action="terminal.manual_thesis.created",entity_type="InvestmentThesis",entity_id=thesis.id,
        payload_json={"account_id":account.id,"asset_id":asset.id,"source":"human","execution_available":False}))
    db.commit();db.refresh(thesis)
    return ManualPaperThesisResponse(thesis=thesis,execution_available=False)



@router.post("/capture", response_model=InvestmentThesisRead, status_code=201)
def capture_thesis(payload: ThesisCaptureRequest, actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)):
    if actor.auth_required and payload.user_id != actor.user_id:
        raise HTTPException(status_code=403, detail="user_id must match authenticated user")
    service = ThesisCaptureService(db, actor=actor)
    try:
        return service.capture(
            user_id=payload.user_id,
            asset_id=payload.asset_id,
            account_id=payload.account_id,
            position_id=payload.position_id,
            strategy_playbook_id=payload.strategy_playbook_id,
            data_snapshot_id=payload.data_snapshot_id,
            user_rationale=payload.user_rationale,
            intended_action=payload.intended_action,
            current_position=payload.current_position,
            market_context=payload.market_context,
            provider_name=payload.provider,
        )
    except DataTrustGateError as exc:
        raise HTTPException(status_code=409, detail={"code": "data_trust_gate_blocked", **exc.gate}) from exc
    except AssetNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidThesisOutputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/{thesis_id}/monitor", response_model=ThesisCheckpointRead, status_code=201)
def monitor_thesis(thesis_id: str, payload: ThesisMonitorRequest, actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)):
    service = ThesisMonitorService(db, actor=actor)
    try:
        return service.monitor(
            thesis_id=thesis_id,
            new_facts=payload.new_facts,
            news=payload.news,
            price_movement=payload.price_movement,
            earnings_data=payload.earnings_data,
            technical_signals=payload.technical_signals,
            onchain_signals=payload.onchain_signals,
            data_snapshot_id=payload.data_snapshot_id,
            provider_name=payload.provider,
        )
    except DataTrustGateError as exc:
        raise HTTPException(status_code=409, detail={"code": "data_trust_gate_blocked", **exc.gate}) from exc
    except ThesisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidThesisOutputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{thesis_id}/checkpoints", response_model=list[ThesisCheckpointRead])
def list_thesis_checkpoints(thesis_id: str, limit: int = 100, db: Session = Depends(get_db)):
    service = ThesisMonitorService(db)
    try:
        return service.list_checkpoints(thesis_id, limit=limit)
    except ThesisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/thesis-events", response_model=list[ThesisEventRead])
def list_thesis_events(thesis_id: str | None = None, limit: int = 50, db: Session = Depends(get_db)):
    return ThesisMonitorService(db).list_events(thesis_id=thesis_id, limit=limit)


@router.post("/thesis-events", response_model=ThesisEventRead, status_code=201)
def create_thesis_event(payload: ThesisEventCreate, db: Session = Depends(get_db)):
    try:
        return ThesisMonitorService(db).create_event(
            thesis_id=payload.thesis_id,
            event_type=payload.event_type,
            title=payload.title,
            description=payload.description,
            source=payload.source,
            event_time=payload.event_time,
            impact_json=payload.impact_json,
        )
    except ThesisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{thesis_id}/context", response_model=ThesisContextRead)
def get_thesis_context(thesis_id: str, db: Session = Depends(get_db)):
    try:
        return ThesisMonitorService(db).build_context(thesis_id)
    except ThesisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{thesis_id}/violation-message", response_model=ThesisViolationMessageResponse, status_code=201)
def create_thesis_violation_message(
    thesis_id: str,
    payload: ThesisViolationMessageRequest,
    actor: AuthenticatedUser = Depends(production_user),
    db: Session = Depends(get_db),
):
    if actor.auth_required and payload.user_id != actor.user_id:
        raise HTTPException(status_code=403, detail="user_id must match authenticated user")
    service = ThesisMonitorService(db, actor=actor)
    try:
        violation, message = service.create_violation_message(
            thesis_id=thesis_id,
            user_id=payload.user_id,
            current_action=payload.current_action,
            related_order_intent_id=payload.related_order_intent_id,
            prior_user_statement=payload.prior_user_statement,
            intervention_level=payload.intervention_level,
            provider_name=payload.provider,
        )
        return {
            "violation": violation,
            "message": message.message,
            "intervention_level": message.intervention_level,
        }
    except ThesisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidThesisOutputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
