from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from pydantic import BaseModel
from pydantic import Field
from typing import Literal
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas import ReportGenerateRequest
from app.schemas import ResearchReportRead
from app.services.reports import InvalidReportOutputError
from app.services.reports import ReportGenerator
from app.models import ResearchReport
from app.services.research_traceability import ResearchTraceabilityError
from app.services.research_traceability import ResearchTraceabilityService
from app.services.data_catalog import DataTrustGateError
from app.api.production import production_user
from app.core.auth import AuthenticatedUser

router = APIRouter(prefix="/reports", tags=["reports"])


class ResearchThesisReviewRequest(BaseModel):
    thesis_id: str
    decision: Literal["supports", "weakens", "invalidates"]
    human_summary: str = Field(min_length=8, max_length=2000)
    confidence: float = Field(default=0.7, ge=0, le=1)


class ResearchPlanRequest(BaseModel):
    thesis_id: str
    account_id: str
    side: Literal["buy", "sell"]
    order_type: Literal["market", "limit"] = "market"
    quantity: float | None = Field(default=None, gt=0)
    notional: float | None = Field(default=None, gt=0)
    limit_price: float | None = Field(default=None, gt=0)
    user_rationale: str = Field(default="", max_length=4000)
    risk_context: dict = Field(default_factory=dict)


@router.get("", response_model=list[ResearchReportRead])
def list_reports(limit: int = 100, db: Session = Depends(get_db)) -> list[ResearchReport]:
    return list(
        db.scalars(
            select(ResearchReport)
            .order_by(ResearchReport.created_at.desc(), ResearchReport.id.desc())
            .limit(min(max(limit, 1), 500))
        ).all()
    )


@router.post("/generate", response_model=ResearchReportRead, status_code=201)
def generate_report(payload: ReportGenerateRequest, actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)):
    generator = ReportGenerator(db, actor=actor)
    try:
        return generator.generate(
            report_type=payload.report_type,
            data_snapshot_id=payload.data_snapshot_id,
            input_facts=payload.input_facts,
            agent_name=payload.agent_name,
            provider_name=payload.provider,
        )
    except DataTrustGateError as exc:
        raise HTTPException(status_code=409, detail={"code": "data_trust_gate_blocked", **exc.gate}) from exc
    except InvalidReportOutputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc


@router.post("/{report_id}/review-thesis", status_code=201)
def review_report_against_thesis(
    report_id: str,
    payload: ResearchThesisReviewRequest,
    actor: AuthenticatedUser = Depends(production_user),
    db: Session = Depends(get_db),
) -> dict:
    try:
        return ResearchTraceabilityService(db).review_against_thesis(
            report_id=report_id,
            thesis_id=payload.thesis_id,
            user_id=actor.user_id,
            decision=payload.decision,
            human_summary=payload.human_summary,
            confidence=payload.confidence,
        )
    except ResearchTraceabilityError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{report_id}/decision-context")
def get_research_decision_context(
    report_id: str,
    actor: AuthenticatedUser = Depends(production_user),
    db: Session = Depends(get_db),
) -> dict:
    try:
        return ResearchTraceabilityService(db).decision_context(report_id=report_id, user_id=actor.user_id)
    except ResearchTraceabilityError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{report_id}/create-plan-and-evaluate", status_code=201)
def create_research_plan_and_evaluate(
    report_id: str,
    payload: ResearchPlanRequest,
    actor: AuthenticatedUser = Depends(production_user),
    db: Session = Depends(get_db),
) -> dict:
    try:
        return ResearchTraceabilityService(db).create_plan_and_evaluate(
            report_id=report_id,
            thesis_id=payload.thesis_id,
            user_id=actor.user_id,
            account_id=payload.account_id,
            side=payload.side,
            order_type=payload.order_type,
            quantity=payload.quantity,
            notional=payload.notional,
            limit_price=payload.limit_price,
            user_rationale=payload.user_rationale,
            risk_context=payload.risk_context,
        )
    except ResearchTraceabilityError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
