from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.external_financial_data import ExternalFinancialDataError
from app.services.external_financial_data import ExternalFinancialDataService


router = APIRouter(prefix="/external-data", tags=["external-read-only-data"])


@router.get("/auxiliary/status")
def get_auxiliary_data_status(user_id: str = "default-user", db: Session = Depends(get_db)) -> dict:
    return ExternalFinancialDataService(db).auxiliary_data_status(user_id=user_id)


@router.post("/auxiliary/evidence-packet")
def create_auxiliary_data_evidence_packet(payload: dict | None = None, user_id: str = "default-user", db: Session = Depends(get_db)) -> dict:
    resolved_user_id = str((payload or {}).get("user_id") or user_id or "default-user")
    return ExternalFinancialDataService(db).auxiliary_data_evidence_packet(user_id=resolved_user_id)


@router.post("/fx/ecb/sync")
def sync_ecb_fx(payload: dict | None = None, db: Session = Depends(get_db)) -> dict:
    try:
        return ExternalFinancialDataService(db).sync_ecb_fx(currencies=(payload or {}).get("currencies"))
    except ExternalFinancialDataError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/corporate-actions/nasdaq/sync")
def sync_nasdaq_corporate_actions(payload: dict, db: Session = Depends(get_db)) -> dict:
    try:
        return ExternalFinancialDataService(db).sync_nasdaq_dividends(symbols=payload.get("symbols") or [], limit_per_symbol=int(payload.get("limit_per_symbol") or 20))
    except ExternalFinancialDataError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/statements/download")
def download_readonly_statement(payload: dict, db: Session = Depends(get_db)) -> dict:
    try:
        return ExternalFinancialDataService(db).download_statement(
            user_id=str(payload.get("user_id") or "default-user"),
            url=str(payload.get("url") or ""),
            provider=str(payload.get("provider") or "http_statement"),
            account_label=payload.get("account_label"),
            statement_type=str(payload.get("statement_type") or "broker_statement"),
            default_currency=str(payload.get("default_currency") or "USD"),
            credentials_ref=payload.get("credentials_ref"),
        )
    except (ExternalFinancialDataError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/statements/download/preflight")
def preflight_readonly_statement_download(payload: dict, db: Session = Depends(get_db)) -> dict:
    try:
        return ExternalFinancialDataService(db).statement_download_preflight(
            url=str(payload.get("url") or ""),
            credentials_ref=payload.get("credentials_ref"),
            verify_secret=bool(payload.get("verify_secret") or False),
        )
    except (ExternalFinancialDataError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
