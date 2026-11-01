from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas import CommandQueryRead
from app.schemas import CommandRunRequest
from app.schemas import CommandRunResponse
from app.services.command_bar import CommandBarError
from app.services.command_bar import CommandBarService
from app.services.command_bar import CommandOrderIntentPolicyError

router = APIRouter(prefix="/command-bar", tags=["command-bar"])


@router.post("/query", response_model=CommandRunResponse, status_code=201)
def run_command(payload: CommandRunRequest, db: Session = Depends(get_db)):
    service = CommandBarService(db)
    try:
        result = service.run(
            user_id=payload.user_id,
            raw_query=payload.raw_query,
            data_snapshot_id=payload.data_snapshot_id,
            context=payload.context,
            allow_order_intent=payload.allow_order_intent,
            account_id=payload.account_id,
            asset_id=payload.asset_id,
            strategy_playbook_id=payload.strategy_playbook_id,
            side=payload.side,
            quantity=payload.quantity,
            notional=payload.notional,
            user_rationale=payload.user_rationale,
        )
        return {
            "query": result.query,
            "tool_calls": result.tool_calls,
            "result": result.result,
            "order_intent": result.order_intent,
        }
    except CommandOrderIntentPolicyError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except CommandBarError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/queries", response_model=list[CommandQueryRead])
def list_command_queries(limit: int = 100, db: Session = Depends(get_db)):
    return CommandBarService(db).list_queries(limit=limit)


@router.get("/queries/{command_query_id}", response_model=CommandRunResponse)
def get_command_query(command_query_id: str, db: Session = Depends(get_db)):
    try:
        result = CommandBarService(db).get_query(command_query_id)
        return {
            "query": result.query,
            "tool_calls": result.tool_calls,
            "result": result.result,
            "order_intent": result.order_intent,
        }
    except CommandBarError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
