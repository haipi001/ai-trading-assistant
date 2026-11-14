from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session
from app.api.production import production_user
from app.core.auth import AuthenticatedUser
from app.db.session import get_db
from app.api.news_feed import access
from app.services.subscriptions import SubscriptionService

router = APIRouter(prefix='/subscriptions', tags=['subscriptions'])

@router.get('')
def list_subscriptions(response: Response, actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)):
    access(actor, 'readiness:read')
    response.headers['Cache-Control'] = 'no-store'
    return SubscriptionService(db, actor.user_id).list()

@router.get('/feed/{target}')
def subscription_feed(target: str, response: Response, actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)):
    access(actor, 'readiness:read')
    response.headers['Cache-Control'] = 'no-store'
    if target not in ('news','quotes'): raise HTTPException(422)
    return SubscriptionService(db,actor.user_id).feed(target)

@router.post('/{identifier}/refresh')
def refresh_subscription(identifier: str, response: Response, actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)):
    access(actor, 'readiness:read')
    response.headers['Cache-Control'] = 'no-store'
    try:
        return SubscriptionService(db,actor.user_id).refresh(identifier)
    except ValueError:
        raise HTTPException(422,detail={'code':'subscription_unavailable'}) from None

@router.put('/{identifier}')
async def save_subscription(identifier: str, request: Request, response: Response, actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)):
    access(actor, 'secrets:write')
    response.headers['Cache-Control'] = 'no-store'
    try:
        import json
        raw = await request.body()
        if len(raw)>20000: raise ValueError('配置过大')
        payload = json.loads(raw)
        if not isinstance(payload,dict): raise ValueError('配置无效')
        return SubscriptionService(db,actor.user_id).save(identifier,payload)
    except (ValueError,TypeError):
        raise HTTPException(422, detail={'code':'subscription_invalid'}) from None

@router.post('/{identifier}/test')
def test_subscription(identifier: str, response: Response, actor: AuthenticatedUser = Depends(production_user), db: Session = Depends(get_db)):
    access(actor, 'secrets:write')
    response.headers['Cache-Control'] = 'no-store'
    try:
        return SubscriptionService(db,actor.user_id).test(identifier)
    except ValueError:
        raise HTTPException(422, detail={'code':'subscription_unavailable'}) from None
