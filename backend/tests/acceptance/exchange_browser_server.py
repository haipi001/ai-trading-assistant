"""Isolated browser fixture. Never contacts exchanges or opens the user's DB/secret file."""
import base64
import hashlib
import hmac
import json
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlparse
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
import uvicorn
from app.core import local_secrets
from app.services import exchange_connection_probe as probes

KEY='browser_fixture_key';SECRET='browser_fixture_secret';PASS='browser_fixture_passphrase'
CLOCK=1792800000000

def fixture_transport(request,timeout):
    parsed=urlparse(request.full_url);path=parsed.path
    headers={k.lower():v for k,v in request.headers.items()}
    assert request.get_method()=='GET'
    host=parsed.hostname
    if host=='api.binance.com':
        if path=='/api/v3/time':value={'serverTime':CLOCK}
        else:
            assert headers['x-mbx-apikey']==KEY
            unsigned,signature=parsed.query.rsplit('&signature=',1)
            assert signature==hmac.new(SECRET.encode(),unsigned.encode(),hashlib.sha256).hexdigest()
            if path=='/sapi/v1/account/apiRestrictions':value={**{flag:False for flag in probes.DANGEROUS_FLAGS},'enableReading':True}
            else:
                assert path=='/api/v3/account'
                value={'canTrade':True,'balances':[{'asset':'BTC','free':'1.25','locked':'0.25'}]}
    elif host=='www.okx.com':
        if path=='/api/v5/public/time':data=[{'ts':str(CLOCK)}]
        else:
            assert headers['ok-access-key']==KEY and headers['ok-access-passphrase']==PASS
            expected=base64.b64encode(hmac.new(SECRET.encode(),(headers['ok-access-timestamp']+'GET'+path).encode(),hashlib.sha256).digest()).decode()
            assert headers['ok-access-sign']==expected
            if path=='/api/v5/account/config':data=[{'perm':'read_only'}]
            else:
                assert path=='/api/v5/account/balance'
                data=[{'details':[{'ccy':'BTC','availBal':'1.25','frozenBal':'0.25'}]}]
        value={'code':'0','data':data}
    elif host=='api.bybit.com':
        if path=='/v5/market/time':data={'timeNano':str(CLOCK*1000000)}
        else:
            assert headers['x-bapi-api-key']==KEY
            expected=hmac.new(SECRET.encode(),(headers['x-bapi-timestamp']+KEY+'5000'+parsed.query).encode(),hashlib.sha256).hexdigest()
            assert headers['x-bapi-sign']==expected
            if path=='/v5/user/query-api':data={'readOnly':1,'permissions':{'Wallet':[],'Withdraw':[]}}
            else:
                assert path=='/v5/account/wallet-balance' and parsed.query=='accountType=UNIFIED'
                data={'list':[{'accountType':'UNIFIED','coin':[{'coin':'BTC','walletBalance':'1.5','equity':'1.75','locked':'0.25'}]}]}
        value={'retCode':0,'result':data}
    elif host=='api.bitget.com':
        if path=='/api/v2/public/time':data={'serverTime':str(CLOCK)}
        else:
            assert headers['access-key']==KEY and headers['access-passphrase']==PASS
            expected=base64.b64encode(hmac.new(SECRET.encode(),(headers['access-timestamp']+'GET'+path).encode(),hashlib.sha256).digest()).decode()
            assert headers['access-sign']==expected
            if path=='/api/v3/account/info':data={'permType':'read-only','permissions':['uta_mgt']}
            else:
                assert path=='/api/v3/account/assets'
                data={'assets':[{'coin':'BTC','available':'1.25','locked':'0.25','balance':'1.5','equity':'1.75'}]}
        value={'code':'00000','data':data}
    elif host=='api.gateio.ws':
        if path=='/api/v4/spot/time':value={'server_time':CLOCK}
        else:
            assert headers['key']==KEY
            prehash='\n'.join(['GET',path,'',hashlib.sha512(b'').hexdigest(),headers['timestamp']])
            assert headers['sign']==hmac.new(SECRET.encode(),prehash.encode(),hashlib.sha512).hexdigest()
            if path=='/api/v4/account/main_keys':value=[{'key':KEY,'state':1,'mode':1,'perms':[{'name':'account','read_only':True},{'name':'spot','read_only':True}]}]
            else:
                assert path=='/api/v4/spot/accounts'
                value=[{'currency':'BTC','available':'1.25','locked':'0.25'}]
    else:raise AssertionError('fixture has no network fallback')
    return BytesIO(json.dumps(value).encode())

if __name__=='__main__':
    with TemporaryDirectory(prefix='exchange-browser-fixture-') as directory:
        local_secrets.store_path=lambda:Path(directory)/'credentials.env'
        probes.open_probe_url=fixture_transport
        from app.api.exchange_connections import router,production_user,get_db
        from app.core.auth import AuthenticatedUser
        from app.models import DataSourceConnection
        engine=create_engine('sqlite:///:memory:',connect_args={'check_same_thread':False},poolclass=StaticPool)
        DataSourceConnection.__table__.create(engine)
        app=FastAPI(title='Isolated exchange browser fixture')
        app.add_middleware(CORSMiddleware,allow_origins=['http://127.0.0.1:3003','http://localhost:3003'],allow_methods=['GET','POST','PATCH','DELETE'],allow_headers=['Content-Type'],allow_credentials=True)
        app.include_router(router)
        def fixture_db():
            with Session(engine) as session:yield session
        app.dependency_overrides[get_db]=fixture_db
        app.dependency_overrides[production_user]=lambda:AuthenticatedUser('browser-fixture','owner',['read','secrets:write'],True,True)
        @app.get('/health/status')
        def fixture_health():return {'status':'ok','service':'isolated-browser-fixture','fixture':True}
        uvicorn.run(app,host='127.0.0.1',port=8002,access_log=False)
