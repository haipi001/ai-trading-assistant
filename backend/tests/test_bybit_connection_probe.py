from io import BytesIO
import json,hashlib,hmac
from urllib.parse import urlparse
import pytest
from app.services.exchange_connection_probe import BybitConnectionProbe,ExchangeProbeError
KEY='fixture_bybit_key';SECRET='fixture_bybit_secret'

def transport(readonly=1,wallet=None,coins=None):
    calls=[]
    def request(req,timeout):
        url=urlparse(req.full_url);calls.append(url.path)
        assert req.get_method()=='GET' and url.hostname=='api.bybit.com'
        if url.path=='/v5/market/time':result={'timeNano':'1792800000000000000'}
        else:
            headers={k.lower():v for k,v in req.headers.items()}
            expected=hmac.new(SECRET.encode(),(headers['x-bapi-timestamp']+KEY+'5000'+url.query).encode(),hashlib.sha256).hexdigest()
            assert headers['x-bapi-sign']==expected
            if url.path=='/v5/user/query-api':result={'readOnly':readonly,'apiKey':KEY,'permissions':{'Wallet':wallet or [],'Withdraw':[]}}
            else:
                assert url.query=='accountType=UNIFIED'
                result={'list':[{'accountType':'UNIFIED','coin':coins if coins is not None else [{'coin':'BTC','walletBalance':'1.25','equity':'1.2','locked':'0.1'}]}]}
        return BytesIO(json.dumps({'retCode':0,'result':result}).encode())
    return request,calls

def test_bybit_signature_and_no_fabricated_available_balance():
    request,calls=transport();result=BybitConnectionProbe(request).verify(KEY,SECRET)
    assert len(calls)==4 and result['balances'][0]['free'] is None
    assert result['balances'][0]['wallet_balance']=='1.25' and result['balances'][0]['equity']=='1.2'
    assert KEY not in json.dumps(result) and SECRET not in json.dumps(result)

@pytest.mark.parametrize('flag',[0,True,'1',None])
def test_readonly_must_be_explicit_integer(flag):
    request,calls=transport(readonly=flag)
    with pytest.raises(ExchangeProbeError):BybitConnectionProbe(request).verify(KEY,SECRET)
    assert len(calls)==2

@pytest.mark.parametrize('wallet',[['AccountTransfer'],['Withdraw'],['unknown']])
def test_no_wallet_write_permissions(wallet):
    request,calls=transport(wallet=wallet)
    with pytest.raises(ExchangeProbeError):BybitConnectionProbe(request).verify(KEY,SECRET)
    assert len(calls)==2

def test_invalid_wallet_balance_rejected():
    request,_=transport(coins=[{'coin':'BTC','walletBalance':'Infinity','equity':'1','locked':'0'}])
    with pytest.raises(ExchangeProbeError):BybitConnectionProbe(request).verify(KEY,SECRET)
