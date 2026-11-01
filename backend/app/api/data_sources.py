from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import DataQualityReport
from app.models import DataSnapshot
from app.models import DataSourceConnection
from app.schemas import DataQualityReportRead
from app.schemas.core import DataQualityExplanationRead
from app.schemas.core import DataSourceAccountAutoRefreshRequest
from app.schemas import DataSnapshotRead
from app.schemas import DataSourceAccountSyncRequest
from app.schemas import DataSourceAccountSyncResponse
from app.schemas import DataSourceConnectionCreate
from app.schemas import DataSourceCandleImportRequest
from app.schemas import DataSourceCandleImportResponse
from app.schemas import DataSourceConnectionRead
from app.schemas import DataFreshnessOverviewRead
from app.schemas import DataSourceHealthRead
from app.schemas import DataSourceProviderRead
from app.schemas import DataSourceQuoteImportRequest
from app.schemas import DataSourceQuoteImportResponse
from app.schemas import DataSourceReadOnlyPreflightResponse
from app.schemas import DataSourceReadOnlySetupRequest
from app.schemas import DataSourceReadOnlySetupResponse
from app.services.data_sources import DataSourceError
from app.services.data_sources import DataSourceNotFoundError
from app.services.data_sources import DataSourceService

router = APIRouter(prefix="/data-sources", tags=["data-sources"])
pipeline_router = APIRouter(prefix="/data-pipeline", tags=["data-pipeline"])


@router.get("/providers", response_model=list[DataSourceProviderRead])
def list_data_source_providers(db: Session = Depends(get_db)) -> list:
    return DataSourceService(db).list_providers()


@router.get("/connections", response_model=list[DataSourceConnectionRead])
def list_data_source_connections(db: Session = Depends(get_db)) -> list[DataSourceConnection]:
    return DataSourceService(db).list_connections()


@router.post("/connections/defaults", response_model=list[DataSourceConnectionRead], status_code=201)
def ensure_default_data_source_connections(db: Session = Depends(get_db)) -> list[DataSourceConnection]:
    return DataSourceService(db).ensure_default_connections()


@router.post("/connections/read-only-account-placeholders", response_model=list[DataSourceConnectionRead], status_code=201)
def ensure_readonly_account_placeholders(db: Session = Depends(get_db)) -> list[DataSourceConnection]:
    return DataSourceService(db).ensure_readonly_account_placeholders()


@router.get("/freshness", response_model=DataFreshnessOverviewRead)
def get_data_freshness(db: Session = Depends(get_db)) -> dict:
    return DataSourceService(db).freshness_overview()


@router.get("/fallback-policy")
def get_data_source_fallback_policy(db: Session = Depends(get_db)) -> dict:
    return jsonable_encoder(DataSourceService(db).fallback_policy())


@router.post("/connections/read-only-setup", response_model=DataSourceReadOnlySetupResponse, status_code=201)
def setup_readonly_data_source_connection(
    payload: DataSourceReadOnlySetupRequest,
    db: Session = Depends(get_db),
) -> DataSourceReadOnlySetupResponse:
    try:
        result = DataSourceService(db).setup_readonly_connection(**payload.model_dump())
    except DataSourceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return DataSourceReadOnlySetupResponse(
        connection=result.connection,
        provider_status=result.provider_status,
        safety_checks=result.safety_checks,
        next_actions=result.next_actions,
        execution_available=False,
    )


@router.post("/binance/read-only-evidence/preflight")
def preflight_binance_readonly_evidence(
    payload: dict | None = None,
    user_id: str = "default-user",
    db: Session = Depends(get_db),
) -> dict:
    try:
        return jsonable_encoder(DataSourceService(db).binance_readonly_evidence_preflight(user_id=user_id, payload=payload or {}))
    except DataSourceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/connections/{connection_id}/read-only-preflight", response_model=DataSourceReadOnlyPreflightResponse)
def check_readonly_data_source_preflight(
    connection_id: str,
    db: Session = Depends(get_db),
) -> DataSourceReadOnlyPreflightResponse:
    try:
        result = DataSourceService(db).read_only_preflight(connection_id)
    except DataSourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DataSourceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return DataSourceReadOnlyPreflightResponse(
        connection=result.connection,
        provider=result.provider,
        status=result.status,
        checked_at=result.checked_at,
        has_credentials_ref=result.has_credentials_ref,
        requires_credentials=result.requires_credentials,
        missing_requirements=result.missing_requirements,
        blocking_reasons=result.blocking_reasons,
        safety_checks=result.safety_checks,
        next_actions=result.next_actions,
        details=result.details,
        execution_available=False,
        order_routing_available=False,
        withdrawals_allowed=False,
        signing_available=False,
    )


@router.post("/connections/{connection_id}/read-only-certification")
def certify_readonly_data_source_connection(
    connection_id: str,
    db: Session = Depends(get_db),
) -> dict:
    try:
        result = DataSourceService(db).read_only_certification(connection_id)
    except DataSourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DataSourceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return jsonable_encoder({
        "connection": result.connection,
        "provider": result.provider,
        "status": result.status,
        "checked_at": result.checked_at,
        "certification_level": result.certification_level,
        "sample_sync_allowed": result.sample_sync_allowed,
        "contract_version": result.contract_version,
        "required_scopes": result.required_scopes,
        "forbidden_scopes": result.forbidden_scopes,
        "blockers": result.blockers,
        "warnings": result.warnings,
        "next_actions": result.next_actions,
        "preflight": result.preflight,
        "adapter_contract": result.adapter_contract,
        "execution_available": False,
    })


