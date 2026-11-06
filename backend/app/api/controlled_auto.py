from app.core.auth import require_permission
from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas import ControlledAutoEvaluateRequest
from app.schemas import ControlledAutoEvaluationResponse
from app.schemas import ControlledAutoExecuteResponse
from app.services.controlled_auto import ControlledAutoError
from app.services.controlled_auto import ControlledAutoNotFoundError
from app.services.controlled_auto import ControlledAutoService

router = APIRouter(prefix="/controlled-auto", tags=["controlled-auto"])


@router.post("/evaluate/{kind}", response_model=ControlledAutoEvaluationResponse, dependencies=[Depends(require_permission("trade:preview"))])
def evaluate_controlled_auto(kind: str, payload: ControlledAutoEvaluateRequest, db: Session = Depends(get_db)):
    try:
        return ControlledAutoService(db).evaluate(kind, payload.model_dump())
    except ControlledAutoNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ControlledAutoError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/execute/{kind}", response_model=ControlledAutoExecuteResponse, dependencies=[Depends(require_permission("trade:submit"))])
def execute_controlled_auto(kind: str, payload: ControlledAutoEvaluateRequest, db: Session = Depends(get_db)):
    try:
        return ControlledAutoService(db).execute(kind, payload.model_dump())
    except ControlledAutoNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ControlledAutoError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
