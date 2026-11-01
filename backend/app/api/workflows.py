from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import WorkflowState
from app.models import WorkflowReviewTask
from app.schemas import WorkflowBlockRequest
from app.schemas import WorkflowCreateRequest
from app.schemas import WorkflowDeepReviewQueueRead
from app.schemas import OrderClosureReportRead
from app.schemas import WorkflowReviewTaskCreate
from app.schemas import WorkflowReviewTaskRead
from app.schemas import WorkflowStateRead
from app.schemas import WorkflowTransitionRequest
from app.schemas import StageReadinessQueueRead
from app.services.order_closure import OrderClosureService
from app.services.stage_readiness import StageReadinessService
from app.services.workflow_review import WorkflowDeepReviewService
from app.services.workflows import WorkflowEngine
from app.services.workflows import WorkflowTransitionError

router = APIRouter(tags=["workflows"])


@router.get("/workflows/deep-review-queue", response_model=WorkflowDeepReviewQueueRead)
def get_deep_review_queue(
    user_id: str = "default-user",
    limit: int = 25,
    db: Session = Depends(get_db),
) -> dict:
    return WorkflowDeepReviewService(db).queue(user_id=user_id, limit=limit)


@router.get("/workflows/stage-5-11-readiness", response_model=StageReadinessQueueRead)
def get_stage_5_11_readiness(
    user_id: str = "default-user",
    limit: int = 25,
    db: Session = Depends(get_db),
) -> dict:
    return StageReadinessService(db).queue(user_id=user_id, limit=limit)


@router.get("/workflows/order-closure-report", response_model=OrderClosureReportRead)
def get_order_closure_report(
    user_id: str = "default-user",
    limit: int = 25,
    db: Session = Depends(get_db),
) -> dict:
    return OrderClosureService(db).report(user_id=user_id, limit=limit)


@router.get("/workflows/review-quality-report")
def get_review_quality_report(
    user_id: str = "default-user",
    limit: int = 25,
    db: Session = Depends(get_db),
) -> dict:
    return OrderClosureService(db).quality_report(user_id=user_id, limit=limit)


@router.get("/workflows/review-action-plan")
def get_review_action_plan(
    user_id: str = "default-user",
    limit: int = 25,
    db: Session = Depends(get_db),
) -> dict:
    return OrderClosureService(db).review_action_plan(user_id=user_id, limit=limit)


@router.get("/workflows/deep-review-tasks", response_model=list[WorkflowReviewTaskRead])
def list_deep_review_tasks(
    user_id: str = "default-user",
    status: str | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
) -> list[WorkflowReviewTask]:
    return WorkflowDeepReviewService(db).list_tasks(user_id=user_id, status=status, limit=limit)


@router.post("/workflows/deep-review-tasks", response_model=WorkflowReviewTaskRead, status_code=201)
def assign_deep_review_task(payload: WorkflowReviewTaskCreate, db: Session = Depends(get_db)) -> WorkflowReviewTask:
    try:
        return WorkflowDeepReviewService(db).assign_task(**payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/workflows/deep-review-tasks/{task_id}/complete", response_model=WorkflowReviewTaskRead, status_code=201)
def complete_deep_review_task(
    task_id: str,
    user_id: str = "default-user",
    db: Session = Depends(get_db),
) -> WorkflowReviewTask:
    try:
        return WorkflowDeepReviewService(db).complete_task(task_id=task_id, user_id=user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/workflows", response_model=WorkflowStateRead, status_code=201)
def create_workflow(payload: WorkflowCreateRequest, db: Session = Depends(get_db)) -> WorkflowState:
    service = WorkflowEngine(db)
    return service.create_workflow(payload.entity_type, payload.entity_id, payload.metadata)


@router.get("/workflows/{workflow_id}", response_model=WorkflowStateRead)
def get_workflow(workflow_id: str, db: Session = Depends(get_db)) -> WorkflowState:
    service = WorkflowEngine(db)
    try:
        return service.get_workflow(workflow_id)
    except WorkflowTransitionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/workflows/entity/{entity_type}/{entity_id}", response_model=list[WorkflowStateRead])
def get_workflow_timeline(entity_type: str, entity_id: str, db: Session = Depends(get_db)) -> list[WorkflowState]:
    service = WorkflowEngine(db)
    return service.get_workflow_timeline(entity_id, entity_type)


@router.post("/workflows/{workflow_id}/transition", response_model=WorkflowStateRead, status_code=201)
def transition_workflow(
    workflow_id: str,
    payload: WorkflowTransitionRequest,
    db: Session = Depends(get_db),
) -> WorkflowState:
    service = WorkflowEngine(db)
    try:
        return service.transition(workflow_id, payload.next_state, payload.reason, payload.metadata)
    except WorkflowTransitionError as exc:
        status_code = 404 if str(exc) == "workflow not found" else 422
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.post("/workflows/{workflow_id}/block", response_model=WorkflowStateRead, status_code=201)
def block_workflow(workflow_id: str, payload: WorkflowBlockRequest, db: Session = Depends(get_db)) -> WorkflowState:
    service = WorkflowEngine(db)
    try:
        return service.block_workflow(workflow_id, payload.reason, payload.metadata)
    except WorkflowTransitionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
