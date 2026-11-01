from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import BehaviorIntervention
from app.models import BehaviorPattern
from app.schemas import BehaviorEvaluateOrderRequest
from app.schemas import BehaviorEvaluateOrderResponse
from app.schemas import BehaviorInterventionDetailRead
from app.schemas import BehaviorInterventionRead
from app.schemas import BehaviorInterventionRespondRequest
from app.schemas import BehaviorPatternRead
from app.schemas import BehaviorProfileRead
from app.services.behavior import BehaviorEngine
from app.services.behavior import BehaviorEvaluationError
from app.services.behavior import InterventionNotFoundError

router = APIRouter(prefix="/behavior", tags=["behavior"])


@router.post("/evaluate-order", response_model=BehaviorEvaluateOrderResponse, status_code=201)
def evaluate_order_behavior(payload: BehaviorEvaluateOrderRequest, db: Session = Depends(get_db)) -> BehaviorEvaluateOrderResponse:
    service = BehaviorEngine(db)
    try:
        result = service.evaluate_order(payload.order_intent_id, payload.model_dump())
    except BehaviorEvaluationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return BehaviorEvaluateOrderResponse(
        order_intent_id=result.order_intent_id,
        level=result.level,
        message=result.message,
        evidence=result.evidence,
        required_user_action=result.required_user_action,
        bypass_allowed=result.bypass_allowed,
        intervention=result.intervention,
        patterns=result.patterns,
        thesis_violation=result.thesis_violation,
    )


@router.get("/patterns", response_model=list[BehaviorPatternRead])
def list_behavior_patterns(limit: int = 100, db: Session = Depends(get_db)) -> list[BehaviorPattern]:
    return BehaviorEngine(db).list_patterns(limit=limit)


@router.get("/interventions", response_model=list[BehaviorInterventionDetailRead])
def list_behavior_interventions(limit: int = 100, db: Session = Depends(get_db)) -> list[dict]:
    service = BehaviorEngine(db)
    interventions = service.list_interventions(limit=limit)
    return [intervention_detail(intervention, db) for intervention in interventions]


@router.get("/profile/{user_id}", response_model=BehaviorProfileRead)
def get_behavior_profile(user_id: str, db: Session = Depends(get_db)) -> dict:
    return BehaviorEngine(db).build_profile(user_id)


@router.post("/interventions/{intervention_id}/respond", response_model=BehaviorInterventionRead)
def respond_to_behavior_intervention(
    intervention_id: str,
    payload: BehaviorInterventionRespondRequest,
    db: Session = Depends(get_db),
) -> BehaviorIntervention:
    service = BehaviorEngine(db)
    try:
        return service.respond_to_intervention(
            intervention_id,
            user_response=payload.user_response,
            bypassed=payload.bypassed,
        )
    except InterventionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BehaviorEvaluationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def intervention_detail(intervention: BehaviorIntervention, db: Session) -> dict:
    pattern = db.get(BehaviorPattern, intervention.pattern_id) if intervention.pattern_id else None
    level = intervention.intervention_level
    return {
        "id": intervention.id,
        "user_id": intervention.user_id,
        "pattern_id": intervention.pattern_id,
        "order_intent_id": intervention.order_intent_id,
        "intervention_level": level,
        "message": intervention.message,
        "user_response": intervention.user_response,
        "bypassed": intervention.bypassed,
        "created_at": intervention.created_at,
        "evidence": pattern.evidence_json if pattern else {},
        "required_user_action": required_user_action(level),
        "bypass_allowed": level != "BLOCK",
    }


def required_user_action(level: str) -> str:
    if level == "BLOCK":
        return "Revise or cancel the order; this intervention cannot be bypassed."
    if level == "HARD_CONFIRM":
        return "Write a specific confirmation explaining the changed facts before proceeding."
    if level == "SOFT_WARNING":
        return "Acknowledge the warning before proceeding."
    return "No user action required."
