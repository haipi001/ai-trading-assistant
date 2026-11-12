from fastapi import APIRouter, Query, Response
from app.core.auth import AuthenticatedUser, require_permission
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
def list_backtest_runs(response: Response, limit: int = Query(default=100,ge=1,le=100), actor: AuthenticatedUser = Depends(require_permission('read')), db: Session = Depends(get_db)):
    response.headers['Cache-Control']='no-store'
    return BacktestRunsService(db).list_runs(limit=limit,user_id=actor.user_id)


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
def create_backtest_research_packet(run_id: str, response: Response, actor: AuthenticatedUser = Depends(require_permission('readiness:write')), db: Session = Depends(get_db)):
    try:
        service=BacktestRunsService(db)
        if service.get_run(run_id).user_id!=actor.user_id:
            raise BacktestRunNotFoundError('backtest run not found')
        response.headers['Cache-Control']='no-store'
        return service.research_packet(run_id)
    except BacktestRunNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post('/{run_id}/research-material', status_code=201)
def prepare_saved_backtest_material(run_id: str, response: Response, actor: AuthenticatedUser = Depends(require_permission('readiness:write')), db: Session = Depends(get_db)):
    from app.services.backtest_research_material import prepare_backtest_material
    response.headers['Cache-Control']='no-store'
    try:return prepare_backtest_material(db,actor.user_id,run_id)
    except BacktestRunNotFoundError as exc:raise HTTPException(404,'backtest run not found') from exc


@router.get('/{run_id}/research-material/{snapshot_id}')
def get_saved_backtest_material(run_id: str, snapshot_id: str, response: Response, actor: AuthenticatedUser = Depends(require_permission('read')), db: Session = Depends(get_db)):
    from app.services.backtest_research_material import read_backtest_material
    response.headers['Cache-Control']='no-store'
    return read_backtest_material(db,actor.user_id,run_id,snapshot_id)


@router.get('/{run_id}/research-material')
def list_saved_backtest_material(run_id: str, response: Response, actor: AuthenticatedUser = Depends(require_permission('read')), db: Session = Depends(get_db)):
    from app.services.backtest_research_material import list_backtest_material
    response.headers['Cache-Control']='no-store'
    try:return list_backtest_material(db,actor.user_id,run_id)
    except BacktestRunNotFoundError as exc:raise HTTPException(404,'backtest run not found') from exc
