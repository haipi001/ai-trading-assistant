from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from pydantic import BaseModel
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.auth import AuthenticatedUser
from app.core.auth import require_permission
from app.models import Approval
from app.models import OrderDraft
from app.models import OrderIntent
from app.models import RiskCheck
from app.schemas import ApprovalDecisionRequest
from app.schemas import ApprovalRead
from app.schemas import DraftModifyRequest
from app.schemas import OrderDraftRead
from app.schemas import RiskCheckOrderRequest
from app.schemas import RiskCheckRead
from app.services.risk import ApprovalBlockedError
from app.services.risk import RiskCheckBlockedError
from app.services.risk import RiskEngineService
from app.services.portfolio_time_series_risk import PortfolioTimeSeriesRiskError
from app.services.portfolio_time_series_risk import PortfolioTimeSeriesRiskService

router = APIRouter(tags=["risk"])


class PortfolioRiskRunRequest(BaseModel):
    lookback_days: int = 252
    drawdown_budget_pct: float | None = None
    sync_market_data: bool = True
    data_snapshot_ids: list[str] = Field(default_factory=list)


@router.get("/portfolio-risk/time-series/latest")
def latest_portfolio_time_series_risk(
    current_user: AuthenticatedUser = Depends(require_permission("read")),
    db: Session = Depends(get_db),
) -> dict:
    packet = PortfolioTimeSeriesRiskService(db).latest(user_id=current_user.user_id)
    if packet is None:
        raise HTTPException(status_code=404, detail="no portfolio time-series risk analysis found")
    return packet


@router.post("/portfolio-risk/time-series/sync-and-run")
def sync_and_run_portfolio_time_series_risk(
    payload: PortfolioRiskRunRequest,
    current_user: AuthenticatedUser = Depends(require_permission("read")),
    db: Session = Depends(get_db),
) -> dict:
    try:
        return PortfolioTimeSeriesRiskService(db).sync_and_analyze(
            user_id=current_user.user_id,
            lookback_days=payload.lookback_days,
            drawdown_budget_pct=payload.drawdown_budget_pct,
            sync_market_data=payload.sync_market_data,
            data_snapshot_ids=payload.data_snapshot_ids,
        )
    except PortfolioTimeSeriesRiskError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/portfolio-risk/time-series/sync-market-data")
def sync_portfolio_risk_market_data_for_review(
    payload: PortfolioRiskRunRequest,
    current_user: AuthenticatedUser = Depends(require_permission("read")),
    db: Session = Depends(get_db),
) -> dict:
    try:
        return PortfolioTimeSeriesRiskService(db).sync_market_data_for_review(
            user_id=current_user.user_id,
            lookback_days=payload.lookback_days,
        )
    except PortfolioTimeSeriesRiskError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/portfolio-risk/time-series/evidence-packet")
def create_portfolio_time_series_risk_evidence_packet(
    current_user: AuthenticatedUser = Depends(require_permission("read")),
    db: Session = Depends(get_db),
) -> dict:
    return PortfolioTimeSeriesRiskService(db).evidence_packet(user_id=current_user.user_id)


@router.post("/risk/check-order", response_model=RiskCheckRead, status_code=201)
def check_order_risk(payload: RiskCheckOrderRequest, db: Session = Depends(get_db)):
    order_intent = db.get(OrderIntent, payload.order_intent_id)
    if order_intent is None:
        raise HTTPException(status_code=404, detail="order intent not found")

    service = RiskEngineService(db)
    try:
        return service.check_order(order_intent, payload.risk_context())
    except RiskCheckBlockedError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/risk-checks", response_model=list[RiskCheckRead])
def list_risk_checks(
    order_intent_id: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
) -> list[RiskCheck]:
    query = select(RiskCheck)
    if order_intent_id:
        query = query.where(RiskCheck.order_intent_id == order_intent_id)
    return list(db.scalars(query.order_by(RiskCheck.created_at.desc(), RiskCheck.id.desc()).limit(limit)).all())


@router.post("/orders/intents/{order_intent_id}/draft", response_model=OrderDraftRead, status_code=201)
def create_order_draft_after_risk(
    order_intent_id: str,
    payload: RiskCheckOrderRequest,
    db: Session = Depends(get_db),
):
    if payload.order_intent_id != order_intent_id:
        raise HTTPException(status_code=422, detail="path order_intent_id does not match payload")
    order_intent = db.get(OrderIntent, order_intent_id)
    if order_intent is None:
        raise HTTPException(status_code=404, detail="order intent not found")

    service = RiskEngineService(db)
    try:
        return service.create_draft_after_risk(order_intent, payload.risk_context())
    except RiskCheckBlockedError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/orders/drafts/{order_draft_id}/approve", response_model=ApprovalRead, status_code=201)
def approve_order_draft(
    order_draft_id: str,
    payload: ApprovalDecisionRequest,
    db: Session = Depends(get_db),
):
    draft = db.get(OrderDraft, order_draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="order draft not found")

    service = RiskEngineService(db)
    try:
        return service.approve_draft(draft, payload.approver_id, payload.decision_reason)
    except (ApprovalBlockedError, RiskCheckBlockedError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/orders/drafts/{order_draft_id}/approvals", response_model=list[ApprovalRead])
def list_order_draft_approvals(
    order_draft_id: str,
    db: Session = Depends(get_db),
) -> list[Approval]:
    draft = db.get(OrderDraft, order_draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="order draft not found")
    return list(
        db.scalars(
            select(Approval)
            .where(Approval.order_draft_id == order_draft_id)
            .order_by(Approval.created_at.desc(), Approval.id.desc())
        ).all()
    )


@router.post("/orders/drafts/{order_draft_id}/reject", response_model=ApprovalRead, status_code=201)
def reject_order_draft(
    order_draft_id: str,
    payload: ApprovalDecisionRequest,
    db: Session = Depends(get_db),
):
    draft = db.get(OrderDraft, order_draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="order draft not found")

    service = RiskEngineService(db)
    return service.reject_draft(draft, payload.approver_id, payload.decision_reason)


@router.post("/orders/drafts/{order_draft_id}/modify", response_model=OrderDraftRead)
def modify_order_draft(
    order_draft_id: str,
    payload: DraftModifyRequest,
    db: Session = Depends(get_db),
):
    draft = db.get(OrderDraft, order_draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="order draft not found")

    service = RiskEngineService(db)
    return service.modify_draft(draft, payload.decision_reason)
