from fastapi import APIRouter
from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas import DemoSeedResponse
from app.schemas import DemoStepStatusRead
from app.schemas import DemoStatusRead
from app.services.demo_seed import DemoStatusPayload
from app.services.demo_seed import DemoSeedService

router = APIRouter(prefix="/demo", tags=["demo"])


@router.post("/seed", response_model=DemoSeedResponse, status_code=201)
def seed_demo(db: Session = Depends(get_db)) -> DemoSeedResponse:
    status = DemoSeedService(db).seed()
    return DemoSeedResponse(status=_serialize_status(status))


@router.get("/status", response_model=DemoStatusRead)
def demo_status(db: Session = Depends(get_db)) -> DemoStatusRead:
    return _serialize_status(DemoSeedService(db).build_status())


def _serialize_status(status: DemoStatusPayload) -> DemoStatusRead:
    return DemoStatusRead(
        seeded=status.seeded,
        last_data_update_at=status.last_data_update_at,
        data_quality_status=status.data_quality_status,
        global_risk_status=status.global_risk_status,
        automation_level=status.automation_level,
        current_workflow_stage=status.current_workflow_stage,
        next_workflow_stage=status.next_workflow_stage,
        counts=status.counts,
        steps=[
            DemoStepStatusRead(
                key=step.key,
                module=step.module,
                label=step.label,
                status=step.status,
                detail=step.detail,
                action_label=step.action_label,
                action_detail=step.action_detail,
                blockers=step.blockers,
            )
            for step in status.steps
        ],
    )
