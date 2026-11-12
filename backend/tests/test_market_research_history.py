import json
import pytest
from test_local_secrets_and_llm_credentials import db,isolated_store,owner,configure_chat,report_for,seed_chat_news
from test_research_market_context import packet
from app.models import DataSnapshot
from app.services.human_control import HumanControlService,HumanControlError

@pytest.mark.parametrize('failure',[False,True])
def test_market_history_freezes_reply_or_failure_and_preserves_news_sources(db,isolated_store,monkeypatch,failure):
    seed_chat_news(db);service=HumanControlService(db);configure_chat(service)
    class Provider:
        def generate_report(self,**kwargs):
            if failure:raise RuntimeError('controlled provider failure')
            reply=report_for(kwargs);reply['summary']='Source claim [N1] and raw sample [M1].'
            reply['evidence']={'news_citation_ids':['N1'],'market_citation_ids':['M1']}
            return json.dumps(reply)
    monkeypatch.setattr(service,'_provider_from_llm_config',lambda config:Provider())
    response=service.research_chat(actor=owner(),payload={'question':'Review only','page':'market','symbol':'ETH','include_news':True,'market_context':packet()})
    listing=service.research_market_history(actor=owner(),symbol='ETH',market_type='spot')
    assert len(listing['items'])==1 and listing['execution_available'] is False
    row=listing['items'][0];assert row['reply_status']==('failed' if failure else 'ok')
    assert row['snapshot_id']==response['market_context_snapshot_id']
    artifact=service.research_market_snapshot(actor=owner(),snapshot_id=row['snapshot_id'])
    assert artifact['provided_market']['bars']==response['provided_market']['bars']
    assert artifact['workspace_labels']=={'page':'market','symbol':'ETH'}
    assert artifact['question']=='Review only' and artifact['response_style']=='brief'
    assert artifact['provider_mode']=='bring_your_own'
    assert artifact['provided_news']['articles'][0]['id']=='N1'
    if failure:assert artifact['validated_reply'] is None
    else:assert artifact['validated_reply']['summary']==response['summary']
    assert service.research_market_history(actor=owner('other'),symbol='ETH')['items']==[]
    assert service.research_market_history(actor=owner(),symbol='AAPL')['items']==[]
    assert service.research_market_history(actor=owner(),symbol='ETH',market_type='stock')['items']==[]
    with pytest.raises(HumanControlError):service.research_market_snapshot(actor=owner('other'),snapshot_id=row['snapshot_id'])


def test_market_history_bounds_results_and_keeps_legacy_unknown_replies(db):
    for _ in range(23):
        db.add(DataSnapshot(user_id='owner-user',snapshot_type='research_chat_market_context',data_json={**packet(),'kind':'csv'},metadata_json={}))
    db.commit();service=HumanControlService(db)
    value=service.research_market_history(actor=owner())
    assert len(value['items'])==20 and value['has_more'] is True
    artifact=service.research_market_snapshot(actor=owner(),snapshot_id=value['items'][0]['snapshot_id'])
    assert artifact['reply_status'] is None and artifact['validated_reply'] is None
    for symbol,market_type in [('ETH/USDT','spot'),('ETH','onchain')]:
        with pytest.raises(HumanControlError):service.research_market_history(actor=owner(),symbol=symbol,market_type=market_type)


def test_market_history_never_resolves_foreign_news_as_owned_evidence(db):
    foreign=DataSnapshot(user_id='other',snapshot_type='research_chat_news_context',data_json={},metadata_json={})
    db.add(foreign);db.flush()
    market=DataSnapshot(user_id='owner-user',snapshot_type='research_chat_market_context',data_json=packet(),metadata_json={'news_context_snapshot_id':foreign.id})
    db.add(market);db.commit()
    with pytest.raises(HumanControlError,match='market_context_incomplete'):
        HumanControlService(db).research_market_snapshot(actor=owner(),snapshot_id=market.id)
