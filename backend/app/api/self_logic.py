from typing import Any

from fastapi import APIRouter
from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import AuditLog
from app.models import AutomationPolicy
from app.models import BehaviorIntervention
from app.models import BehaviorPattern
from app.models import DecisionGate
from app.models import InvestmentConstitution
from app.models import InvestmentThesis
from app.models import MonthlyDecisionReview
from app.models import RiskBudget
from app.models import StrategyPlaybook
from app.models import ThesisCheckpoint
from app.models import ThesisViolation
from app.models import WorkflowState
from app.schemas import AutomationPolicyCreate
from app.schemas import AutomationPolicyRead
from app.schemas import BehaviorInterventionCreate
from app.schemas import BehaviorInterventionRead
from app.schemas import BehaviorPatternCreate
from app.schemas import BehaviorPatternRead
from app.schemas import DecisionGateCreate
from app.schemas import DecisionGateRead
from app.schemas import InvestmentConstitutionCreate
from app.schemas import InvestmentConstitutionRead
from app.schemas import InvestmentThesisCreate
from app.schemas import InvestmentThesisRead
from app.schemas import MonthlyDecisionReviewCreate
from app.schemas import MonthlyDecisionReviewRead
from app.schemas import RiskBudgetCreate
from app.schemas import RiskBudgetRead
from app.schemas import StrategyPlaybookCreate
from app.schemas import StrategyPlaybookRead
from app.schemas import ThesisCheckpointCreate
from app.schemas import ThesisCheckpointRead
from app.schemas import ThesisViolationCreate
from app.schemas import ThesisViolationRead
from app.schemas import WorkflowStateCreate
from app.schemas import WorkflowStateRead

router = APIRouter(tags=["self-logic"])


def write_audit_log(db: Session, *, action: str, entity_type: str, entity_id: str, payload_json: dict[str, Any]) -> AuditLog:
    audit_log = AuditLog(
        actor_type="system",
        actor_id="self-logic-crud-api",
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        payload_json=payload_json,
    )
    db.add(audit_log)
    return audit_log


def list_records(db: Session, model: type, limit: int) -> list:
    return list(db.scalars(select(model).order_by(model.id).limit(limit)).all())


def create_record(db: Session, model: type, payload, *, action: str, entity_type: str):
    record = model(**payload.model_dump())
    db.add(record)
    db.flush()
    write_audit_log(db, action=action, entity_type=entity_type, entity_id=record.id, payload_json=payload.model_dump(mode="json"))
    db.commit()
    db.refresh(record)
    return record


@router.get("/investment-constitutions", response_model=list[InvestmentConstitutionRead])
def list_investment_constitutions(limit: int = 100, db: Session = Depends(get_db)) -> list[InvestmentConstitution]:
    return list_records(db, InvestmentConstitution, limit)


@router.post("/investment-constitutions", response_model=InvestmentConstitutionRead, status_code=201)
def create_investment_constitution(
    payload: InvestmentConstitutionCreate,
    db: Session = Depends(get_db),
) -> InvestmentConstitution:
    return create_record(db, InvestmentConstitution, payload, action="investment_constitution.created", entity_type="InvestmentConstitution")


@router.get("/risk-budgets", response_model=list[RiskBudgetRead])
def list_risk_budgets(limit: int = 100, db: Session = Depends(get_db)) -> list[RiskBudget]:
    return list_records(db, RiskBudget, limit)


@router.post("/risk-budgets", response_model=RiskBudgetRead, status_code=201)
def create_risk_budget(payload: RiskBudgetCreate, db: Session = Depends(get_db)) -> RiskBudget:
    return create_record(db, RiskBudget, payload, action="risk_budget.created", entity_type="RiskBudget")


@router.get("/strategy-playbooks", response_model=list[StrategyPlaybookRead])
def list_strategy_playbooks(limit: int = 100, db: Session = Depends(get_db)) -> list[StrategyPlaybook]:
    return list_records(db, StrategyPlaybook, limit)


@router.post("/strategy-playbooks", response_model=StrategyPlaybookRead, status_code=201)
def create_strategy_playbook(payload: StrategyPlaybookCreate, db: Session = Depends(get_db)) -> StrategyPlaybook:
    return create_record(db, StrategyPlaybook, payload, action="strategy_playbook.created", entity_type="StrategyPlaybook")


@router.get("/investment-theses", response_model=list[InvestmentThesisRead])
def list_investment_theses(limit: int = 100, db: Session = Depends(get_db)) -> list[InvestmentThesis]:
    return list_records(db, InvestmentThesis, limit)


@router.post("/investment-theses", response_model=InvestmentThesisRead, status_code=201)
def create_investment_thesis(payload: InvestmentThesisCreate, db: Session = Depends(get_db)) -> InvestmentThesis:
    return create_record(db, InvestmentThesis, payload, action="investment_thesis.created", entity_type="InvestmentThesis")


