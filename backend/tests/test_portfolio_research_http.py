import json
import pytest
from test_onchain_history_http import database
from test_trade_permissions import managed_actor
from test_local_secrets_and_llm_credentials import isolated_store,owner,report_for
from test_research_portfolio_context import seed,ref
from app.services.human_control import HumanControlService
BASE='/production/human-control/llm/chat/'
@pytest.mark.parametrize('market',['stocks','cex'])
@pytest.mark.parametrize('failure',[False,True])
def test_owned_portfolio_prepare_chat_and_restore_use_real_routes(client,managed_actor,isolated_store,monkeypatch,failure,market):
    managed_actor('owner')
    with database() as db:
        seed(db,user='tenant-trade-test',kind='brokerage' if market=='stocks' else 'exchange');seed(db,user='foreign',account='foreign')
        HumanControlService(db).set_llm_credentials(actor=owner('tenant-trade-test'),payload={'provider':'deepseek','model':'controlled-no-network','api_key':'fixture-portfolio-only','monthly_budget_usd':10,'per_request_budget_usd':1,'approved_for_research':True})
    headers={'Authorization':'Bearer controlled','X-AI-Trading-User':'foreign'}
    assert client.post(BASE+'portfolio-context/prepare',json=ref(market=market)).status_code==401
    assert client.post(BASE+'portfolio-context/prepare',json=ref('foreign'),headers=headers).status_code==404
    assert client.post(BASE+'portfolio-context/prepare',json={**ref(market=market),'balances':[1]},headers=headers).status_code==422
    prepared=client.post(BASE+'portfolio-context/prepare',json=ref(market=market),headers=headers)
    assert prepared.status_code==200,prepared.text
    assert prepared.headers['cache-control']=='no-store'
    class Provider:
        def generate_report(self,**kwargs):
            if failure:raise RuntimeError('controlled provider failure')
            value=report_for(kwargs);value['summary']='Account record [H1] and quantity [H2].';value['evidence']={'portfolio_citation_ids':['H1','H2']};return json.dumps(value)
    monkeypatch.setattr(HumanControlService,'_provider_from_llm_config',lambda *_:Provider())
    result=client.post(BASE.rstrip('/'),json={'question':'Explain application ledger only','page':'assets','portfolio_context':prepared.json()['reference']},headers=headers)
    assert result.status_code==200,result.text
    payload=result.json();assert payload['status']==('failed' if failure else 'ok'),payload
    listing=client.get(BASE+'portfolio-contexts',params={'account_id':'account-a','market':market},headers=headers)
    assert listing.status_code==200 and listing.json()['items'][0]['snapshot_id']==payload['portfolio_context_snapshot_id']
    detail=client.get(BASE+'portfolio-context/'+payload['portfolio_context_snapshot_id'],headers=headers)
    assert detail.status_code==200 and detail.json()['execution_available'] is False
    assert detail.json()['provided_portfolio']==prepared.json()['provided_portfolio']
    if failure:assert detail.json()['validated_reply'] is None
    else:assert detail.json()['validated_reply']['cited_portfolio_ids']==['H1','H2']
    assert client.get(BASE+'portfolio-contexts',params={'account_id':'foreign','market':market},headers=headers).json()['items']==[]
    managed_actor('viewer')
    assert client.post(BASE+'portfolio-context/prepare',json=ref(market=market),headers=headers).status_code==200
    assert client.post(BASE.rstrip('/'),json={'question':'No model permission'},headers=headers).status_code==403
