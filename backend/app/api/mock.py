from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from app.services.asset_identity import AssetIdentityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.mock_import import import_mock_accounts
from app.services.mock_import import import_mock_positions
from app.services.mock_import import update_mock_quotes

router = APIRouter(prefix="/mock", tags=["mock"])


@router.post("/import-accounts")
def import_accounts(db: Session = Depends(get_db)) -> dict:
    return import_mock_accounts(db)


@router.post("/import-positions")
def import_positions(db: Session = Depends(get_db)) -> dict:
    try:
        return import_mock_positions(db)
    except AssetIdentityError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/update-quotes")
def update_quotes(db: Session = Depends(get_db)) -> dict:
    try:
        return update_mock_quotes(db)
    except AssetIdentityError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
