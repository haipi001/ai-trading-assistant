from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import ScheduledJob
from app.schemas.core import ScheduledJobCreate
from app.schemas.core import ScheduledJobRead
from app.schemas.core import ScheduledJobRunResponse
from app.services.scheduled_jobs import ScheduledJobError
from app.services.scheduled_jobs import ScheduledJobService

router = APIRouter(prefix="/scheduled-jobs", tags=["scheduled-jobs"])


@router.get("", response_model=list[ScheduledJobRead])
def list_scheduled_jobs(
    job_type: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
) -> list[ScheduledJob]:
    return ScheduledJobService(db).list_jobs(job_type=job_type, limit=limit)


@router.post("", response_model=ScheduledJobRead, status_code=201)
def create_scheduled_job(payload: ScheduledJobCreate, db: Session = Depends(get_db)) -> ScheduledJob:
    try:
        return ScheduledJobService(db).create_job(**payload.model_dump())
    except ScheduledJobError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/{job_id}/run", response_model=ScheduledJobRunResponse)
def run_scheduled_job(job_id: str, db: Session = Depends(get_db)) -> ScheduledJobRunResponse:
    try:
        job, result = ScheduledJobService(db).run_job(job_id)
    except ScheduledJobError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ScheduledJobRunResponse(job=job, result=result, execution_available=False)
