from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Signal
from app.schemas import OrderIntentRead
from app.schemas import SignalCreateOrderIntentRequest
from app.schemas import SignalGenerateRequest
from app.schemas import SignalReviewQueueItemRead
from app.schemas import SignalRead
from app.services.signals import SignalEngineService
from app.services.signals import SignalOrderIntentNotAllowedError

router = APIRouter(prefix="/signals", tags=["signals"])


@router.get("", response_model=list[SignalRead])
def list_signals(limit: int = 100, db: Session = Depends(get_db)) -> list[Signal]:
    return list(db.scalars(select(Signal).order_by(Signal.created_at, Signal.id).limit(limit)).all())


@router.post("/generate", response_model=list[SignalRead], status_code=201)
def generate_signals(payload: SignalGenerateRequest, db: Session = Depends(get_db)) -> list[Signal]:
    service = SignalEngineService(db)
    return service.generate(
        asset_id=payload.asset_id,
        candles=[candle.model_dump() for candle in payload.candles],
        signal_types=payload.signal_types,
        horizon=payload.horizon,
        market_facts=payload.market_facts,
        onchain_facts=payload.onchain_facts,
    )


@router.get("/review-queue", response_model=list[SignalReviewQueueItemRead])
def list_signal_review_queue(limit: int = 50, db: Session = Depends(get_db)) -> list[dict]:
    return SignalEngineService(db).list_review_queue(limit=limit)


@router.get("/quality-report")
def signal_quality_report(horizon_candles: int = 5, limit: int = 500, minimum_sample_size: int = 30, db: Session = Depends(get_db)) -> dict:
    """Review-only signal quality: realized forward returns and hit rates from
    stored candles. Signals cannot bypass gates regardless of quality."""
    try:
        return SignalEngineService(db).evaluate_signal_quality(horizon_candles=horizon_candles, limit=limit, minimum_sample_size=minimum_sample_size)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/{signal_id}/create-order-intent", response_model=OrderIntentRead, status_code=201)
def create_order_intent_from_signal(
    signal_id: str,
    payload: SignalCreateOrderIntentRequest,
    db: Session = Depends(get_db),
):
    signal = db.get(Signal, signal_id)
    if signal is None:
        raise HTTPException(status_code=404, detail="signal not found")

    service = SignalEngineService(db)
    try:
        return service.create_order_intent(
            signal=signal,
            account_id=payload.account_id,
            automation_level=payload.automation_level,
            signal_order_intents_enabled=payload.signal_order_intents_enabled,
            quantity=payload.quantity,
            notional=payload.notional,
        )
    except SignalOrderIntentNotAllowedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
