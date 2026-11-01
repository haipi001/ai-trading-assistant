from fastapi import APIRouter, Depends, HTTPException, Response, Request
from pydantic import BaseModel, SecretStr, ConfigDict, ValidationError
from app.api.production import production_user
from app.core.auth import AuthenticatedUser
from app.services.exchange_connection_probe import BinanceConnectionProbe, ExchangeProbeError

router = APIRouter(prefix='/exchange-connections', tags=['exchange-connections'])

class ProbeCredentials(BaseModel):
    model_config = ConfigDict(extra='forbid')
    api_key: SecretStr
    api_secret: SecretStr

@router.post('/binance/probe')
async def probe_binance(request: Request, response: Response, actor: AuthenticatedUser = Depends(production_user)):
    if 'secrets:write' not in actor.permissions:
        raise HTTPException(403, detail={'code': 'credential_permission_required'})
    response.headers['Cache-Control'] = 'no-store'
    try:
        raw = await request.body()
        if len(raw) > 4096: raise ValueError()
        payload = ProbeCredentials.model_validate_json(raw)
    except (ValidationError, ValueError):
        raise HTTPException(422, detail={'code': 'invalid_credentials_fields'}) from None
    try:
        from starlette.concurrency import run_in_threadpool
        return await run_in_threadpool(BinanceConnectionProbe().verify, payload.api_key.get_secret_value(), payload.api_secret.get_secret_value())
    except ExchangeProbeError as exc:
        raise HTTPException(422, detail={'code': exc.code}) from None

from sqlalchemy.orm import Session
from app.db.session import get_db
from app.services.exchange_connections import ExchangeConnectionService

class SavedCredentials(ProbeCredentials):
    label: str

async def read_saved_credentials(request):
    try:
        raw=await request.body()
        if len(raw)>8192:raise ValueError()
        return SavedCredentials.model_validate_json(raw)
    except (ValueError,ValidationError):
        raise HTTPException(422,detail={'code':'invalid_credentials_fields'},headers={'Cache-Control':'no-store'}) from None

def require_credentials_access(actor):
    if 'secrets:write' not in actor.permissions:
        raise HTTPException(403,detail={'code':'credential_permission_required'})

@router.get('')
def list_connections(response: Response, actor: AuthenticatedUser=Depends(production_user),db: Session=Depends(get_db)):
    require_credentials_access(actor);response.headers['Cache-Control']='no-store'
    return ExchangeConnectionService(db,actor.user_id).list()

@router.post('/binance',status_code=201)
async def save_binance(request: Request,response: Response,actor: AuthenticatedUser=Depends(production_user),db: Session=Depends(get_db)):
    require_credentials_access(actor);response.headers['Cache-Control']='no-store'
    payload=await read_saved_credentials(request)
    try:
        from starlette.concurrency import run_in_threadpool
        return await run_in_threadpool(ExchangeConnectionService(db,actor.user_id).create,payload.label,payload.api_key.get_secret_value(),payload.api_secret.get_secret_value())
    except ExchangeProbeError as exc:
        raise HTTPException(422,detail={'code':exc.code},headers={'Cache-Control':'no-store'}) from None

@router.post('/{connection_id}/check')
def check_connection(connection_id: str,response: Response,actor: AuthenticatedUser=Depends(production_user),db: Session=Depends(get_db)):
    require_credentials_access(actor);response.headers['Cache-Control']='no-store'
    try:return ExchangeConnectionService(db,actor.user_id).check(connection_id)
    except ExchangeProbeError as exc:
        raise HTTPException(404 if exc.code=='connection_not_found' else 422,detail={'code':exc.code},headers={'Cache-Control':'no-store'}) from None

@router.delete('/{connection_id}')
def disable_connection(connection_id: str,response: Response,actor: AuthenticatedUser=Depends(production_user),db: Session=Depends(get_db)):
    require_credentials_access(actor);response.headers['Cache-Control']='no-store'
    try:return ExchangeConnectionService(db,actor.user_id).disable(connection_id)
    except ExchangeProbeError as exc:
        raise HTTPException(404 if exc.code=='connection_not_found' else 422,detail={'code':exc.code}) from None

