import hashlib,hmac,json
from io import BytesIO
from urllib.parse import urlparse
import pytest
from app.services.exchange_connection_probe import GateConnectionProbe,ExchangeProbeError
KEY='fixture_gate_key';SECRET='fixture_gate_secret'

def transport(key=KEY,perms=None,mode=1):
    calls=[]
    def send(req,timeout):
        path=urlparse(req.full_url).path;calls.append(path)
        assert req.get_method()=='GET' and req.full_url.startswith('https://api.gateio.ws/')
        if path.endswith('/time'):data={'server_time':1792800000000}
        else:
            headers={k.lower():v for k,v in req.headers.items()}
            prehash='\n'.join(['GET',path,'',hashlib.sha512(b'').hexdigest(),headers['timestamp']])
            assert headers['sign']==hmac.new(SECRET.encode(),prehash.encode(),hashlib.sha512).hexdigest()
            data=[{'key':key,'state':1,'mode':mode,'perms':perms if perms is not None else [{'name':'spot','read_only':True}]}] if path.endswith('/main_keys') else [{'currency':'BTC','available':'1','locked':'0.1'}]
        return BytesIO(json.dumps(data).encode())
    return send,calls

def test_gate_exact_identity_signature_and_balance():
    send,calls=transport();result=GateConnectionProbe(send).verify(KEY,SECRET)
    assert len(calls)==4 and result['balances'][0]['free']=='1'
    assert KEY not in json.dumps(result) and SECRET not in json.dumps(result)

@pytest.mark.parametrize('key',[KEY[:5]+'*****','different_key'])
def test_masked_or_other_key_is_not_a_permission_proof(key):
    send,calls=transport(key)
    with pytest.raises(ExchangeProbeError,match='key_permission_identity_unavailable'):GateConnectionProbe(send).verify(KEY,SECRET)
    assert len(calls)==2

@pytest.mark.parametrize('perms',[[{'name':'spot','read_only':False}],[{'name':'spot','read_only':True},{'name':'wallet','read_only':False}],[]])
def test_write_or_unknown_permissions_rejected(perms):
    send,calls=transport(perms=perms)
    with pytest.raises(ExchangeProbeError):GateConnectionProbe(send).verify(KEY,SECRET)
    assert len(calls)==2

def test_unified_mode_not_mislabelled_classic():
    send,_=transport(mode=2)
    with pytest.raises(ExchangeProbeError,match='unsupported_account_mode'):GateConnectionProbe(send).verify(KEY,SECRET)
