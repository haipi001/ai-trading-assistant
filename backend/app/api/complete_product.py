from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.auth import AuthenticatedUser
from app.core.auth import require_permission
from app.db.session import get_db
from app.services.complete_product_buildout import CompleteProductBuildoutService
from app.services.complete_product_readiness import CompleteProductReadinessService

router = APIRouter(prefix="/complete-product/readiness", tags=["complete-product-readiness"])


@router.get("/summary")
def complete_product_readiness_summary(
    current_user: AuthenticatedUser = Depends(require_permission("readiness:read")),
    db: Session = Depends(get_db),
) -> dict:
    return CompleteProductReadinessService(db).summary(user_id=current_user.user_id)


@router.get("/items")
def complete_product_readiness_items(
    current_user: AuthenticatedUser = Depends(require_permission("readiness:read")),
    db: Session = Depends(get_db),
) -> list[dict]:
    return CompleteProductReadinessService(db).items(user_id=current_user.user_id)


@router.get("/items/{item_no}")
def complete_product_readiness_item(
    item_no: int,
    current_user: AuthenticatedUser = Depends(require_permission("readiness:read")),
    db: Session = Depends(get_db),
) -> dict:
    try:
        return CompleteProductReadinessService(db).item(item_no, user_id=current_user.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/buildout/summary")
def complete_product_buildout_summary(
    current_user: AuthenticatedUser = Depends(require_permission("readiness:read")),
    db: Session = Depends(get_db),
) -> dict:
    return CompleteProductBuildoutService(db).summary(user_id=current_user.user_id)


@router.get("/buildout/projects")
def complete_product_buildout_projects(
    current_user: AuthenticatedUser = Depends(require_permission("readiness:read")),
    db: Session = Depends(get_db),
) -> list[dict]:
    return CompleteProductBuildoutService(db).projects(user_id=current_user.user_id)


@router.get("/launch-preparation")
def complete_product_launch_preparation(
    current_user: AuthenticatedUser = Depends(require_permission("readiness:read")),
    db: Session = Depends(get_db),
) -> dict:
    return CompleteProductBuildoutService(db).launch_preparation(user_id=current_user.user_id)


@router.get("/private-core")
def complete_product_private_core(
    current_user: AuthenticatedUser = Depends(require_permission("readiness:read")),
    db: Session = Depends(get_db),
) -> dict:
    return CompleteProductBuildoutService(db).private_core(user_id=current_user.user_id)


@router.get("/safety-limited-capabilities")
def complete_product_safety_limited_capabilities(
    current_user: AuthenticatedUser = Depends(require_permission("readiness:read")),
    db: Session = Depends(get_db),
) -> dict:
    return CompleteProductBuildoutService(db).safety_limited_capabilities(user_id=current_user.user_id)
