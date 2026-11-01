from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import InvestmentLedgerEntry
from app.models import StatementImportBatch
from app.schemas import InvestmentLedgerEntryRead
from app.schemas import LedgerReconciliationReportRead
from app.schemas import LedgerPreflightRead
from app.schemas import LedgerSyncResponse
from app.schemas import StatementImportBatchRead
from app.schemas import StatementImportRequest
from app.schemas import StatementImportResponse
from app.services.ledger import LedgerImportError
from app.services.ledger import InvestmentLedgerService

router = APIRouter(prefix="/ledger", tags=["investment-ledger"])


@router.get("/entries", response_model=list[InvestmentLedgerEntryRead])
def list_ledger_entries(
    user_id: str = "default-user",
    limit: int = 100,
    db: Session = Depends(get_db),
) -> list[InvestmentLedgerEntry]:
    return InvestmentLedgerService(db).list_entries(user_id=user_id, limit=limit)


@router.get("/statement-imports", response_model=list[StatementImportBatchRead])
def list_statement_imports(
    user_id: str = "default-user",
    limit: int = 50,
    db: Session = Depends(get_db),
) -> list[StatementImportBatch]:
    return InvestmentLedgerService(db).list_statement_imports(user_id=user_id, limit=limit)


@router.post("/statement-imports", response_model=StatementImportResponse, status_code=201)
def import_statement(payload: StatementImportRequest, db: Session = Depends(get_db)) -> dict:
    try:
        return InvestmentLedgerService(db).import_statement(**payload.model_dump())
    except LedgerImportError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/preflight", response_model=LedgerPreflightRead)
def get_ledger_preflight(user_id: str = "default-user", db: Session = Depends(get_db)) -> dict:
    return InvestmentLedgerService(db).preflight(user_id=user_id)


@router.get("/reconciliation-policy")
def get_ledger_reconciliation_policy(user_id: str = "default-user", db: Session = Depends(get_db)) -> dict:
    return InvestmentLedgerService(db).reconciliation_policy(user_id=user_id)


@router.get("/reconciliation-workbench")
def get_ledger_reconciliation_workbench(user_id: str = "default-user", db: Session = Depends(get_db)) -> dict:
    return InvestmentLedgerService(db).reconciliation_workbench(user_id=user_id)


@router.get("/statement-normalization-report")
def get_statement_normalization_report(user_id: str = "default-user", db: Session = Depends(get_db)) -> dict:
    return InvestmentLedgerService(db).statement_normalization_report(user_id=user_id)


@router.post("/repair-workflow", status_code=201)
def create_ledger_repair_workflow(user_id: str = "default-user", db: Session = Depends(get_db)) -> dict:
    return InvestmentLedgerService(db).repair_workflow(user_id=user_id)


@router.post("/repair-workflow/rerun-reconciliation", status_code=201)
def rerun_ledger_repair_reconciliation(user_id: str = "default-user", db: Session = Depends(get_db)) -> dict:
    return jsonable_encoder(InvestmentLedgerService(db).rerun_repair_reconciliation(user_id=user_id))


@router.get("/statement-imports/{batch_id}/rows/{row_index}")
def get_statement_row_detail(
    batch_id: str,
    row_index: int,
    user_id: str = "default-user",
    db: Session = Depends(get_db),
) -> dict:
    try:
        return InvestmentLedgerService(db).statement_row_detail(batch_id=batch_id, row_index=row_index, user_id=user_id)
    except LedgerImportError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/data-promotion-report")
def get_ledger_data_promotion_report(user_id: str = "default-user", db: Session = Depends(get_db)) -> dict:
    return InvestmentLedgerService(db).data_promotion_report(user_id=user_id)


@router.post("/sync", response_model=LedgerSyncResponse, status_code=201)
def sync_ledger(user_id: str = "default-user", limit: int = 200, db: Session = Depends(get_db)) -> dict:
    return InvestmentLedgerService(db).sync(user_id=user_id, limit=limit)


@router.post("/reconcile", response_model=LedgerReconciliationReportRead, status_code=201)
def reconcile_ledger(user_id: str = "default-user", db: Session = Depends(get_db)) -> dict:
    return InvestmentLedgerService(db).reconcile(user_id=user_id)


@router.post("/reconcile/extended", response_model=LedgerReconciliationReportRead, status_code=201)
def reconcile_extended_ledger(user_id: str = "default-user", db: Session = Depends(get_db)) -> dict:
    return InvestmentLedgerService(db).reconcile_extended(user_id=user_id)


@router.get("/reconciliation/latest", response_model=LedgerReconciliationReportRead)
def latest_reconciliation(user_id: str = "default-user", db: Session = Depends(get_db)) -> dict:
    report = InvestmentLedgerService(db).latest_reconciliation(user_id=user_id)
    if report is None:
        raise HTTPException(status_code=404, detail="reconciliation run not found")
    return report
