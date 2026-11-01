from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session
from app.api.production import production_user
from app.core.auth import AuthenticatedUser
from app.db.session import get_db
from app.services.news_feed import NewsFeedError, NewsFeedService

router = APIRouter(prefix="/news-feed", tags=["news-feed"])


def access(actor, permission):
    if permission not in actor.permissions:
        raise HTTPException(403, detail={"code": "news_permission_required"})


@router.get("/settings")
def settings(response: Response, actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)):
    access(actor, "readiness:read")
    response.headers["Cache-Control"] = "no-store"
    return NewsFeedService(db, actor.user_id).settings()


@router.put("/settings")
async def configure(request: Request, response: Response, actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)):
    access(actor, "secrets:write")
    response.headers["Cache-Control"] = "no-store"
    try:
        import json
        raw = await request.body()
        if len(raw) > 4096:
            raise ValueError()
        payload = json.loads(raw)
        if not isinstance(payload, dict) or set(payload) - {"provider", "sources", "query", "symbols", "language", "refresh_seconds", "auto_refresh", "api_key"}:
            raise ValueError()
        return NewsFeedService(db, actor.user_id).configure(payload)
    except NewsFeedError as exc:
        raise HTTPException(422, detail={"code": exc.code}) from None
    except (ValueError, TypeError):
        raise HTTPException(422, detail={"code": "news_settings_invalid"}) from None


@router.get("/latest")
def latest(response: Response, actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)):
    access(actor, "readiness:read")
    response.headers["Cache-Control"] = "no-store"
    return NewsFeedService(db, actor.user_id).latest()


@router.post("/refresh")
def refresh(response: Response, automatic: bool = False, actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)):
    access(actor, "readiness:read")
    response.headers["Cache-Control"] = "no-store"
    return NewsFeedService(db, actor.user_id).refresh(automatic=automatic)
