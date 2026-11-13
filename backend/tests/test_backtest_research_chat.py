import json
import pytest
from test_local_secrets_and_llm_credentials import isolated_store,report_for
from test_paper_review_research_chat import configure
from test_backtests import create_playbook
from app.services.human_control import HumanControlService

@pytest.mark.parametrize('valid',[True,False])
def test_backtest_chat_http_uses_frozen_source_and_validated_reply(client,isolated_store,monkeypatch,valid):
    configure();playbook=create_playbook(client)
    run=client.post('/backtest-runs',json={'strategy_playbook_id':playbook['id'],'name':'HTTP review','date_from':'2026-01-01','date_to':'2026-01-08','initial_capital':100,'parameters_json':{}}).json()
    packet=client.post(f"/backtest-runs/{run['id']}/research-material").json()
    reference={'snapshot_id':packet['snapshot_id'],'backtest_run_id':run['id'],'content_hash':packet['material']['content_hash']}
    calls=[]
    class Provider:
        def generate_report(self,**kwargs):
            calls.append(kwargs)
            assert kwargs['input_facts']['backtest_context']['backtest_run_id']==run['id']
            report=report_for(kwargs);report['summary']='Historical simulation [BT1]' if valid else 'No source cited'
            report['evidence']={'backtest_citation_ids':['BT1'] if valid else []}
            return json.dumps(report)
    monkeypatch.setattr(HumanControlService,'_provider_from_llm_config',lambda *_:Provider())
    response=client.post('/production/human-control/llm/chat',json={'question':'Review simulation','backtest_context':reference})
    assert response.status_code==200,response.text
    result=response.json();assert result['status']==('ok' if valid else 'failed'),result
    assert len(calls)==1 and result['execution_available'] is False
    assert result['context_scope']=='owned_frozen_backtest_material'
    path=f"/backtest-runs/{run['id']}/research-replies/{result['backtest_context_snapshot_id']}"
    listing=client.get(f"/backtest-runs/{run['id']}/research-replies")
    assert listing.status_code==200 and listing.headers['cache-control']=='no-store'
    assert listing.json()['items'][0]['snapshot_id']==result['backtest_context_snapshot_id']
    assert listing.json()['items'][0]['reply_status']==result['status']
    assert client.get(f"/backtest-runs/{run['id']}/research-replies",headers={'X-AI-Trading-User':'foreign'}).status_code==404
    saved=client.get(path)
    assert saved.status_code==200 and saved.headers['cache-control']=='no-store'
    assert saved.json()['reply_status']==result['status']
    assert (saved.json()['validated_reply'] is not None)==valid
    assert client.get(path,headers={'X-AI-Trading-User':'foreign'}).status_code==404
    if valid:
        from test_server_account_risk import edit_db
        from app.models import DataSnapshot
        def corrupt_reply(db):
            row=db.get(DataSnapshot,result['backtest_context_snapshot_id'])
            row.metadata_json={**row.metadata_json,'validated_reply':{**row.metadata_json['validated_reply'],'summary':'No source marker'}}
        edit_db(corrupt_reply)
        assert client.get(path).status_code==409



def test_backtest_chat_invalid_references_never_construct_provider(client,isolated_store,monkeypatch):
    configure();playbook=create_playbook(client)
    run=client.post('/backtest-runs',json={'strategy_playbook_id':playbook['id'],'name':'No provider','date_from':'2026-01-01','date_to':'2026-01-08','initial_capital':100,'parameters_json':{}}).json()
    packet=client.post(f"/backtest-runs/{run['id']}/research-material").json()
    reference={'snapshot_id':packet['snapshot_id'],'backtest_run_id':run['id'],'content_hash':packet['material']['content_hash']}
    calls=[]
    def forbidden(*args):
        calls.append(True)
        raise AssertionError('provider must not be constructed')
    monkeypatch.setattr(HumanControlService,'_provider_from_llm_config',forbidden)
    for patch in [{'content_hash':'0'*64},{'backtest_run_id':'other'},{'snapshot_id':'foreign-or-missing'},{'material':packet['material']}]:
        response=client.post('/production/human-control/llm/chat',json={'question':'Review','backtest_context':{**reference,**patch}})
        assert response.status_code==200,response.text
        assert response.json()['status']=='blocked'
    response=client.post('/production/human-control/llm/chat',json={'question':'Review','backtest_context':reference,'strategy_context':{}})
    assert response.json()['reason']=='ai_backtest_incompatible'
    assert calls==[]

    from test_server_account_risk import edit_db
    from app.models import DataSnapshot
    edit_db(lambda db:setattr(db.get(DataSnapshot,packet['snapshot_id']),'user_id','foreign'))
    response=client.post('/production/human-control/llm/chat',json={'question':'Review','backtest_context':reference})
    assert response.json()['status']=='blocked'
    assert calls==[]


def test_backtest_expiring_during_preflight_is_rejected_before_provider(client,isolated_store,monkeypatch):
    from datetime import datetime,timedelta
    import app.services.backtest_research_material as materials
    configure();playbook=create_playbook(client)
    run=client.post('/backtest-runs',json={'strategy_playbook_id':playbook['id'],'name':'Preflight expiry','date_from':'2026-01-01','date_to':'2026-01-08','initial_capital':100,'parameters_json':{}}).json()
    packet=client.post(f"/backtest-runs/{run['id']}/research-material").json()
    reference={'snapshot_id':packet['snapshot_id'],'backtest_run_id':run['id'],'content_hash':packet['material']['content_hash']}
    original=HumanControlService.llm_preflight_dry_run
    def preflight(self,**kwargs):
        result=original(self,**kwargs)
        monkeypatch.setattr(materials,'utc_now',lambda:datetime.fromisoformat(packet['material']['captured_at'])+timedelta(seconds=601))
        return result
    calls=[]
    monkeypatch.setattr(HumanControlService,'llm_preflight_dry_run',preflight)
    monkeypatch.setattr(HumanControlService,'_provider_from_llm_config',lambda *_:calls.append(True))
    response=client.post('/production/human-control/llm/chat',json={'question':'Review','backtest_context':reference}).json()
    assert response['status']=='blocked' and response['reason']=='ai_backtest_stale'
    assert calls==[]
