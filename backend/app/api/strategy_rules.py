from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from fastapi import Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas import StrategyRuleCreate
from app.schemas import StrategyRuleRead
from app.schemas import StrategyRuleUpdate
from app.services.strategy_rules import StrategyRuleError
from app.services.strategy_rules import StrategyRuleNotFoundError
from app.services.strategy_rules import StrategyRulesService

router = APIRouter(prefix="/strategy-rules", tags=["strategy-rules"])


@router.get("", response_model=list[StrategyRuleRead])
def list_strategy_rules(
    strategy_playbook_id: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    return StrategyRulesService(db).list_rules(strategy_playbook_id=strategy_playbook_id, limit=limit)


@router.post("", response_model=StrategyRuleRead, status_code=201)
def create_strategy_rule(payload: StrategyRuleCreate, db: Session = Depends(get_db)):
    try:
        return StrategyRulesService(db).create_rule(payload.model_dump())
    except StrategyRuleError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.patch("/{rule_id}", response_model=StrategyRuleRead)
def update_strategy_rule(rule_id: str, payload: StrategyRuleUpdate, db: Session = Depends(get_db)):
    try:
        return StrategyRulesService(db).update_rule(rule_id, payload.model_dump(exclude_unset=True))
    except StrategyRuleNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{rule_id}", status_code=204)
def delete_strategy_rule(rule_id: str, db: Session = Depends(get_db)) -> Response:
    try:
        StrategyRulesService(db).disable_rule(rule_id)
    except StrategyRuleNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=204)
