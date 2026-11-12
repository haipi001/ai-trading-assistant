import json
import pytest
from sqlalchemy import select,func
from app.models import DataSnapshot,PostTradeReview,ResearchReport
from app.services.human_control import HumanControlService
from test_local_secrets_and_llm_credentials import isolated_store,owner,report_for,seed_chat_news
from test_onchain_history_http import database
from test_terminal_research_paper_loop import run_loop
from test_manual_paper_thesis import business_counts
from test_research_paper_review_context import prepare
from test_server_account_risk import edit_db
BASE='/production/human-control/llm/chat'


def configure(user_id='default-user'):
    with database() as db:
        HumanControlService(db).set_llm_credentials(actor=owner(user_id),payload={'provider':'deepseek','model':'controlled-paper-review','api_key':'fixture-paper-review-no-network','monthly_budget_usd':10,'per_request_budget_usd':1,'approved_for_research':True})


@pytest.mark.parametrize('mode',['ok','provider_failure','bad_citation','wrong_snapshot','no_citation','clipped_citations'])
@pytest.mark.parametrize('news',[False,True])
def test_paper_review_chat_freezes_actual_inputs_reply_or_failure_and_owned_history(client,isolated_store,monkeypatch,mode,news):
    result=run_loop(client,'stocks','AAPL','stock','US','NASDAQ',1)
    edit_db(lambda db:setattr(db.get(PostTradeReview,result['review']['id']),'status','pending'))
    original_review=client.get(f"/paper-executions/{result['execution']['id']}/review-context").json()['post_trade_review']
    packet=prepare(client,result);configure();before=business_counts()
    with database() as db:reports_before=db.scalar(select(func.count()).select_from(ResearchReport))
    if news:
        with database() as db:seed_chat_news(db,user_id='default-user')
    captured=[]
    class Provider:
        def generate_report(self,**kwargs):
            captured.append(kwargs)
            assert kwargs['input_facts']['paper_review_context']==packet['provided_paper_review']
            assert kwargs['report_type']=='portfolio_daily_review' # existing structured reply envelope, not a new trading report
            with database() as db:
                saved=db.get(DataSnapshot,kwargs['data_snapshot_id'])
                assert saved.snapshot_type=='research_chat_paper_review_context'
                assert saved.data_json==kwargs['input_facts']['paper_review_context']
                assert 'reply_status' not in saved.metadata_json
            if mode=='provider_failure':raise RuntimeError('controlled provider failure')
            reply=report_for(kwargs);identifier='PR999' if mode=='bad_citation' else 'PR2'
            reply['summary']='Original reason ['+identifier+'] and saved review [PR3].'+(' Source claim [N1].' if news else '')
            reply['evidence']={'paper_review_citation_ids':[identifier,'PR3'],**({'news_citation_ids':['N1']} if news else {})}
            if mode=='no_citation':reply['summary']='Generic explanation without reading the supplied records.';reply['evidence']={}
            if mode=='clipped_citations':reply['summary']='x'*9000+' [PR2] [PR3]'+(' [N1]' if news else '')
            if mode=='wrong_snapshot':reply['data_snapshot_id']='unrelated'
            return json.dumps(reply)
    monkeypatch.setattr(HumanControlService,'_provider_from_llm_config',lambda *_:Provider())
    response=client.post(BASE,json={'question':'Compare only recorded Paper rationale and review','page':'market','symbol':'AAPL','paper_review_context':packet['reference'],'include_news':news})
    assert response.status_code==200,response.text
    value=response.json();assert value['status']==('ok' if mode=='ok' else 'failed'),value
    assert len(captured)==1 and value['external_call_attempted'] is True
    assert value['execution_available'] is False and value['counts_as_external_evidence'] is False
    assert value['provided_paper_review']==packet['provided_paper_review']
    assert value['context_scope']==('question_history_workspace_news_and_paper_review_snapshots' if news else 'question_history_workspace_and_paper_review_snapshot')
    snapshot_id=value['paper_review_context_snapshot_id']
    listing=client.get(BASE+'/paper-review-contexts',params={'execution_id':result['execution']['id']})
    assert listing.status_code==200 and listing.headers['cache-control']=='no-store'
    assert listing.json()['items'][0]['snapshot_id']==snapshot_id
    detail=client.get(BASE+'/paper-review-context/'+snapshot_id)
    assert detail.status_code==200 and detail.headers['cache-control']=='no-store'
    artifact=detail.json();assert artifact['provided_paper_review']==packet['provided_paper_review']
    if mode=='ok':assert artifact['validated_reply']['cited_paper_review_ids']==['PR2','PR3']
    else:assert artifact['validated_reply'] is None
    assert bool(artifact['provided_news'])==news
    assert client.get(BASE+'/paper-review-context/'+snapshot_id,headers={'X-AI-Trading-User':'foreign'}).status_code==404
    assert client.get(BASE+'/paper-review-contexts',params={'execution_id':result['execution']['id']},headers={'X-AI-Trading-User':'foreign'}).json()['items']==[]
    assert business_counts()==before
    assert client.get(f"/paper-executions/{result['execution']['id']}/review-context").json()['post_trade_review']==original_review
    with database() as db:assert db.scalar(select(func.count()).select_from(ResearchReport))==reports_before
    if mode=='ok':
        import shutil,subprocess
        from pathlib import Path
        if shutil.which('node'):
            source=(Path(__file__).resolve().parents[2]/'src')
            code="""import {readFileSync} from 'node:fs';import assert from 'node:assert/strict';
const {researchResult}=await import(process.argv[1]);const {paperReviewHistoryList,paperReviewHistoryArtifact}=await import(process.argv[2]);
const {value,listing,artifact}=JSON.parse(readFileSync(0,'utf8'));researchResult(value);paperReviewHistoryList(listing,value.provided_paper_review.execution_id);paperReviewHistoryArtifact(artifact,listing.items[0]);
assert.equal(artifact.validated_reply.cited_paper_review_ids[0],'PR2');
"""
            completed=subprocess.run(['node','--input-type=module','-e',code,(source/'research-ai.js').as_uri(),(source/'paper-review-research-history.js').as_uri()],input=json.dumps({'value':value,'listing':listing.json(),'artifact':artifact}),text=True,capture_output=True,timeout=20)
            assert completed.returncode==0,completed.stderr


