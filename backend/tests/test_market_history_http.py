from test_onchain_history_http import database
from test_trade_permissions import managed_actor
from app.models import DataSnapshot
BASE='/production/human-control/llm/chat/'
def test_market_history_routes_isolate_verified_users_and_reject_invalid_filters(client,managed_actor):
    managed_actor('owner')
    with database() as db:
        def row(user):return DataSnapshot(user_id=user,snapshot_type='research_chat_market_context',data_json={'symbol':'ETH','venue':'public','timeframe':'1m','market_type':'spot','quote_currency':'USDT','kind':'csv'},metadata_json={'reply_status':'failed','validated_reply':None})
        own=row('tenant-trade-test');foreign=row('foreign');db.add_all([own,foreign]);db.commit();own_id=own.id;foreign_id=foreign.id
    assert client.get(BASE+'market-contexts').status_code==401
    headers={'Authorization':'Bearer fixture','X-AI-Trading-User':'foreign'}
    response=client.get(BASE+'market-contexts',params={'symbol':'ETH','market_type':'spot'},headers=headers)
    assert response.status_code==200,response.text
    assert response.headers['cache-control']=='no-store'
    assert [item['snapshot_id'] for item in response.json()['items']]==[own_id]
    assert response.json()['execution_available'] is False
    assert client.get(BASE+'market-context/'+foreign_id,headers=headers).status_code==404
    detail=client.get(BASE+'market-context/'+own_id,headers=headers)
    assert detail.status_code==200 and detail.json()['validated_reply'] is None
    assert client.get(BASE+'market-contexts',params={'market_type':'stock'},headers=headers).json()['items']==[]
    for params in [{'symbol':'ETH/USDT'},{'market_type':'onchain'},{'symbol':'x'*25}]:
        assert client.get(BASE+'market-contexts',params=params,headers=headers).status_code==422

import json
import pytest
from test_local_secrets_and_llm_credentials import isolated_store,owner,report_for
from test_research_market_context import packet
from app.services.human_control import HumanControlService

@pytest.mark.parametrize('market_type',['spot','stock'])
@pytest.mark.parametrize('failure',[False,True])
def test_actual_chat_route_saves_recoverable_market_artifacts(client,managed_actor,isolated_store,monkeypatch,market_type,failure):
    managed_actor('owner')
    with database() as db:
        HumanControlService(db).set_llm_credentials(actor=owner('tenant-trade-test'),payload={'provider':'deepseek','model':'controlled-test-no-network','api_key':'fixture-local-only','monthly_budget_usd':10,'per_request_budget_usd':1,'approved_for_research':True})
    class Provider:
        def generate_report(self,**kwargs):
            if failure:raise RuntimeError('controlled model failure')
            reply=report_for(kwargs);reply['summary']='Controlled historical sample [M1].'
            reply['evidence']={'market_citation_ids':['M1']}
            return json.dumps(reply)
    monkeypatch.setattr(HumanControlService,'_provider_from_llm_config',lambda *_:Provider())
    material=packet('csv')
    if market_type=='stock':material.update(market_type='stock',symbol='AAPL',quote_currency='USD',venue='NASDAQ')
    headers={'Authorization':'Bearer controlled-session'}
    response=client.post(BASE.rstrip('/'),json={'question':'Controlled historical sample','page':'market','symbol':material['symbol'],'market_context':material},headers=headers)
    assert response.status_code==200,response.text
    payload=response.json();assert payload['status']==('failed' if failure else 'ok'),payload
    identifier=payload['market_context_snapshot_id']
    listing=client.get(BASE+'market-contexts',params={'symbol':material['symbol'],'market_type':market_type},headers=headers)
    assert listing.status_code==200 and listing.json()['items'][0]['snapshot_id']==identifier
    detail=client.get(BASE+'market-context/'+identifier,headers=headers)
    assert detail.status_code==200,detail.text
    artifact=detail.json()
    assert artifact['provided_market']['bars']==material['bars']
    assert artifact['provided_market']['source_verified'] is False
    assert artifact['execution_available'] is False
    if failure:assert artifact['validated_reply'] is None
    else:assert artifact['validated_reply']['summary']==payload['summary']


def test_chat_status_reflects_research_permission_even_with_saved_configuration(client,managed_actor,isolated_store,monkeypatch):
    managed_actor('owner')
    with database() as db:
        HumanControlService(db).set_llm_credentials(actor=owner('tenant-trade-test'),payload={'provider':'deepseek','model':'controlled-test-no-network','api_key':'fixture-local-only','monthly_budget_usd':10,'per_request_budget_usd':1,'approved_for_research':True})
    headers={'Authorization':'Bearer controlled-session'}
    assert client.get(BASE+'status',headers=headers).json()['can_request'] is True
    def unexpected(*args,**kwargs):raise AssertionError('a viewer must not construct a model Provider')
    monkeypatch.setattr(HumanControlService,'_provider_from_llm_config',unexpected)
    managed_actor('viewer')
    status=client.get(BASE+'status',headers=headers)
    assert status.status_code==200
    assert status.json()['can_request'] is False
    assert status.json()['reason']=='ai_permission_required'
    assert status.json()['external_call_attempted'] is False
    assert client.post(BASE.rstrip('/'),json={'question':'No permission'},headers=headers).status_code==403
