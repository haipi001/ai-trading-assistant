from fastapi import APIRouter
from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import PortfolioSnapshot
from app.schemas import PortfolioCurrentRead
from app.schemas import PortfolioDailySummaryRead
from app.schemas import PortfolioSnapshotRead
from app.services.portfolio import PortfolioSnapshotService
from app.services.portfolio import PortfolioSummaryService

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.get("/current", response_model=PortfolioCurrentRead)
def get_current_portfolio(account_id: str | None = None, db: Session = Depends(get_db)) -> dict:
    return PortfolioSummaryService(db).build_current(account_id)


@router.post("/snapshot", response_model=PortfolioSnapshotRead, status_code=201)
def create_portfolio_snapshot(db: Session = Depends(get_db)) -> PortfolioSnapshot:
    return PortfolioSnapshotService(db).create_snapshot()


@router.get("/daily-summary", response_model=PortfolioDailySummaryRead)
def get_daily_summary(account_id: str | None = None, db: Session = Depends(get_db)) -> dict:
    return PortfolioSummaryService(db).build_daily_summary(account_id)
