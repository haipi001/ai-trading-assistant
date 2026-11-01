from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.auth import AuthenticatedUser
from app.core.auth import require_permission
from app.db.session import get_db
from app.services.fundraising_readiness import FundraisingReadinessService

router = APIRouter(prefix="/fundraising/readiness", tags=["fundraising-readiness"])


@router.get("/summary")
def fundraising_readiness_summary(
    current_user: AuthenticatedUser = Depends(require_permission("readiness:read")),
    db: Session = Depends(get_db),
) -> dict:
    return FundraisingReadinessService(db).summary(user_id=current_user.user_id)


@router.get("/items")
def fundraising_readiness_items(
    current_user: AuthenticatedUser = Depends(require_permission("readiness:read")),
    db: Session = Depends(get_db),
) -> list[dict]:
    return FundraisingReadinessService(db).items(user_id=current_user.user_id)


@router.get("/items/{item_no}")
def fundraising_readiness_item(
    item_no: int,
    current_user: AuthenticatedUser = Depends(require_permission("readiness:read")),
    db: Session = Depends(get_db),
) -> dict:
    try:
        return FundraisingReadinessService(db).item(item_no, user_id=current_user.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