@pytest.mark.parametrize('kind,reason',[('missing','ai_paper_review_source_unavailable'),('extra','ai_paper_review_invalid'),('symbol','ai_paper_review_identity_mismatch'),('quote','ai_paper_review_identity_mismatch'),('mixed','ai_paper_review_incompatible'),('changed','ai_paper_review_changed')])
def test_invalid_paper_material_stops_before_provider_construction(client,isolated_store,monkeypatch,kind,reason):
    result=run_loop(client,'cex','BTC','crypto','GLOBAL','CEX',.001);packet=prepare(client,result);configure()
    payload={'question':'Review only original Paper material','symbol':'BTC','paper_review_context':dict(packet['reference'])}
    if kind=='missing':payload['paper_review_context']['snapshot_id']='missing'
    if kind=='extra':payload['paper_review_context']['client_fills']=[1]
    if kind=='symbol':payload['symbol']='AAPL'
    if kind=='quote':payload['symbol']='BTC/USDT'
    if kind=='changed':edit_db(lambda db:setattr(db.get(PostTradeReview,result['review']['id']),'status','pending'))
    if kind=='mixed':
        # Use a valid owned ledger reference; mixing is refused before either becomes a model call.
        with database() as db:
            from app.services.research_portfolio_context import prepare_portfolio_context
            payload['portfolio_context']=prepare_portfolio_context(db,'default-user',{'account_id':result['account']['id'],'market':'cex','context_version':7})['reference']
    def forbidden(*args,**kwargs):raise AssertionError('invalid material must not construct a provider')
    monkeypatch.setattr(HumanControlService,'_provider_from_llm_config',forbidden)
    value=client.post(BASE,json=payload).json()
    assert value['status']=='blocked' and value['reason']==reason,value
    assert value['external_call_attempted'] is False
    with database() as db:assert db.scalar(select(func.count()).select_from(DataSnapshot).where(DataSnapshot.snapshot_type=='research_chat_paper_review_context'))==0


