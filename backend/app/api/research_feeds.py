import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.research_feeds import ResearchFeedError, ResearchFeedService

router = APIRouter(prefix="/research-feeds", tags=["research-feeds"])

@router.get("/overview")
def overview(db: Session = Depends(get_db)) -> dict:
    return ResearchFeedService(db).overview()

@router.post("/evidence-packet")
def create_evidence_packet(payload: dict | None = None, user_id: str = "default-user", db: Session = Depends(get_db)) -> dict:
    resolved_user_id = str((payload or {}).get("user_id") or user_id or "default-user")
    return ResearchFeedService(db).evidence_packet(user_id=resolved_user_id)

@router.get("/news/latest")
def latest_news(db: Session = Depends(get_db)) -> dict:
    return ResearchFeedService(db).latest_news()

@router.post("/news/sync")
def sync_news(payload: dict, db: Session = Depends(get_db)) -> dict:
    return _call(lambda: ResearchFeedService(db).sync_nasdaq_news(symbols=payload.get("symbols") or [], limit_per_symbol=int(payload.get("limit_per_symbol") or 10)))

@router.post("/sec/sync")
def sync_sec(payload: dict, db: Session = Depends(get_db)) -> dict:
    return _call(lambda: ResearchFeedService(db).sync_sec_filings_and_fundamentals(symbols=payload.get("symbols") or [], limit_per_symbol=int(payload.get("limit_per_symbol") or 12)))

@router.post("/macro/sync")
def sync_macro(payload: dict | None = None, db: Session = Depends(get_db)) -> dict:
    return _call(lambda: ResearchFeedService(db).sync_fred_macro(series=(payload or {}).get("series")))

@router.post("/onchain/sync")
def sync_onchain(payload: dict | None = None, db: Session = Depends(get_db)) -> dict:
    return _call(lambda: ResearchFeedService(db).sync_onchain_metrics(metrics=(payload or {}).get("metrics"), timespan=str((payload or {}).get("timespan") or "90days")))

@router.post("/catalyst-calendar/sync")
def sync_calendar(payload: dict, db: Session = Depends(get_db)) -> dict:
    return _call(lambda: ResearchFeedService(db).sync_catalyst_calendar(symbols=payload.get("symbols") or [], days=int(payload.get("days") or 14)))

@router.get("/thesis-delta/{thesis_id}")
def get_thesis_delta(thesis_id: str, db: Session = Depends(get_db)) -> dict:
    """Review-only 'what changed since this thesis' report from locally stored
    evidence (candles + synced feed snapshots). No network calls, no orders."""
    try:
        return ResearchFeedService(db).thesis_delta(thesis_id)
    except ResearchFeedError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

def _call(callback):
    try:
        return callback()
    except (ResearchFeedError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
