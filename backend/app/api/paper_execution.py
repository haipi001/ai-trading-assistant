from app.core.auth import require_permission, AuthenticatedUser
from pydantic import BaseModel
from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Execution
from app.models import OrderDraft
from app.models import PaperCorporateAction
from app.models import PaperTaxLot
from app.models import PaperTaxLotRealization
from app.models import PostTradeReview
from app.models import TradeJournalEntry
from app.schemas import ExecutionRead
from app.schemas import PaperCashDividendRequest
from app.schemas import PaperCorporateActionRead
from app.schemas import PaperCorporateActionResponse
from app.schemas import PaperExecutionRequest
from app.schemas import PaperExecutionResponse
from app.schemas import PaperStockSplitRequest
from app.schemas import PaperTaxLotRead
from app.schemas import PaperTaxLotRealizationRead
from app.schemas import PostTradeReviewRead
from app.schemas import PostTradeReviewUpdate
from app.schemas import TradeJournalEntryRead
from app.services.paper_execution import PaperExecutionBlockedError
from app.services.paper_execution import PaperExecutionConflictError
from app.services.paper_execution import PaperExecutionService

from app.schemas.core import ManualPaperEvidenceRead
from app.services.manual_trade_evidence import ManualEvidenceError, prepare_manual_evidence, read_manual_evidence

router = APIRouter(tags=["paper-execution"])


@router.get("/paper-executions", response_model=list[ExecutionRead], dependencies=[Depends(require_permission("read"))])
def list_paper_executions(limit: int = 100, db: Session = Depends(get_db)) -> list[Execution]:
    return list(
        db.scalars(
            select(Execution)
            .where(Execution.execution_mode == "paper")
            .order_by(Execution.created_at.desc(), Execution.id.desc())
            .limit(limit)
        ).all()
    )


class PaperReviewContext(BaseModel):
    execution: ExecutionRead
    journal_entry: TradeJournalEntryRead
    post_trade_review: PostTradeReviewRead
    execution_available: bool = False


@router.get('/paper-executions/{execution_id}/review-context', response_model=PaperReviewContext)
def paper_review_context(execution_id: str,
                         actor: AuthenticatedUser = Depends(require_permission('read')),
                         db: Session = Depends(get_db)):
    execution = db.scalar(select(Execution).where(Execution.id == execution_id,
        Execution.user_id == actor.user_id, Execution.execution_mode == 'paper'))
    if execution is None:
        raise HTTPException(404, detail='paper execution not found')
    review = db.scalar(select(PostTradeReview).where(PostTradeReview.execution_id == execution.id,
        PostTradeReview.user_id == actor.user_id, PostTradeReview.order_draft_id == execution.order_draft_id))
    journal = db.scalar(select(TradeJournalEntry).where(TradeJournalEntry.id == review.trade_journal_entry_id,
        TradeJournalEntry.user_id == actor.user_id)) if review else None
    if review is None or journal is None:
        raise HTTPException(409, detail='paper review records incomplete')
    return PaperReviewContext(execution=execution, journal_entry=journal, post_trade_review=review)


@router.post("/paper-executions/drafts/{order_draft_id}/execute", response_model=PaperExecutionResponse, status_code=201, dependencies=[Depends(require_permission("trade:submit"))])
def execute_paper_draft(
    order_draft_id: str,
    payload: PaperExecutionRequest,
    db: Session = Depends(get_db),
) -> PaperExecutionResponse:
    draft = db.get(OrderDraft, order_draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="order draft not found")

    service = PaperExecutionService(db)
    try:
        execution, journal_entry, post_trade_review, updated_draft, tax_lots, tax_lot_realizations = service.execute_draft(
            draft,
            approver_id=payload.approver_id,
            decision_reason=payload.decision_reason,
            fill_price=payload.fill_price,
            fill_quantity=payload.fill_quantity,
            fee_bps=payload.fee_bps,
            slippage_bps=payload.slippage_bps,
            idempotency_key=payload.idempotency_key,
        )
    except PaperExecutionConflictError as exc:
        raise HTTPException(status_code=409, detail={'code': 'paper_execution_outcome_unknown', 'message': str(exc)}) from exc
    except PaperExecutionBlockedError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return PaperExecutionResponse(
        replayed=service.replayed,
        execution=execution,
        journal_entry=journal_entry,
        post_trade_review=post_trade_review,
        order_draft=updated_draft,
        tax_lots=tax_lots,
        tax_lot_realizations=tax_lot_realizations,
    )


@router.get("/paper-corporate-actions", response_model=list[PaperCorporateActionRead], dependencies=[Depends(require_permission("read"))])
def list_paper_corporate_actions(
    account_id: str | None = None,
    asset_id: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
) -> list[PaperCorporateAction]:
    query = select(PaperCorporateAction)
    if account_id:
        query = query.where(PaperCorporateAction.account_id == account_id)
    if asset_id:
        query = query.where(PaperCorporateAction.asset_id == asset_id)
    return list(
        db.scalars(query.order_by(PaperCorporateAction.created_at.desc(), PaperCorporateAction.id.desc()).limit(limit)).all()
    )


