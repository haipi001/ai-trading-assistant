import json
import os
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app.db.base import Base
from app.models import LocalUserConfig, AuditLog
from app.core import local_secrets
from app.services import subscriptions as module
from app.services.subscriptions import SubscriptionService, validate_endpoint

@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(local_secrets,'store_path',lambda:tmp_path/'secrets.env')
    engine=create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    with Session(engine) as session: yield session
    for key in list(os.environ):
        if key.startswith('SUB_'): os.environ.pop(key,None)


def config(**kw):
    return dict(name='Fixture RSS',url='https://example.com/feed',kind='rss',auth='bearer',header_name='Authorization',params={'symbol':'BTC'},enabled=True,refresh_seconds=300,**kw)


def test_user_scoping_redaction_retain_clear_and_test(db, monkeypatch):
    a=SubscriptionService(db,'a'); b=SubscriptionService(db,'b')
    value=a.save('fixture',config(api_key='fixture-key'))
    assert value['key_configured'] and not b.list()
    assert 'fixture-key' not in json.dumps([r.value_json for r in db.scalars(select(LocalUserConfig))])
    a.save('fixture',config())
    assert a.list()[0]['key_configured']
    monkeypatch.setattr(module,'fetch_subscription',lambda config,secret: {'items':2,'format':'rss'} if secret=='fixture-key' else None)
    assert a.test('fixture')['result']['items']==2
    assert len(list(db.scalars(select(AuditLog))))==3
    a.save('fixture',config(clear_key=True))
    assert not a.list()[0]['key_configured']
    with pytest.raises(ValueError): b.test('fixture')

@pytest.mark.parametrize('url',['http://example.com/rss','https://user:pass@example.com/rss','https://example.com/rss?key=x','https://example.com:8443/rss','https://example.com/#x'])
def test_invalid_endpoints(url):
    with pytest.raises(ValueError): validate_endpoint(url)


def test_private_dns_rejected_without_connection(monkeypatch):
    monkeypatch.setattr(module.socket,'getaddrinfo',lambda *a,**k:[(2,1,6,'',('127.0.0.1',443))])
    with pytest.raises(ValueError,match='公网'): module.fetch_subscription(config(),None)


def test_failed_read_redacts_error(db, monkeypatch):
    service=SubscriptionService(db,'a');service.save('fixture',config(api_key='fixture-key'))
    def fail(*a):raise RuntimeError('fixture-key sensitive upstream error')
    monkeypatch.setattr(module,'fetch_subscription',fail)
    value=service.test('fixture')
    assert value['status']=='error' and 'fixture-key' not in json.dumps(value)


def test_invalid_params_never_write_secret(db):
    service=SubscriptionService(db,'a')
    payload=config(api_key='fixture-key');payload['params']={'apiKey':'sensitive'}
    with pytest.raises(ValueError):service.save('fixture',payload)
    assert not service.list() and not os.environ.get(service.secret_name('fixture'))


