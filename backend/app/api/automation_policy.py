from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas import AutomationPolicyEffectiveRead
from app.schemas import AutomationPolicyEffectiveRequest
from app.schemas import AutomationPolicyEvaluateRequest
from app.schemas import AutomationPolicyEvaluateResponse
from app.services.automation_policy import AutomationPolicyEngine
from app.services.automation_policy import AutomationPolicyNotImplementedError

router = APIRouter(prefix="/automation-policy", tags=["automation-policy"])


@router.post("/effective", response_model=AutomationPolicyEffectiveRead)
def get_effective_policy(payload: AutomationPolicyEffectiveRequest, db: Session = Depends(get_db)) -> AutomationPolicyEffectiveRead:
    engine = AutomationPolicyEngine(db)
    try:
        return engine.get_effective_policy(
            user_id=payload.user_id,
            account_id=payload.account_id,
            asset_id=payload.asset_id,
            strategy_playbook_id=payload.strategy_playbook_id,
        )
    except AutomationPolicyNotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc


@router.post("/evaluate", response_model=AutomationPolicyEvaluateResponse)
def evaluate_policy(payload: AutomationPolicyEvaluateRequest, db: Session = Depends(get_db)) -> AutomationPolicyEvaluateResponse:
    engine = AutomationPolicyEngine(db)
    try:
        return engine.evaluate(
            user_id=payload.user_id,
            account_id=payload.account_id,
            asset_id=payload.asset_id,
            strategy_playbook_id=payload.strategy_playbook_id,
            action=payload.action,
            order_notional=payload.order_notional,
            gates_passed=payload.gates_passed,
            risk_budget_passed=payload.risk_budget_passed,
            human_approved=payload.human_approved,
            live_trading_enabled=payload.live_trading_enabled,
        )
    except AutomationPolicyNotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