def test_paper_review_reply_stays_bound_to_pre_call_records_after_review_changes(client,isolated_store,monkeypatch):
    result=run_loop(client,'stocks','AAPL','stock','US','NASDAQ',1);packet=prepare(client,result);configure()
    class Provider:
        def generate_report(self,**kwargs):
            edit_db(lambda db:setattr(db.get(PostTradeReview,result['review']['id']),'review_json',{'terminal_manual_review':{'notes':'Updated while provider was running','source':'human'}}))
            reply=report_for(kwargs);reply['summary']='Earlier recorded review [PR3].';reply['evidence']={'paper_review_citation_ids':['PR3']};return json.dumps(reply)
    monkeypatch.setattr(HumanControlService,'_provider_from_llm_config',lambda *_:Provider())
    response=client.post(BASE,json={'question':'Explain the captured review','symbol':'AAPL','paper_review_context':packet['reference']})
    assert response.status_code==200 and response.json()['status']=='ok',response.text
    artifact=client.get(BASE+'/paper-review-context/'+response.json()['paper_review_context_snapshot_id']).json()
    assert artifact['provided_paper_review']==packet['provided_paper_review']
    value=client.post(BASE,json={'question':'Do not reuse stale review','symbol':'AAPL','paper_review_context':packet['reference']}).json()
    assert value['status']=='blocked' and value['reason']=='ai_paper_review_changed'

from test_trade_permissions import managed_actor

def test_paper_ai_send_requires_research_write_but_history_is_readable_by_same_user_viewer(client,isolated_store,managed_actor,monkeypatch):
    managed_actor('owner')
    class Authorized:
        def get(self,path,**kwargs):return client.get(path,headers={'Authorization':'Bearer controlled'},**kwargs)
        def post(self,path,**kwargs):
            if isinstance(kwargs.get('json'),dict) and 'user_id' in kwargs['json']:
                kwargs['json']={**kwargs['json'],'user_id':'tenant-trade-test'}
            return client.post(path,headers={'Authorization':'Bearer controlled'},**kwargs)
        def patch(self,path,**kwargs):return client.patch(path,headers={'Authorization':'Bearer controlled'},**kwargs)
    authenticated=Authorized()
    result=run_loop(authenticated,'stocks','AAPL','stock','US','NASDAQ',1)
    packet=prepare(authenticated,result);configure('tenant-trade-test');constructed=[]
    class Provider:
        def generate_report(self,**kwargs):
            reply=report_for(kwargs);reply['summary']='Paper record [PR1].';reply['evidence']={'paper_review_citation_ids':['PR1']};return json.dumps(reply)
    def provider(*args):constructed.append(True);return Provider()
    monkeypatch.setattr(HumanControlService,'_provider_from_llm_config',provider)
    body={'question':'Review my Paper execution','symbol':'AAPL','paper_review_context':packet['reference']}
    response=authenticated.post(BASE,json=body)
    assert response.status_code==200 and response.json()['status']=='ok',response.text
    snapshot_id=response.json()['paper_review_context_snapshot_id']
    managed_actor('viewer')
    assert authenticated.post(BASE,json=body).status_code==403
    assert len(constructed)==1
    assert authenticated.get(BASE+'/paper-review-context/'+snapshot_id).status_code==200
    assert client.get(BASE+'/paper-review-context/'+snapshot_id).status_code==401