@router.post("/paper-corporate-actions/cash-dividend", response_model=PaperCorporateActionResponse, status_code=201, dependencies=[Depends(require_permission("proposal:create"))])
def apply_paper_cash_dividend(
    payload: PaperCashDividendRequest,
    db: Session = Depends(get_db),
) -> PaperCorporateActionResponse:
    service = PaperExecutionService(db)
    try:
        corporate_action, journal_entry = service.apply_cash_dividend(
            account_id=payload.account_id,
            asset_id=payload.asset_id,
            amount_per_share=payload.amount_per_share,
            effective_at=payload.effective_at,
            note=payload.note,
        )
    except PaperExecutionBlockedError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return PaperCorporateActionResponse(corporate_action=corporate_action, journal_entry=journal_entry)


@router.post("/paper-corporate-actions/stock-split", response_model=PaperCorporateActionResponse, status_code=201, dependencies=[Depends(require_permission("proposal:create"))])
def apply_paper_stock_split(
    payload: PaperStockSplitRequest,
    db: Session = Depends(get_db),
) -> PaperCorporateActionResponse:
    service = PaperExecutionService(db)
    try:
        corporate_action, journal_entry = service.apply_stock_split(
            account_id=payload.account_id,
            asset_id=payload.asset_id,
            ratio_numerator=payload.ratio_numerator,
            ratio_denominator=payload.ratio_denominator,
            effective_at=payload.effective_at,
            note=payload.note,
        )
    except PaperExecutionBlockedError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return PaperCorporateActionResponse(corporate_action=corporate_action, journal_entry=journal_entry)


@router.get("/paper-tax-lots", response_model=list[PaperTaxLotRead], dependencies=[Depends(require_permission("read"))])
def list_paper_tax_lots(
    account_id: str | None = None,
    asset_id: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
) -> list[PaperTaxLot]:
    query = select(PaperTaxLot)
    if account_id:
        query = query.where(PaperTaxLot.account_id == account_id)
    if asset_id:
        query = query.where(PaperTaxLot.asset_id == asset_id)
    return list(
        db.scalars(query.order_by(PaperTaxLot.opened_at.desc(), PaperTaxLot.id.desc()).limit(limit)).all()
    )


@router.get("/paper-tax-lot-realizations", response_model=list[PaperTaxLotRealizationRead], dependencies=[Depends(require_permission("read"))])
def list_paper_tax_lot_realizations(
    execution_id: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
) -> list[PaperTaxLotRealization]:
    query = select(PaperTaxLotRealization)
    if execution_id:
        query = query.where(PaperTaxLotRealization.execution_id == execution_id)
    return list(
        db.scalars(
            query.order_by(PaperTaxLotRealization.created_at.desc(), PaperTaxLotRealization.id.desc()).limit(limit)
        ).all()
    )


@router.get("/trade-journal-entries", response_model=list[TradeJournalEntryRead], dependencies=[Depends(require_permission("read"))])
def list_trade_journal_entries(limit: int = 100, db: Session = Depends(get_db)) -> list[TradeJournalEntry]:
    return list(
        db.scalars(select(TradeJournalEntry).order_by(TradeJournalEntry.created_at.desc(), TradeJournalEntry.id.desc()).limit(limit)).all()
    )


@router.get("/post-trade-reviews", response_model=list[PostTradeReviewRead], dependencies=[Depends(require_permission("read"))])
def list_post_trade_reviews(limit: int = 100, db: Session = Depends(get_db)) -> list[PostTradeReview]:
    return list(
        db.scalars(select(PostTradeReview).order_by(PostTradeReview.created_at.desc(), PostTradeReview.id.desc()).limit(limit)).all()
    )


@router.patch("/post-trade-reviews/{review_id}", response_model=PostTradeReviewRead, dependencies=[Depends(require_permission("proposal:create"))])
def update_post_trade_review(
    review_id: str,
    payload: PostTradeReviewUpdate,
    db: Session = Depends(get_db),
) -> PostTradeReview:
    review = db.get(PostTradeReview, review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="post trade review not found")
    if payload.status is not None:
        review.status = payload.status
    if payload.review_json is not None:
        review.review_json = payload.review_json
    db.commit()
    db.refresh(review)
    return review


@router.post('/orders/intents/{order_intent_id}/manual-evidence', status_code=201,
             dependencies=[Depends(require_permission('trade:preview'))], response_model=ManualPaperEvidenceRead)
def prepare_manual_paper_evidence(order_intent_id: str, db: Session = Depends(get_db)) -> dict:
    try:
        return prepare_manual_evidence(db, order_intent_id)
    except ManualEvidenceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get('/orders/intents/{order_intent_id}/manual-evidence',
            dependencies=[Depends(require_permission('read'))], response_model=ManualPaperEvidenceRead)
def get_manual_paper_evidence(order_intent_id: str, db: Session = Depends(get_db)) -> dict:
    try:
        return read_manual_evidence(db, order_intent_id)
    except ManualEvidenceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