@router.patch('/{connection_id}')
async def rename_connection(connection_id: str,request: Request,response: Response,actor: AuthenticatedUser=Depends(production_user),db: Session=Depends(get_db)):
    require_credentials_access(actor);response.headers['Cache-Control']='no-store'
    try:
        import json
        raw=await request.body()
        if len(raw)>1024:raise ValueError()
        payload=json.loads(raw)
        if not isinstance(payload,dict) or set(payload)!={'label'}:raise ValueError()
    except (ValueError,TypeError):
        raise HTTPException(422,detail={'code':'invalid_connection_label'},headers={'Cache-Control':'no-store'}) from None
    try:return ExchangeConnectionService(db,actor.user_id).rename(connection_id,payload['label'])
    except ExchangeProbeError as exc:
        raise HTTPException(404 if exc.code=='connection_not_found' else 422,detail={'code':exc.code},headers={'Cache-Control':'no-store'}) from None


class OkxCredentials(ProbeCredentials):
    passphrase: SecretStr

class SavedOkxCredentials(OkxCredentials):
    label: str

@router.post('/okx/probe')
async def probe_okx(request: Request,response: Response,actor: AuthenticatedUser=Depends(production_user)):
    require_credentials_access(actor);response.headers['Cache-Control']='no-store'
    try:
        raw=await request.body()
        if len(raw)>8192:raise ValueError()
        payload=OkxCredentials.model_validate_json(raw)
    except (ValueError,ValidationError):raise HTTPException(422,detail={'code':'invalid_credentials_fields'}) from None
    try:
        from starlette.concurrency import run_in_threadpool
        from app.services.exchange_connection_probe import OkxConnectionProbe
        return await run_in_threadpool(OkxConnectionProbe().verify,payload.api_key.get_secret_value(),payload.api_secret.get_secret_value(),payload.passphrase.get_secret_value())
    except ExchangeProbeError as exc:raise HTTPException(422,detail={'code':exc.code}) from None

@router.post('/okx',status_code=201)
async def save_okx(request: Request,response: Response,actor: AuthenticatedUser=Depends(production_user),db: Session=Depends(get_db)):
    require_credentials_access(actor);response.headers['Cache-Control']='no-store'
    try:
        raw=await request.body()
        if len(raw)>8192:raise ValueError()
        payload=SavedOkxCredentials.model_validate_json(raw)
    except (ValueError,ValidationError):raise HTTPException(422,detail={'code':'invalid_credentials_fields'}) from None
    try:
        from starlette.concurrency import run_in_threadpool
        return await run_in_threadpool(ExchangeConnectionService(db,actor.user_id).create,payload.label,payload.api_key.get_secret_value(),payload.api_secret.get_secret_value(),'okx',payload.passphrase.get_secret_value())
    except ExchangeProbeError as exc:raise HTTPException(422,detail={'code':exc.code}) from None


@router.post('/bybit/probe')
async def probe_bybit(request: Request,response: Response,actor: AuthenticatedUser=Depends(production_user)):
    require_credentials_access(actor);response.headers['Cache-Control']='no-store'
    try:
        raw=await request.body()
        if len(raw)>4096:raise ValueError()
        payload=ProbeCredentials.model_validate_json(raw)
    except (ValueError,ValidationError):raise HTTPException(422,detail={'code':'invalid_credentials_fields'}) from None
    try:
        from starlette.concurrency import run_in_threadpool
        from app.services.exchange_connection_probe import BybitConnectionProbe
        return await run_in_threadpool(BybitConnectionProbe().verify,payload.api_key.get_secret_value(),payload.api_secret.get_secret_value())
    except ExchangeProbeError as exc:raise HTTPException(422,detail={'code':exc.code}) from None

