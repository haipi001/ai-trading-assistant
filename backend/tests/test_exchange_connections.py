import json,os
import pytest
from sqlalchemy import create_engine,select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.models import DataSourceConnection
from app.core import local_secrets
from app.services.exchange_connections import ExchangeConnectionService
from app.services.exchange_connection_probe import ExchangeProbeError

class Probe:
    fail=False
    def verify(self,key,secret):
        if self.fail:raise ExchangeProbeError('key_ip_or_permissions_rejected')
        assert key=='fixture_key' and secret=='fixture_secret'
        return {'permissions':{'reading':True,'trading':False,'withdrawals':False,'transfers':False},'balances':[]}

@pytest.fixture()
def setup(tmp_path,monkeypatch):
    monkeypatch.setattr(local_secrets,'store_path',lambda:tmp_path/'test.env')
    engine=create_engine('sqlite:///:memory:',connect_args={'check_same_thread':False},poolclass=StaticPool);DataSourceConnection.__table__.create(engine)
    with Session(engine) as db:
        yield db,Probe(),tmp_path
    for key in list(os.environ):
        if key.startswith('USER_EXCHANGE_'):monkeypatch.delenv(key,raising=False)

def test_create_list_recheck_disable_and_no_inline_db_secret(setup):
    db,probe,path=setup;service=ExchangeConnectionService(db,'alice',probe)
    result=service.create('account','fixture_key','fixture_secret')
    assert result['status']=='verified_readonly' and len(service.list())==1
    row=db.scalar(select(DataSourceConnection))
    assert 'fixture_secret' not in json.dumps(row.config_json)
    assert 'fixture_key' not in json.dumps(result)
    assert (path/'test.env').stat().st_mode&0o777==0o600
    assert service.check(result['id'])['status']=='verified_readonly'
    assert ExchangeConnectionService(db,'bob',probe).list()==[]
    with pytest.raises(ExchangeProbeError):ExchangeConnectionService(db,'bob',probe).check(result['id'])
    assert service.disable(result['id'])['credentials_persisted'] is False
    assert 'fixture_secret' not in (path/'test.env').read_text()
    with pytest.raises(ExchangeProbeError):service.check(result['id'])

def test_bad_probe_never_persists_and_recheck_failure_clears_status(setup):
    db,probe,path=setup;service=ExchangeConnectionService(db,'alice',probe)
    probe.fail=True
    with pytest.raises(ExchangeProbeError):service.create('bad','fixture_key','fixture_secret')
    assert service.list()==[] and not (path/'test.env').exists()
    probe.fail=False;created=service.create('ok','fixture_key','fixture_secret');probe.fail=True
    with pytest.raises(ExchangeProbeError):service.check(created['id'])
    assert service.list()[0]['status']=='verification_failed'