def test_routes_require_permissions_and_never_return_key(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy.pool import StaticPool
    from types import SimpleNamespace
    from app.api.subscriptions import router
    from app.api.production import production_user
    from app.db.session import get_db
    monkeypatch.setattr(local_secrets,'store_path',lambda:tmp_path/'route-secrets.env')
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    app=FastAPI();app.include_router(router)
    actor=SimpleNamespace(user_id='route-user',permissions=['readiness:read'])
    app.dependency_overrides[production_user]=lambda:actor
    def session():
        with Session(engine) as db:yield db
    app.dependency_overrides[get_db]=session
    client=TestClient(app)
    assert client.put('/subscriptions/demo',json=config(api_key='fixture-route-key')).status_code==403
    actor.permissions.append('secrets:write')
    response=client.put('/subscriptions/demo',json=config(api_key='fixture-route-key'))
    assert response.status_code==200 and response.json()['key_configured']
    assert 'fixture-route-key' not in response.text
    assert client.get('/subscriptions').headers['cache-control']=='no-store'
    actor.user_id='other'
    assert client.get('/subscriptions').json()==[]
    assert client.post('/subscriptions/demo/test').status_code==422
    os.environ.pop(SubscriptionService(None,'route-user').secret_name('demo'),None)


def test_rss_feed_preserves_old_data_on_failure_and_throttles(db,monkeypatch):
    service=SubscriptionService(db,'cache-user')
    service.save('rss',config())
    calls=[]
    def fetch(value,secret):
        calls.append(value['id'])
        return {'items':1,'format':'rss','articles':[{'title':'Fixture','url':'https://example.com/story'}]}
    monkeypatch.setattr(module,'fetch_subscription',fetch)
    first=service.refresh('rss')
    assert first['fetched_at'] and len(first['result']['articles'])==1
    assert service.refresh('rss')['fetched_at']==first['fetched_at'] and len(calls)==1
    assert service.feed('news')[0]['result']['articles']
    assert service.feed('quotes')==[]
    assert 'articles' not in service.list()[0]['result']
    row=service.row('rss');row.value_json={**row.value_json,'checked_at':'2000-01-01T00:00:00+00:00'};db.commit()
    def fail(*a):raise ValueError('secret source body')
    monkeypatch.setattr(module,'fetch_subscription',fail)
    failed=service.refresh('rss')
    assert failed['status']=='error' and failed['result']['articles']==first['result']['articles']
    assert failed['fetched_at']==first['fetched_at'] and 'secret source body' not in json.dumps(failed)
    service.save('rss',{**config(),'enabled':False})
    assert service.feed('news')==[]


def test_json_field_mapping_and_invalid_prices():
    from app.services.subscription_data import normalize
    value={**config(),'id':'price','kind':'json','mapping':{'root':'data','price':'last','symbol':'ticker','timestamp':'ts','timestamp_unit':'ms','currency':'USDT','venue':'fixture'}}
    result=normalize(value,{'data':[{'ticker':'BTCUSDT','last':'123.45','ts':1794528000000},{'ticker':'BAD','last':'NaN'},{'ticker':'BAD2','last':True}]})
    assert result['items']==1 and result['quotes'][0]['price']==123.45
    assert result['quotes'][0]['currency']=='USDT' and result['quotes'][0]['timestamp']
    assert result['quotes'][0]['change'] is None
    with pytest.raises(ValueError):normalize(value,{'unexpected':[]})


def test_rss_normalization_strips_unsafe_links_and_keeps_kind():
    from app.services.subscription_data import normalize
    value={**config(),'id':'rss','news_kind':'flash'}
    result=normalize(value,{'articles':[{'title':'Actual fixture','url':'https://example.com/news','publishedAt':'2026-11-13T01:00:00Z'},{'title':'Unsafe','url':'javascript:alert(1)'}]})
    assert result['items']==1 and result['articles'][0]['kind']=='flash'
    assert result['articles'][0]['publisher']=='Fixture RSS'


def test_config_change_during_fetch_cannot_publish_old_response(db,monkeypatch):
    service=SubscriptionService(db,'race-user');service.save('rss',config())
    def fetch(*a):
        service.save('rss',{**config(),'url':'https://example.com/new-feed'})
        return {'items':1,'format':'rss','articles':[{'title':'Old'}]}
    monkeypatch.setattr(module,'fetch_subscription',fetch)
    result=service.refresh('rss')
    assert result['url']=='https://example.com/new-feed' and result.get('result') is None


def test_refresh_endpoint_is_read_only_and_user_scoped(tmp_path,monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy.pool import StaticPool
    from types import SimpleNamespace
    from app.api.subscriptions import router
    from app.api.production import production_user
    from app.db.session import get_db
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    app=FastAPI();app.include_router(router)
    actor=SimpleNamespace(user_id='reader',permissions=['readiness:read'])
    app.dependency_overrides[production_user]=lambda:actor
    def session():
        with Session(engine) as db:yield db
    app.dependency_overrides[get_db]=session
    with Session(engine) as db:SubscriptionService(db,'reader').save('public',{**config(),'auth':'none'})
    monkeypatch.setattr(module,'fetch_subscription',lambda *args:{'items':1,'format':'rss','articles':[{'title':'Fixture','url':'https://example.com/story'}]})
    client=TestClient(app)
    result=client.post('/subscriptions/public/refresh')
    assert result.status_code==200 and result.json()['result']['articles'][0]['title']=='Fixture'
    assert client.get('/subscriptions/feed/news').json()[0]['result']['items']==1
    assert client.get('/subscriptions/feed/quotes').json()==[]
    actor.user_id='other'
    assert client.get('/subscriptions/feed/news').json()==[]
    assert client.post('/subscriptions/public/refresh').status_code==422
    actor.permissions=[]
    assert client.post('/subscriptions/public/refresh').status_code==403
