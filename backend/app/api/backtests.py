from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas import BacktestRunCreate
from app.schemas import BacktestRunRead
from app.services.backtests import BacktestRunError
from app.services.backtests import BacktestRunNotFoundError
from app.services.backtests import BacktestRunsService

router = APIRouter(prefix="/backtest-runs", tags=["backtest-runs"])


@router.get("", response_model=list[BacktestRunRead])
def list_backtest_runs(limit: int = 100, db: Session = Depends(get_db)):
    return BacktestRunsService(db).list_runs(limit=limit)


@router.post("", response_model=BacktestRunRead, status_code=201)
def create_backtest_run(payload: BacktestRunCreate, db: Session = Depends(get_db)):
    try:
        return BacktestRunsService(db).create_run(payload.model_dump())
    except BacktestRunError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{run_id}", response_model=BacktestRunRead)
def get_backtest_run(run_id: str, db: Session = Depends(get_db)):
    try:
        return BacktestRunsService(db).get_run(run_id)
    except BacktestRunNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{run_id}/start", response_model=BacktestRunRead)
def start_backtest_run(run_id: str, db: Session = Depends(get_db)):
    try:
        return BacktestRunsService(db).start_run(run_id)
    except BacktestRunNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{run_id}/promotion-preflight")
def check_backtest_promotion_preflight(run_id: str, db: Session = Depends(get_db)):
    try:
        return BacktestRunsService(db).promotion_preflight(run_id)
    except BacktestRunNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{run_id}/research-packet")
def create_backtest_research_packet(run_id: str, db: Session = Depends(get_db)):
    try:
        return BacktestRunsService(db).research_packet(run_id)
    except BacktestRunNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
