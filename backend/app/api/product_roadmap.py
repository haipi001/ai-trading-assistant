from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException

from app.core.auth import AuthenticatedUser
from app.core.auth import require_permission
from app.services.product_roadmap import ProductRoadmapService

router = APIRouter(prefix="/product-roadmap", tags=["product-roadmap"])


@router.get("/summary")
def product_roadmap_summary(
    current_user: AuthenticatedUser = Depends(require_permission("readiness:read")),
) -> dict:
    _ = current_user
    return ProductRoadmapService().summary()


@router.get("/phases")
def product_roadmap_phases(
    current_user: AuthenticatedUser = Depends(require_permission("readiness:read")),
) -> list[dict]:
    _ = current_user
    return ProductRoadmapService().phases()


@router.get("/phases/{phase_no}")
def product_roadmap_phase(
    phase_no: int,
    current_user: AuthenticatedUser = Depends(require_permission("readiness:read")),
) -> dict:
    _ = current_user
    try:
        return ProductRoadmapService().phase(phase_no)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