@router.get("/thesis-checkpoints", response_model=list[ThesisCheckpointRead])
def list_thesis_checkpoints(limit: int = 100, db: Session = Depends(get_db)) -> list[ThesisCheckpoint]:
    return list_records(db, ThesisCheckpoint, limit)


@router.post("/thesis-checkpoints", response_model=ThesisCheckpointRead, status_code=201)
def create_thesis_checkpoint(payload: ThesisCheckpointCreate, db: Session = Depends(get_db)) -> ThesisCheckpoint:
    return create_record(db, ThesisCheckpoint, payload, action="thesis_checkpoint.created", entity_type="ThesisCheckpoint")


@router.get("/thesis-violations", response_model=list[ThesisViolationRead])
def list_thesis_violations(limit: int = 100, db: Session = Depends(get_db)) -> list[ThesisViolation]:
    return list_records(db, ThesisViolation, limit)


@router.post("/thesis-violations", response_model=ThesisViolationRead, status_code=201)
def create_thesis_violation(payload: ThesisViolationCreate, db: Session = Depends(get_db)) -> ThesisViolation:
    return create_record(db, ThesisViolation, payload, action="thesis_violation.created", entity_type="ThesisViolation")


@router.get("/decision-gates", response_model=list[DecisionGateRead])
def list_decision_gates(limit: int = 100, db: Session = Depends(get_db)) -> list[DecisionGate]:
    return list_records(db, DecisionGate, limit)


@router.post("/decision-gates", response_model=DecisionGateRead, status_code=201)
def create_decision_gate(payload: DecisionGateCreate, db: Session = Depends(get_db)) -> DecisionGate:
    return create_record(db, DecisionGate, payload, action="decision_gate.created", entity_type="DecisionGate")


@router.get("/automation-policies", response_model=list[AutomationPolicyRead])
def list_automation_policies(limit: int = 100, db: Session = Depends(get_db)) -> list[AutomationPolicy]:
    return list_records(db, AutomationPolicy, limit)


@router.post("/automation-policies", response_model=AutomationPolicyRead, status_code=201)
def create_automation_policy(payload: AutomationPolicyCreate, db: Session = Depends(get_db)) -> AutomationPolicy:
    return create_record(db, AutomationPolicy, payload, action="automation_policy.created", entity_type="AutomationPolicy")


@router.get("/behavior-patterns", response_model=list[BehaviorPatternRead])
def list_behavior_patterns(limit: int = 100, db: Session = Depends(get_db)) -> list[BehaviorPattern]:
    return list_records(db, BehaviorPattern, limit)


@router.post("/behavior-patterns", response_model=BehaviorPatternRead, status_code=201)
def create_behavior_pattern(payload: BehaviorPatternCreate, db: Session = Depends(get_db)) -> BehaviorPattern:
    return create_record(db, BehaviorPattern, payload, action="behavior_pattern.created", entity_type="BehaviorPattern")


@router.get("/behavior-interventions", response_model=list[BehaviorInterventionRead])
def list_behavior_interventions(limit: int = 100, db: Session = Depends(get_db)) -> list[BehaviorIntervention]:
    return list_records(db, BehaviorIntervention, limit)


@router.post("/behavior-interventions", response_model=BehaviorInterventionRead, status_code=201)
def create_behavior_intervention(payload: BehaviorInterventionCreate, db: Session = Depends(get_db)) -> BehaviorIntervention:
    return create_record(db, BehaviorIntervention, payload, action="behavior_intervention.created", entity_type="BehaviorIntervention")


@router.get("/workflow-states", response_model=list[WorkflowStateRead])
def list_workflow_states(limit: int = 100, db: Session = Depends(get_db)) -> list[WorkflowState]:
    return list_records(db, WorkflowState, limit)


@router.post("/workflow-states", response_model=WorkflowStateRead, status_code=201)
def create_workflow_state(payload: WorkflowStateCreate, db: Session = Depends(get_db)) -> WorkflowState:
    return create_record(db, WorkflowState, payload, action="workflow_state.created", entity_type="WorkflowState")


@router.get("/monthly-decision-reviews", response_model=list[MonthlyDecisionReviewRead])
def list_monthly_decision_reviews(limit: int = 100, db: Session = Depends(get_db)) -> list[MonthlyDecisionReview]:
    return list_records(db, MonthlyDecisionReview, limit)


@router.post("/monthly-decision-reviews", response_model=MonthlyDecisionReviewRead, status_code=201)
def create_monthly_decision_review(
    payload: MonthlyDecisionReviewCreate,
    db: Session = Depends(get_db),
) -> MonthlyDecisionReview:
    return create_record(db, MonthlyDecisionReview, payload, action="monthly_decision_review.created", entity_type="MonthlyDecisionReview")