@router.post('/bybit',status_code=201)
async def save_bybit(request: Request,response: Response,actor: AuthenticatedUser=Depends(production_user),db: Session=Depends(get_db)):
    require_credentials_access(actor);response.headers['Cache-Control']='no-store'
    payload=await read_saved_credentials(request)
    try:
        from starlette.concurrency import run_in_threadpool
        return await run_in_threadpool(ExchangeConnectionService(db,actor.user_id).create,payload.label,payload.api_key.get_secret_value(),payload.api_secret.get_secret_value(),'bybit')
    except ExchangeProbeError as exc:raise HTTPException(422,detail={'code':exc.code}) from None


@router.post('/bitget/probe')
async def probe_bitget(request: Request,response: Response,actor: AuthenticatedUser=Depends(production_user)):
    require_credentials_access(actor);response.headers['Cache-Control']='no-store'
    try:
        raw=await request.body()
        if len(raw)>8192:raise ValueError()
        payload=OkxCredentials.model_validate_json(raw)
    except (ValueError,ValidationError):raise HTTPException(422,detail={'code':'invalid_credentials_fields'}) from None
    try:
        from starlette.concurrency import run_in_threadpool
        from app.services.exchange_connection_probe import BitgetConnectionProbe
        return await run_in_threadpool(BitgetConnectionProbe().verify,payload.api_key.get_secret_value(),payload.api_secret.get_secret_value(),payload.passphrase.get_secret_value())
    except ExchangeProbeError as exc:raise HTTPException(422,detail={'code':exc.code}) from None

@router.post('/bitget',status_code=201)
async def save_bitget(request: Request,response: Response,actor: AuthenticatedUser=Depends(production_user),db: Session=Depends(get_db)):
    require_credentials_access(actor);response.headers['Cache-Control']='no-store'
    try:
        raw=await request.body()
        if len(raw)>8192:raise ValueError()
        payload=SavedOkxCredentials.model_validate_json(raw)
    except (ValueError,ValidationError):raise HTTPException(422,detail={'code':'invalid_credentials_fields'}) from None
    try:
        from starlette.concurrency import run_in_threadpool
        return await run_in_threadpool(ExchangeConnectionService(db,actor.user_id).create,payload.label,payload.api_key.get_secret_value(),payload.api_secret.get_secret_value(),'bitget',payload.passphrase.get_secret_value())
    except ExchangeProbeError as exc:raise HTTPException(422,detail={'code':exc.code}) from None


@router.post('/gate/probe')
async def probe_gate(request: Request,response: Response,actor: AuthenticatedUser=Depends(production_user)):
    require_credentials_access(actor);response.headers['Cache-Control']='no-store'
    try:
        raw=await request.body()
        if len(raw)>4096:raise ValueError()
        payload=ProbeCredentials.model_validate_json(raw)
    except (ValueError,ValidationError):raise HTTPException(422,detail={'code':'invalid_credentials_fields'}) from None
    try:
        from starlette.concurrency import run_in_threadpool
        from app.services.exchange_connection_probe import GateConnectionProbe
        return await run_in_threadpool(GateConnectionProbe().verify,payload.api_key.get_secret_value(),payload.api_secret.get_secret_value())
    except ExchangeProbeError as exc:raise HTTPException(422,detail={'code':exc.code}) from None

@router.post('/gate',status_code=201)
async def save_gate(request: Request,response: Response,actor: AuthenticatedUser=Depends(production_user),db: Session=Depends(get_db)):
    require_credentials_access(actor);response.headers['Cache-Control']='no-store'
    payload=await read_saved_credentials(request)
    try:
        from starlette.concurrency import run_in_threadpool
        return await run_in_threadpool(ExchangeConnectionService(db,actor.user_id).create,payload.label,payload.api_key.get_secret_value(),payload.api_secret.get_secret_value(),'gate')
    except ExchangeProbeError as exc:raise HTTPException(422,detail={'code':exc.code}) from None
