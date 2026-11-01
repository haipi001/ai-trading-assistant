from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas import AgentResearchRequest
from app.schemas import AgentResearchResponse
from app.services.research_committee import InvalidAgentOutputError
from app.services.research_committee import ResearchCommitteeService
from app.services.data_catalog import DataTrustGateError

router = APIRouter(prefix="/agents", tags=["agents"])


@router.post("/run-research", response_model=AgentResearchResponse, status_code=201)
def run_research(payload: AgentResearchRequest, db: Session = Depends(get_db)):
    service = ResearchCommitteeService(db)
    input_facts = {
        "asset_id": payload.asset_id,
        "portfolio_snapshot_id": payload.portfolio_snapshot_id,
        "market_facts": payload.market_facts,
        "positions": payload.positions,
        "signals": payload.signals,
        "prior_reports": payload.prior_reports,
    }
    try:
        result = service.run(
            data_snapshot_id=payload.data_snapshot_id,
            input_facts=input_facts,
            automation_level=payload.automation_level,
        )
    except DataTrustGateError as exc:
        raise HTTPException(status_code=409, detail={"code": "data_trust_gate_blocked", **exc.gate}) from exc
    except InvalidAgentOutputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {
        "final_report": result.report,
        "agent_runs": result.agent_runs,
        "order_intent_id": result.order_intent_id,
    }
