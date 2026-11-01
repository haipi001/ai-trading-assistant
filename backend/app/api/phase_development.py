from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.phase_development import PhaseDevelopmentService

router = APIRouter(prefix="/phase-development", tags=["phase-development"])


@router.get("/summary")
def get_phase_development_summary(user_id: str = "default-user", db: Session = Depends(get_db)) -> dict:
    return jsonable_encoder(PhaseDevelopmentService(db).summary(user_id=user_id))


@router.post("/real-readonly-data-proof/binance-private-verify")
def verify_binance_readonly_private(payload: dict | None = None, user_id: str = "default-user", db: Session = Depends(get_db)) -> dict:
    try:
        return jsonable_encoder(
            PhaseDevelopmentService(db).verify_binance_readonly_private(user_id=user_id, evidence_refs=payload or {})
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/real-readonly-data-proof/ibkr-private-verify")
def verify_ibkr_readonly_private(payload: dict | None = None, user_id: str = "default-user", db: Session = Depends(get_db)) -> dict:
    try:
        return jsonable_encoder(
            PhaseDevelopmentService(db).verify_ibkr_readonly_private(user_id=user_id, evidence_refs=payload or {})
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/research-evidence/configure")
def configure_research_evidence(payload: dict, user_id: str = "default-user", db: Session = Depends(get_db)) -> dict:
    try:
        return jsonable_encoder(PhaseDevelopmentService(db).configure_research_evidence(user_id=user_id, payload=payload))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/research-evidence/eval")
def get_research_eval_packet(user_id: str = "default-user", db: Session = Depends(get_db)) -> dict:
    return jsonable_encoder(PhaseDevelopmentService(db).research_eval_packet(user_id=user_id))


@router.get("/research-evidence/eval-history")
def get_research_eval_history(user_id: str = "default-user", db: Session = Depends(get_db)) -> dict:
    return jsonable_encoder(PhaseDevelopmentService(db).research_eval_history(user_id=user_id))


@router.get("/portfolio-risk-terminal/drilldown/{dimension}")
def get_portfolio_risk_drilldown(dimension: str, user_id: str = "default-user", db: Session = Depends(get_db)) -> dict:
    return jsonable_encoder(PhaseDevelopmentService(db).portfolio_risk_drilldown(dimension=dimension, user_id=user_id))


@router.post("/private-beta-foundation/checklist")
def update_private_beta_foundation(payload: dict, user_id: str = "default-user", db: Session = Depends(get_db)) -> dict:
    try:
        return jsonable_encoder(PhaseDevelopmentService(db).update_private_beta_foundation(user_id=user_id, payload=payload))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/traction-loop/configure")
def update_traction_loop(payload: dict, user_id: str = "default-user", db: Session = Depends(get_db)) -> dict:
    try:
        return jsonable_encoder(PhaseDevelopmentService(db).update_traction_loop(user_id=user_id, payload=payload))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/broker-sandbox-proof/state")
def update_broker_sandbox_state(payload: dict, user_id: str = "default-user", db: Session = Depends(get_db)) -> dict:
    try:
        return jsonable_encoder(PhaseDevelopmentService(db).update_broker_sandbox_state(user_id=user_id, payload=payload))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/controlled-pilot/gates")
def update_controlled_pilot_gates(payload: dict, user_id: str = "default-user", db: Session = Depends(get_db)) -> dict:
    try:
        return jsonable_encoder(PhaseDevelopmentService(db).update_controlled_pilot_gates(user_id=user_id, payload=payload))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{phase_key}")
def get_phase_development_phase(phase_key: str, user_id: str = "default-user", db: Session = Depends(get_db)) -> dict:
    try:
        return jsonable_encoder(PhaseDevelopmentService(db).phase(phase_key=phase_key, user_id=user_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
