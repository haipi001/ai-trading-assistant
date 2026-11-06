import pytest
from types import SimpleNamespace
from test_local_secrets_and_llm_credentials import db,isolated_store
from app.models import Wallet,DataSnapshot,AuditLog
from app.models.core import utc_now
from app.services.research_onchain_context import load_onchain_context,validate_onchain_citations,OnchainContextError

def test_reference_uses_owned_server_snapshot_and_rejects_browser_facts(db):
    address='0x'+'1'*40
    db.add(Wallet(id='w',user_id='owner',chain='ethereum',address=address))
    source=DataSnapshot(user_id='owner',snapshot_type='terminal_onchain_readonly',as_of=utc_now(),data_json={'wallet_id':'w','wallet_address':address,'chain_id':'1','contract_address':'','block_number':123,'balances':[{'symbol':'ETH','amount':'1.000000000000000001','decimals':18,'contract_address':None}]},metadata_json={'provider':'evm_rpc_readonly','signing_available':False,'execution_available':False,'usable_for_trading':False})
    db.add(source);db.flush()
    db.add(AuditLog(actor_type='user',actor_id='owner',action='terminal.onchain.read',entity_type='DataSnapshot',entity_id=source.id,payload_json={}));db.commit()
    ref={'schema_version':1,'snapshot_id':source.id,'wallet_id':'w','chain_id':'1','contract_address':'','context_version':8,'allowance_ids':[],'protocol_ids':[]}
    result=load_onchain_context(db,'owner',ref)
    assert result['entries'][0]['balances'][0]['amount']=='1.000000000000000001'
    assert result['context_version']==8
    for actor,value in [('foreign',ref),('owner',{**ref,'balances':[999]}),('owner',{**ref,'chain_id':'8453'})]:
        with pytest.raises(OnchainContextError):load_onchain_context(db,actor,value)

@pytest.mark.parametrize('ids,text', [(['W2'],'[W2]'),([], '[W1]'),(['W1'],'no citation')])
def test_citations_cannot_invent_or_silently_rebind_sources(ids,text):
    report=SimpleNamespace(evidence={'onchain_citation_ids':ids},summary=text,bullish_case='',bearish_case='',key_risks=[],limitations='',suggested_action='')
    with pytest.raises(OnchainContextError):validate_onchain_citations(report,{'entries':[{'id':'W1'}]})

def test_chat_freezes_material_and_reply(db,isolated_store,monkeypatch):
    import json
    from test_local_secrets_and_llm_credentials import owner,configure_chat,report_for
    from app.services.human_control import HumanControlService,HumanControlError
    ref=chat_reference(db)
    service=HumanControlService(db);configure_chat(service)
    class Provider:
        def generate_report(self,**kwargs):
            result=report_for(kwargs);result.update(summary='Observed balance [W1]',evidence={'onchain_citation_ids':['W1']});return json.dumps(result)
    monkeypatch.setattr(service,'_provider_from_llm_config',lambda config:Provider())
    result=service.research_chat(actor=owner(),payload={'question':'Explain observation','page':'chain','onchain_context':ref})
    assert result['status']=='ok' and result['cited_onchain_ids']==['W1']
    saved=service.research_onchain_snapshot(actor=owner(),snapshot_id=result['onchain_context_snapshot_id'])
    assert saved['validated_reply']['summary']==result['summary']
    assert saved['validated_reply']['suggested_action']=='Review evidence'
    assert saved['validated_reply']['confidence']==0.1
    assert saved['provided_onchain']['reference']==ref
    assert service.research_onchain_history(actor=owner(),wallet_id='cw',chain_id='1',contract_address='')['items'][0]['snapshot_id']==result['onchain_context_snapshot_id']
    assert service.research_onchain_history(actor=owner('foreign'),wallet_id='cw',chain_id='1',contract_address='')['items']==[]
    assert service.research_onchain_history(actor=owner(),wallet_id='cw',chain_id='8453',contract_address='')['items']==[]
    with pytest.raises(HumanControlError):service.research_onchain_snapshot(actor=owner('foreign'),snapshot_id=result['onchain_context_snapshot_id'])
    from datetime import timedelta
    before=saved['provided_onchain']
    db.get(DataSnapshot,ref['snapshot_id']).as_of=utc_now()-timedelta(hours=1);db.commit()
    assert service.research_onchain_snapshot(actor=owner(),snapshot_id=result['onchain_context_snapshot_id'])['provided_onchain']==before
    with pytest.raises(OnchainContextError,match='ai_onchain_stale'):load_onchain_context(db,'owner-user',ref)


def chat_reference(db):
    address='0x'+'1'*40
    db.add(Wallet(id='cw',user_id='owner-user',chain='ethereum',address=address))
    source=DataSnapshot(user_id='owner-user',snapshot_type='terminal_onchain_readonly',as_of=utc_now(),data_json={'wallet_id':'cw','wallet_address':address,'chain_id':'1','contract_address':'','block_number':123,'balances':[{'symbol':'ETH','amount':'1.000000000000000001','decimals':18,'contract_address':None}]},metadata_json={'provider':'evm_rpc_readonly','signing_available':False,'execution_available':False,'usable_for_trading':False})
    db.add(source);db.flush();db.add(AuditLog(actor_type='user',actor_id='owner-user',action='terminal.onchain.read',entity_type='DataSnapshot',entity_id=source.id,payload_json={}));db.commit()
    ref={'schema_version':1,'snapshot_id':source.id,'wallet_id':'cw','chain_id':'1','contract_address':'','context_version':8,'allowance_ids':[],'protocol_ids':[]}
    return ref

@pytest.mark.parametrize('mode',['bad_citation','provider_failure'])
def test_chat_failure_does_not_persist_a_validated_reply(db,isolated_store,monkeypatch,mode):
    import json
    from test_local_secrets_and_llm_credentials import owner,configure_chat,report_for
    from app.services.human_control import HumanControlService
    ref=chat_reference(db);service=HumanControlService(db);configure_chat(service)
    class Provider:
        def generate_report(self,**kwargs):
            if mode=='provider_failure':raise RuntimeError('controlled failure')
            result=report_for(kwargs);result.update(summary='Invented source [W9]',evidence={'onchain_citation_ids':['W9']});return json.dumps(result)
    monkeypatch.setattr(service,'_provider_from_llm_config',lambda config:Provider())
    result=service.research_chat(actor=owner(),payload={'question':'Explain','onchain_context':ref})
    assert result['status']=='failed' and result['external_call_attempted'] is True
    saved=service.research_onchain_snapshot(actor=owner(),snapshot_id=result['onchain_context_snapshot_id'])
    assert saved['reply_status']=='failed' and saved['validated_reply'] is None


def test_unconfigured_chat_stops_before_building_provider(db,monkeypatch):
    from test_local_secrets_and_llm_credentials import owner
    from app.services.human_control import HumanControlService
    service=HumanControlService(db)
    monkeypatch.setattr(service,'_provider_from_llm_config',lambda config:pytest.fail('must not construct provider'))
    result=service.research_chat(actor=owner(),payload={'question':'Explain','onchain_context':chat_reference(db)})
    assert result['status']=='blocked' and result['external_call_attempted'] is False
