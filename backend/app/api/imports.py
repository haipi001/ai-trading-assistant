from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas import CsvImportRequest
from app.schemas import CsvImportResponse
from app.services.csv_import import CsvImportError
from app.services.csv_import import CsvImportService

router = APIRouter(prefix="/imports", tags=["imports"])


@router.post("/csv", response_model=CsvImportResponse, status_code=201)
def import_csv(payload: CsvImportRequest, db: Session = Depends(get_db)) -> CsvImportResponse:
    try:
        result = CsvImportService(db).import_csv(**payload.model_dump())
    except CsvImportError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return CsvImportResponse(
        import_type=result.import_type,
        rows_received=result.rows_received,
        rows_imported=result.rows_imported,
        rows_skipped=result.rows_skipped,
        accounts_created=result.accounts_created,
        assets_created=result.assets_created,
        positions_upserted=result.positions_upserted,
        snapshot=result.snapshot,
        quality_report=result.quality_report,
        catalog_entry=result.catalog_entry,
        skipped=result.skipped,
        execution_available=False,
    )
