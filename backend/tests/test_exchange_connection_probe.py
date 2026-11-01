import json
from io import BytesIO
from urllib.error import HTTPError
from urllib.parse import urlparse, parse_qs
import hashlib, hmac
import pytest
from app.services.exchange_connection_probe import BinanceConnectionProbe, ExchangeProbeError, DANGEROUS_FLAGS

KEY='fixture_key_only'; SECRET='fixture_secret_only'
def replies(permission_overrides=None, account=None):
    permissions={flag:False for flag in DANGEROUS_FLAGS};permissions['enableReading']=True;permissions.update(permission_overrides or {})
    calls=[]
    def transport(request,timeout):
        calls.append(request)
        path=urlparse(request.full_url).path
        assert request.get_method()=='GET'
        if path=='/api/v3/time':return BytesIO(json.dumps({'serverTime':1234567890000}).encode())
        query=urlparse(request.full_url).query
        unsigned,signature=query.rsplit('&signature=',1)
        assert signature==hmac.new(SECRET.encode(),unsigned.encode(),hashlib.sha256).hexdigest()
        assert request.headers['X-mbx-apikey']==KEY
        if 'apiRestrictions' in path:return BytesIO(json.dumps(permissions).encode())
        return BytesIO(json.dumps(account or {'canTrade':True,'balances':[{'asset':'BTC','free':'0.00000001','locked':'0'}]}).encode())
    return transport,calls

def test_real_signed_read_path_and_no_secret_return():
    transport,calls=replies();result=BinanceConnectionProbe(transport).verify(KEY,SECRET)
    assert len(calls)==4 and result['status']=='verified_readonly'
    assert result['balances'][0]['free']=='1E-8'
    assert KEY not in json.dumps(result) and SECRET not in json.dumps(result)
    assert result['credentials_persisted'] is False

@pytest.mark.parametrize('flags',[{'enableWithdrawals':True},{'enableSpotAndMarginTrading':True},{'enableFutures':None},{'enableReading':False},{'enableInternalTransfer':True}])
def test_reject_permissions_before_account_read(flags):
    transport,calls=replies(flags)
    with pytest.raises(ExchangeProbeError):BinanceConnectionProbe(transport).verify(KEY,SECRET)
    assert len(calls)==2

def test_reject_bad_balances():
    transport,_=replies(account={'balances':[{'asset':'BTC','free':'NaN','locked':'0'}]})
    with pytest.raises(ExchangeProbeError):BinanceConnectionProbe(transport).verify(KEY,SECRET)

def test_redacts_http_exception_url():
    def bad(request,timeout):raise HTTPError('https://x/?secret='+SECRET,401,KEY,None,None)
    with pytest.raises(ExchangeProbeError) as caught:BinanceConnectionProbe(bad).verify(KEY,SECRET)
    assert KEY not in str(caught.value) and SECRET not in str(caught.value)

def test_api_validation_does_not_echo_credentials():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.exchange_connections import router, production_user
    from app.core.auth import AuthenticatedUser
    app=FastAPI();app.include_router(router)
    app.dependency_overrides[production_user]=lambda:AuthenticatedUser('fixture','owner',['secrets:write'],True,True)
    client=TestClient(app)
    result=client.post('/exchange-connections/binance/probe',json={'api_key':KEY})
    assert result.status_code==422 and KEY not in result.text
    app.dependency_overrides[production_user]=lambda:AuthenticatedUser('fixture','viewer',[],True,True)
    assert client.post('/exchange-connections/binance/probe',json={}).status_code==403
