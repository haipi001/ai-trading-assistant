from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas import ModuleGateComplianceRead
from app.schemas import ModuleHealthStatusRead
from app.schemas import ModuleInfoRead
from app.schemas import SidecarPolicyEvaluateRequest
from app.schemas import SidecarPolicyEvaluateResponse
from app.services.modules import ModuleNotFoundError
from app.services.modules import ModulesService

router = APIRouter(prefix="/modules", tags=["modules"])


@router.get("", response_model=list[ModuleInfoRead])
def list_modules():
    return ModulesService().list_modules()


@router.post("/sidecar-policy/evaluate", response_model=SidecarPolicyEvaluateResponse)
def evaluate_sidecar_policy(payload: SidecarPolicyEvaluateRequest, db: Session = Depends(get_db)):
    return ModulesService(db).evaluate_sidecar_policy(payload.model_dump())


@router.post("/sidecar-contract/report")
def sidecar_contract_report(payload: dict, db: Session = Depends(get_db)):
    return ModulesService(db).sidecar_contract_report(payload)


@router.get("/{module_type}/health", response_model=ModuleHealthStatusRead)
def module_health(module_type: str):
    try:
        return ModulesService().health(module_type)
    except ModuleNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{module_type}/gate-compliance", response_model=ModuleGateComplianceRead)
def module_gate_compliance(module_type: str):
    try:
        return ModulesService().gate_compliance(module_type)
    except ModuleNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