def test_http_saved_connection_lifecycle(setup,monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.exchange_connections import router,production_user,get_db
    from app.core.auth import AuthenticatedUser
    from app.services.exchange_connection_probe import BinanceConnectionProbe
    db,probe,path=setup
    monkeypatch.setattr(BinanceConnectionProbe,'verify',lambda self,key,secret:probe.verify(key,secret))
    app=FastAPI();app.include_router(router)
    app.dependency_overrides[production_user]=lambda:AuthenticatedUser('alice','owner',['secrets:write'],True,True)
    app.dependency_overrides[get_db]=lambda:db
    client=TestClient(app)
    created=client.post('/exchange-connections/binance',json={'label':'fixture','api_key':'fixture_key','api_secret':'fixture_secret'})
    assert created.status_code==201 and 'fixture_secret' not in created.text and 'fixture_key' not in created.text
    identity=created.json()['id']
    assert client.get('/exchange-connections').json()[0]['id']==identity
    assert client.post(f'/exchange-connections/{identity}/check').status_code==200
    assert client.delete(f'/exchange-connections/{identity}').json()['status']=='disabled'
    assert client.post(f'/exchange-connections/{identity}/check').status_code==422
    missing=client.post('/exchange-connections/binance',json={'label':'bad','api_key':'fixture_key'})
    assert missing.status_code==422 and 'fixture_key' not in missing.text

def test_okx_credentials_are_reused_without_exposing_passphrase(setup):
    db,_,path=setup
    class OkxProbe(Probe):
        def verify(self,key,secret,passphrase):
            assert passphrase=='fixture_passphrase'
            return super().verify(key,secret)
    service=ExchangeConnectionService(db,'alice',OkxProbe())
    created=service.create('okx','fixture_key','fixture_secret','okx','fixture_passphrase')
    assert created['exchange']=='okx'
    assert 'fixture_passphrase' not in json.dumps(created)
    assert service.check(created['id'])['status']=='verified_readonly'
    service.disable(created['id'])
    assert 'fixture_passphrase' not in (path/'test.env').read_text()

def test_bybit_stored_connection_selects_provider_and_scope(setup):
    db,probe,path=setup
    class BybitProbe(Probe):
        def verify(self,key,secret):
            return {**super().verify(key,secret),'balance_scope':'unified_account'}
    service=ExchangeConnectionService(db,'alice',BybitProbe())
    created=service.create('bybit','fixture_key','fixture_secret','bybit')
    assert created['exchange']=='bybit' and created['balance_scope']=='unified_account'
    assert service.check(created['id'])['exchange']=='bybit'
    service.disable(created['id'])

def test_bitget_passphrase_connection_lifecycle(setup):
    db,_,path=setup
    class BitgetProbe(Probe):
        def verify(self,key,secret,passphrase):
            assert passphrase=='fixture_passphrase'
            return {**super().verify(key,secret),'balance_scope':'bitget_unified_account'}
    service=ExchangeConnectionService(db,'alice',BitgetProbe())
    created=service.create('bitget','fixture_key','fixture_secret','bitget','fixture_passphrase')
    assert created['exchange']=='bitget' and created['balance_scope']=='bitget_unified_account'
    assert service.check(created['id'])['status']=='verified_readonly'
    assert service.disable(created['id'])['credentials_persisted'] is False

def test_gate_connection_lifecycle_and_scope(setup):
    db,_,path=setup
    class GateProbe(Probe):
        def verify(self,key,secret):
            return {**super().verify(key,secret),'balance_scope':'classic_spot_main_account'}
    service=ExchangeConnectionService(db,'alice',GateProbe())
    created=service.create('gate','fixture_key','fixture_secret','gate')
    assert created['exchange']=='gate' and created['balance_scope']=='classic_spot_main_account'
    assert service.check(created['id'])['status']=='verified_readonly'
    assert service.disable(created['id'])['credentials_persisted'] is False


def test_rename_keeps_credentials_and_verification_and_is_owner_bound(setup):
    db,probe,path=setup;service=ExchangeConnectionService(db,'alice',probe)
    created=service.create('first','fixture_key','fixture_secret')
    contents=(path/'test.env').read_bytes()
    probe.fail=True  # Rename must never contact the exchange.
    renamed=service.rename(created['id'],'  研究账户  ')
    assert renamed['label']=='研究账户'
    assert renamed['id']==created['id'] and renamed['checked_at']==created['checked_at']
    assert renamed['status']==created['status'] and renamed['permissions']==created['permissions']
    assert (path/'test.env').read_bytes()==contents
    with pytest.raises(ExchangeProbeError,match='connection_not_found'):
        ExchangeConnectionService(db,'bob',probe).rename(created['id'],'other')
    for label in ['', ' '*4, 'x'*81, 'bad\nname', 'bad\x7fname', 123, None]:
        with pytest.raises(ExchangeProbeError,match='invalid_connection_label'):service.rename(created['id'],label)
    assert service.list()[0]['label']=='研究账户'
    service.disable(created['id'])
    assert service.rename(created['id'],'已停用账户')['status']=='disabled'
    assert service.list()[0]['credentials_persisted'] is False


def test_http_rename_rejects_extra_fields_and_requires_owner_permission(setup,monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.exchange_connections import router,production_user,get_db
    from app.core.auth import AuthenticatedUser
    db,probe,path=setup
    created=ExchangeConnectionService(db,'alice',probe).create('first','fixture_key','fixture_secret')
    app=FastAPI();app.include_router(router)
    actor=[AuthenticatedUser('alice','owner',['secrets:write'],True,True)]
    app.dependency_overrides[production_user]=lambda:actor[0]
    app.dependency_overrides[get_db]=lambda:db
    client=TestClient(app);url=f"/exchange-connections/{created['id']}"
    response=client.patch(url,json={'label':'新名称'})
    assert response.status_code==200 and response.json()['label']=='新名称'
    assert response.headers['Cache-Control']=='no-store'
    for payload in [{'label':'x','api_key':'fixture_key'}, {'label':False}, {}, [], {'label':'x'*1025}]:
        response=client.patch(url,json=payload)
        assert response.status_code==422 and 'fixture_key' not in response.text
    actor[0]=AuthenticatedUser('bob','owner',['secrets:write'],True,True)
    assert client.patch(url,json={'label':'other'}).status_code==404
    actor[0]=AuthenticatedUser('alice','viewer',[],True,True)
    assert client.patch(url,json={'label':'other'}).status_code==403
    assert ExchangeConnectionService(db,'alice',probe).list()[0]['label']=='新名称'