@router.post("/connections/{connection_id}/certified-sync-plan")
def create_certified_sync_plan(
    connection_id: str,
    db: Session = Depends(get_db),
) -> dict:
    try:
        return DataSourceService(db).certified_sync_plan(connection_id)
    except DataSourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DataSourceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/connections", response_model=DataSourceConnectionRead, status_code=201)
def create_data_source_connection(
    payload: DataSourceConnectionCreate,
    db: Session = Depends(get_db),
) -> DataSourceConnection:
    try:
        return DataSourceService(db).create_connection(**payload.model_dump())
    except DataSourceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/connections/{connection_id}/health", response_model=DataSourceHealthRead)
def check_data_source_health(connection_id: str, db: Session = Depends(get_db)) -> DataSourceHealthRead:
    try:
        health = DataSourceService(db).check_health(connection_id)
    except DataSourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DataSourceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return DataSourceHealthRead(connection_id=connection_id, **health.__dict__)


@router.post("/connections/{connection_id}/import-quotes", response_model=DataSourceQuoteImportResponse, status_code=201)
def import_data_source_quotes(
    connection_id: str,
    payload: DataSourceQuoteImportRequest,
    db: Session = Depends(get_db),
) -> DataSourceQuoteImportResponse:
    try:
        result = DataSourceService(db).import_quotes(connection_id, **payload.model_dump())
    except DataSourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DataSourceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return DataSourceQuoteImportResponse(
        connection=result.connection,
        quotes_imported=result.quotes_imported,
        symbols=result.symbols,
        skipped=result.skipped,
        snapshot=result.snapshot,
        quality_report=result.quality_report,
        catalog_entry=result.catalog_entry,
    )


@router.post("/connections/{connection_id}/import-candles", response_model=DataSourceCandleImportResponse, status_code=201)
def import_data_source_candles(
    connection_id: str,
    payload: DataSourceCandleImportRequest,
    db: Session = Depends(get_db),
) -> DataSourceCandleImportResponse:
    try:
        result = DataSourceService(db).import_candles(connection_id, **payload.model_dump())
    except DataSourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DataSourceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return DataSourceCandleImportResponse(
        connection=result.connection,
        candles_imported=result.candles_imported,
        symbols=result.symbols,
        timeframe=result.timeframe,
        skipped=result.skipped,
        snapshot=result.snapshot,
        quality_report=result.quality_report,
        catalog_entry=result.catalog_entry,
    )


@router.post("/connections/{connection_id}/sync-account", response_model=DataSourceAccountSyncResponse, status_code=201)
def sync_data_source_account(
    connection_id: str,
    payload: DataSourceAccountSyncRequest,
    db: Session = Depends(get_db),
) -> DataSourceAccountSyncResponse:
    try:
        result = DataSourceService(db).sync_account_snapshot(connection_id, **payload.model_dump())
    except DataSourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DataSourceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return DataSourceAccountSyncResponse(
        connection=result.connection,
        account=result.account,
        positions_synced=result.positions_synced,
        balances_synced=result.balances_synced,
        orders_seen=result.orders_seen,
        snapshot=result.snapshot,
        quality_report=result.quality_report,
        portfolio_snapshot=result.portfolio_snapshot,
        catalog_entry=result.catalog_entry,
        ledger_sync=result.ledger_sync,
        reconciliation=result.reconciliation,
    )


@router.put("/connections/{connection_id}/auto-refresh")
def configure_data_source_account_auto_refresh(
    connection_id: str,
    payload: DataSourceAccountAutoRefreshRequest,
    db: Session = Depends(get_db),
) -> dict:
    try:
        return DataSourceService(db).configure_account_auto_refresh(
            connection_id,
            user_id=payload.user_id,
            enabled=payload.enabled,
            interval_minutes=payload.interval_minutes,
        )
    except DataSourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DataSourceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/connections/{connection_id}/sync-history")
def get_data_source_account_sync_history(
    connection_id: str,
    user_id: str = "default-user",
    limit: int = 50,
    db: Session = Depends(get_db),
) -> dict:
    try:
        return DataSourceService(db).account_sync_history(
            connection_id,
            user_id=user_id,
            limit=limit,
        )
    except DataSourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@pipeline_router.get("/snapshots", response_model=list[DataSnapshotRead])
def list_data_snapshots(
    snapshot_type: str | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
) -> list[DataSnapshot]:
    return DataSourceService(db).list_snapshots(snapshot_type=snapshot_type, limit=limit)


@pipeline_router.get("/quality-reports", response_model=list[DataQualityReportRead])
def list_data_quality_reports(
    source: str | None = None,
    limit: int = 10,
    db: Session = Depends(get_db),
) -> list[DataQualityReport]:
    return DataSourceService(db).list_quality_reports(source=source, limit=limit)


@pipeline_router.get("/quality-reports/{report_id}/explain", response_model=DataQualityExplanationRead)
def explain_data_quality_report(report_id: str, db: Session = Depends(get_db)) -> dict:
    try:
        return DataSourceService(db).explain_quality_report(report_id)
    except DataSourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
