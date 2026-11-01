import base64,hashlib,hmac,json
from io import BytesIO
from urllib.parse import urlparse
import pytest
from app.services.exchange_connection_probe import OkxConnectionProbe,ExchangeProbeError
KEY='fixture_okx_key';SECRET='fixture_okx_secret';PASS='fixture_passphrase'

def replies(perm='read_only',details=None):
    calls=[]
    def transport(request,timeout):
        path=urlparse(request.full_url).path;calls.append(path)
        assert request.get_method()=='GET' and request.full_url.startswith('https://www.okx.com/')
        if path=='/api/v5/public/time':data=[{'ts':'1792800000000'}]
        else:
            headers={k.lower():v for k,v in request.headers.items()}
            assert headers['ok-access-key']==KEY and headers['ok-access-passphrase']==PASS
            expected=base64.b64encode(hmac.new(SECRET.encode(),(headers['ok-access-timestamp']+'GET'+path).encode(),hashlib.sha256).digest()).decode()
            assert expected==headers['ok-access-sign']
            data=[{'perm':perm}] if path.endswith('/config') else [{'details':details if details is not None else [{'ccy':'BTC','availBal':'0.25','frozenBal':'0.1'}]}]
        return BytesIO(json.dumps({'code':'0','data':data}).encode())
    return transport,calls

def test_okx_signature_and_balances():
    transport,calls=replies();value=OkxConnectionProbe(transport).verify(KEY,SECRET,PASS)
    assert len(calls)==4 and value['balances']==[{'asset':'BTC','free':'0.25','locked':'0.1'}]
    assert value['status']=='verified_readonly'
    for secret in (KEY,SECRET,PASS):assert secret not in json.dumps(value)

@pytest.mark.parametrize('perm',['read_only,trade','read_only,withdraw','read_only,unknown','','trade'])
def test_only_explicit_readonly_is_accepted(perm):
    transport,calls=replies(perm)
    with pytest.raises(ExchangeProbeError):OkxConnectionProbe(transport).verify(KEY,SECRET,PASS)
    assert len(calls)==2

def test_missing_passphrase_and_invalid_amount():
    transport,_=replies()
    with pytest.raises(ExchangeProbeError):OkxConnectionProbe(transport).verify(KEY,SECRET,'')
    transport,_=replies(details=[{'ccy':'BTC','availBal':'NaN','frozenBal':'0'}])
    with pytest.raises(ExchangeProbeError):OkxConnectionProbe(transport).verify(KEY,SECRET,PASS)
