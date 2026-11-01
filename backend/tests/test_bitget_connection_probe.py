import base64,hashlib,hmac,json
from io import BytesIO
from urllib.parse import urlparse
import pytest
from app.services.exchange_connection_probe import BitgetConnectionProbe,ExchangeProbeError
KEY='fixture_bitget_key';SECRET='fixture_bitget_secret';PASS='fixture_passphrase'

def transport(perm='read-only',permissions=None,assets=None):
    calls=[]
    def send(req,timeout):
        path=urlparse(req.full_url).path;calls.append(path)
        assert req.get_method()=='GET' and req.full_url.startswith('https://api.bitget.com/')
        if path=='/api/v2/public/time':data={'serverTime':'1792800000000'}
        else:
            headers={k.lower():v for k,v in req.headers.items()}
            expected=base64.b64encode(hmac.new(SECRET.encode(),(headers['access-timestamp']+'GET'+path).encode(),hashlib.sha256).digest()).decode()
            assert headers['access-sign']==expected and headers['access-key']==KEY and headers['access-passphrase']==PASS
            data={'permType':perm,'permissions':permissions if permissions is not None else ['uta_mgt']} if path.endswith('/info') else {'assets':assets if assets is not None else [{'coin':'USDT','available':'3','locked':'1','balance':'4','equity':'4.2'}]}
        return BytesIO(json.dumps({'code':'00000','data':data}).encode())
    return send,calls

def test_signed_unified_account_assets():
    send,calls=transport();result=BitgetConnectionProbe(send).verify(KEY,SECRET,PASS)
    assert len(calls)==4 and result['balances'][0]=={'asset':'USDT','free':'3','locked':'1','wallet_balance':'4','equity':'4.2'}
    for value in (KEY,SECRET,PASS):assert value not in json.dumps(result)

@pytest.mark.parametrize('perm,permissions',[('read-and-write',['uta_mgt']),('read-only',['withdraw']),('read-only',['unknown']),('',[])])
def test_readonly_flags_and_capabilities(perm,permissions):
    send,calls=transport(perm,permissions)
    with pytest.raises(ExchangeProbeError):BitgetConnectionProbe(send).verify(KEY,SECRET,PASS)
    assert len(calls)==2

def test_bad_amount_and_missing_passphrase():
    send,_=transport()
    with pytest.raises(ExchangeProbeError):BitgetConnectionProbe(send).verify(KEY,SECRET,'')
    send,_=transport(assets=[{'coin':'USDT','available':'NaN','locked':'0','balance':'0','equity':'0'}])
    with pytest.raises(ExchangeProbeError):BitgetConnectionProbe(send).verify(KEY,SECRET,PASS)