def test_review_changed_during_preflight_is_rechecked_before_provider_construction(client,isolated_store,monkeypatch):
    result=run_loop(client,'stocks','AAPL','stock','US','NASDAQ',1);packet=prepare(client,result);configure()
    original=HumanControlService.llm_preflight_dry_run
    def preflight(self,**kwargs):
        value=original(self,**kwargs)
        edit_db(lambda db:setattr(db.get(PostTradeReview,result['review']['id']),'status','pending'))
        return value
    def forbidden(*args):raise AssertionError('changed preflight material must not construct a provider')
    monkeypatch.setattr(HumanControlService,'llm_preflight_dry_run',preflight)
    monkeypatch.setattr(HumanControlService,'_provider_from_llm_config',forbidden)
    value=client.post(BASE,json={'question':'Do not use preflight-stale material','symbol':'AAPL','paper_review_context':packet['reference']}).json()
    assert value['status']=='blocked' and value['reason']=='ai_paper_review_changed',value
    assert value['external_call_attempted'] is False


def test_changed_model_provenance_cannot_describe_a_provider_built_from_another_configuration(client,isolated_store,monkeypatch):
    result=run_loop(client,'stocks','AAPL','stock','US','NASDAQ',1);packet=prepare(client,result);configure()
    original=HumanControlService.research_chat_status;calls=[]
    def changed(self,**kwargs):
        value=original(self,**kwargs);calls.append(True)
        return {**value,'model':'new-user-selected-model'} if len(calls)>1 else value
    def forbidden(*args):raise AssertionError('mismatched model/config must not construct a provider')
    monkeypatch.setattr(HumanControlService,'research_chat_status',changed)
    monkeypatch.setattr(HumanControlService,'_provider_from_llm_config',forbidden)
    value=client.post(BASE,json={'question':'No mismatched provenance','symbol':'AAPL','paper_review_context':packet['reference']}).json()
    assert value['status']=='blocked' and value['reason']=='ai_configuration_changed',value
    assert value['external_call_attempted'] is False


def test_cex_paper_reply_keeps_exact_quote_and_venue_binding_in_shipped_frontend(client,isolated_store,monkeypatch):
    import shutil,subprocess
    from pathlib import Path
    result=run_loop(client,'cex','BTC','crypto','GLOBAL','CEX',.001);packet=prepare(client,result);configure()
    class Provider:
        def generate_report(self,**kwargs):
            reply=report_for(kwargs);reply['summary']='Paper execution [PR1] and original rationale [PR2].';reply['evidence']={'paper_review_citation_ids':['PR1','PR2']};return json.dumps(reply)
    monkeypatch.setattr(HumanControlService,'_provider_from_llm_config',lambda *_:Provider())
    response=client.post(BASE,json={'question':'Explain this Paper execution','symbol':'BTC/USD','paper_review_context':packet['reference']})
    assert response.status_code==200 and response.json()['status']=='ok',response.text
    if shutil.which('node'):
        source=Path(__file__).resolve().parents[2]/'src'
        code="""import {readFileSync} from 'node:fs';import assert from 'node:assert/strict';
const {researchResult}=await import(process.argv[1]);const {paperReviewAttachmentMatches}=await import(process.argv[2]);const value=JSON.parse(readFileSync(0,'utf8'));researchResult(value);
const material=value.provided_paper_review,attachment={reference:material.reference,material},context={market:'cex',accountId:material.account_id,instrumentId:'BTC/USD',venue:'CEX',contextVersion:7};
assert.equal(paperReviewAttachmentMatches(attachment,context,'BTC/USD'),true);assert.equal(paperReviewAttachmentMatches(attachment,{...context,instrumentId:'BTC/USDT'},'BTC/USDT'),false);assert.equal(paperReviewAttachmentMatches(attachment,{...context,venue:'OKX'},'BTC/USD'),false);
"""
        completed=subprocess.run(['node','--input-type=module','-e',code,(source/'research-ai.js').as_uri(),(source/'research-paper-review.js').as_uri()],input=json.dumps(response.json()),text=True,capture_output=True,timeout=20)
        assert completed.returncode==0,completed.stderr
