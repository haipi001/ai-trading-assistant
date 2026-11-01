from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import DataCatalogEntry
from app.schemas import DataCatalogEntryRead
from app.schemas import DataCatalogEntryDetailRead
from app.schemas import DataCatalogOverviewRead
from app.schemas import DataTrustReportRead
from app.services.data_catalog import DataCatalogNotFoundError
from app.services.data_catalog import DataCatalogService

router = APIRouter(prefix="/data-catalog", tags=["data-catalog"])


@router.get("/entries", response_model=list[DataCatalogEntryRead])
def list_data_catalog_entries(
    dataset_type: str | None = None,
    quality_status: str | None = None,
    usable_for_trading: bool | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
) -> list[DataCatalogEntry]:
    return DataCatalogService(db).list_entries(
        dataset_type=dataset_type,
        quality_status=quality_status,
        usable_for_trading=usable_for_trading,
        limit=limit,
    )


@router.get("/overview", response_model=DataCatalogOverviewRead)
def get_data_catalog_overview(limit: int = 8, db: Session = Depends(get_db)) -> dict:
    return DataCatalogService(db).overview(limit=limit)


@router.get("/trust-report", response_model=DataTrustReportRead)
def get_data_trust_report(decision_scope: str = "research", db: Session = Depends(get_db)) -> dict:
    try:
        return DataCatalogService(db).trust_report(decision_scope=decision_scope)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/provenance-report")
def get_data_provenance_report(
    decision_scope: str = "research",
    limit: int = 50,
    db: Session = Depends(get_db),
) -> dict:
    try:
        return DataCatalogService(db).provenance_report(decision_scope=decision_scope, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/contract-enforcement-report")
def get_contract_enforcement_report(
    decision_scope: str = "research",
    limit: int = 50,
    db: Session = Depends(get_db),
) -> dict:
    try:
        return DataCatalogService(db).contract_enforcement_report(decision_scope=decision_scope, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/entries/{entry_id}", response_model=DataCatalogEntryDetailRead)
def get_data_catalog_entry_detail(entry_id: str, db: Session = Depends(get_db)) -> dict:
    try:
        return DataCatalogService(db).entry_detail(entry_id)
    except DataCatalogNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/entries/{entry_id}/version")
def version_data_catalog_entry_snapshot(entry_id: str, db: Session = Depends(get_db)) -> dict:
    try:
        return DataCatalogService(db).version_entry_snapshot(entry_id)
    except DataCatalogNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/entries/{entry_id}/promotion")
def get_data_catalog_entry_promotion(entry_id: str, db: Session = Depends(get_db)) -> dict:
    try:
        return DataCatalogService(db).promotion_status(entry_id)
    except DataCatalogNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/entries/{entry_id}/promote")
def promote_data_catalog_entry(entry_id: str, db: Session = Depends(get_db)) -> dict:
    """Advance a catalog entry through raw → reviewed → trusted based on
    quality and reconciliation evidence. Review-only; creates no orders."""
    try:
        return DataCatalogService(db).promote_entry(entry_id)
    except DataCatalogNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/entries/{entry_id}/replay-preflight")
def preflight_data_catalog_entry_replay(entry_id: str, db: Session = Depends(get_db)) -> dict:
    try:
        return DataCatalogService(db).replay_preflight(entry_id)
    except DataCatalogNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/entries/{entry_id}/replay")
def replay_data_catalog_entry_snapshot(entry_id: str, db: Session = Depends(get_db)) -> dict:
    try:
        return jsonable_encoder(DataCatalogService(db).replay_entry_snapshot(entry_id))
    except DataCatalogNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/entries/{entry_id}/compare/{other_entry_id}")
def compare_data_catalog_entry_snapshots(
    entry_id: str, other_entry_id: str, db: Session = Depends(get_db)
) -> dict:
    try:
        return jsonable_encoder(DataCatalogService(db).compare_entry_snapshots(entry_id, other_entry_id))
    except DataCatalogNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
