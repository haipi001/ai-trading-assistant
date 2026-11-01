from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import DecisionGate
from app.schemas import DecisionGateEvaluateRequest
from app.schemas import DecisionGateEvaluateResponse
from app.schemas import DecisionGateRead
from app.services.decision_gates import DecisionGateBlockedError
from app.services.decision_gates import DecisionGateService

router = APIRouter(prefix="/decision-gates", tags=["decision-gates"])


@router.post("/evaluate", response_model=DecisionGateEvaluateResponse, status_code=201)
def evaluate_decision_gates(payload: DecisionGateEvaluateRequest, db: Session = Depends(get_db)) -> DecisionGateEvaluateResponse:
    service = DecisionGateService(db)
    try:
        gates = service.evaluate_order(payload.order_intent_id, payload.model_dump())
    except DecisionGateBlockedError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return DecisionGateEvaluateResponse(
        order_intent_id=payload.order_intent_id,
        gates=gates,
        all_passed=all(gate.status == "PASSED" for gate in gates),
    )


@router.get("/order-intent/{order_intent_id}", response_model=list[DecisionGateRead])
def get_order_intent_decision_gates(order_intent_id: str, db: Session = Depends(get_db)) -> list[DecisionGate]:
    service = DecisionGateService(db)
    return service.gate_timeline(order_intent_id)


@router.post("/order-intent/{order_intent_id}/replay")
def replay_order_intent_decision_gates(order_intent_id: str, db: Session = Depends(get_db)) -> dict:
    service = DecisionGateService(db)
    try:
        return service.replay_order(order_intent_id)
    except DecisionGateBlockedError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
