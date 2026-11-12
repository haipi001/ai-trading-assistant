import json
import pytest
from test_local_secrets_and_llm_credentials import isolated_store,report_for
from test_paper_review_research_chat import configure
from test_strategy_research_material import body
from test_workspaces import seed_identity_options
from app.services.human_control import HumanControlService
from app.models import DataSnapshot
from test_onchain_history_http import database
BASE='/production/human-control/llm/chat'

@pytest.mark.parametrize('grid',[False,True,'dca'])
@pytest.mark.parametrize('mode',['ok','missing_citation','bad_citation','clipped','provider_failure'])
def test_strategy_chat_reads_owned_snapshot_freezes_input_and_validates_citations(client,isolated_store,monkeypatch,mode,grid):
    seed_identity_options('default-user');configure()
    payload=body()
    if grid is True:payload['parameters'].update({'grid':{'kind':'arithmetic_grid','lower':'100','upper':'200','intervals':10},'budget_currency':'USD','quote_currency':'USD'})
    if grid=='dca':payload['parameters']['dca']={'kind':'spot_dca','frequency':'每周','first_run_local':'2027-01-02T09:30','take_profit_percent':'20'}
    packet=client.post('/api/v2/workspaces/research/strategy-material',json=payload).json()
    material=packet['material']
    reference={'snapshot_id':packet['snapshot_id'],**{k:material[k] for k in ['account_id','market','context_version','content_hash']}}
    calls=[]
    class Provider:
        def generate_report(self,**kwargs):
            calls.append(kwargs)
            assert kwargs['input_facts']['strategy_context']==material
            with database() as db:
                row=db.get(DataSnapshot,kwargs['data_snapshot_id'])
                assert row.snapshot_type=='research_chat_strategy_context'
                assert row.data_json==material
            if mode=='provider_failure':raise RuntimeError('controlled no network')
            report=report_for(kwargs);report['summary']='User parameters [SP1] require review.';report['evidence']={'strategy_citation_ids':['SP1']};report['evidence']['strategy_parameter_changes']=[{'field':'trigger','before':material['parameters']['trigger'],'after':'monthly review','rationale':'Review the budget before each cycle','citation_ids':['SP1']}]
            if grid is True:report['evidence']['strategy_parameter_changes'].append({'field':'grid.upper','before':'200','after':'250','rationale':'Review a wider hypothetical range, not a forecast','citation_ids':['SP1']})
            if grid=='dca':report['evidence']['strategy_parameter_changes'].append({'field':'dca.frequency','before':'每周','after':'每月','rationale':'Review the planned funding cadence, not a schedule','citation_ids':['SP1']})
            if mode=='missing_citation':report['summary']='No material reviewed';report['evidence']={}
            if mode=='bad_citation':report['summary']='[SP2]';report['evidence']={'strategy_citation_ids':['SP2']}
            if mode=='clipped':report['summary']='x'*9000+' [SP1]'
            return json.dumps(report)
    monkeypatch.setattr(HumanControlService,'_provider_from_llm_config',lambda *_:Provider())
    result=client.post(BASE,json={'question':'Review my parameters','strategy_context':reference}).json()
    assert result['status']==('ok' if mode=='ok' else 'failed'),result
    assert result['provided_strategy']==material
    assert result['execution_available'] is False
    assert result['context_scope']=='question_history_workspace_and_strategy_snapshot'
    assert len(calls)==1
    if mode=='ok':assert result['strategy_parameter_changes'][0]['after']=='monthly review'
    history=client.get('/api/v2/workspaces/research/strategy-history',params={'account_id':material['account_id'],'market':material['market']})
    assert history.status_code==200 and history.headers['cache-control']=='no-store'
    row=history.json()['items'][0]
    assert row['snapshot_id']==result['strategy_context_snapshot_id']
    detail_url='/api/v2/workspaces/research/strategy-history/'+row['snapshot_id']
    artifact=client.get(detail_url)
    assert artifact.status_code==200 and artifact.headers['cache-control']=='no-store'
    assert artifact.json()['provided_strategy']==material
    assert bool(artifact.json()['validated_reply'])==(mode=='ok')
    assert client.get(detail_url,headers={'X-AI-Trading-User':'foreign'}).status_code==404
    if mode=='ok':
        import subprocess,shutil
        from pathlib import Path
        if shutil.which('node'):
            source=Path(__file__).resolve().parents[2]/'src'/'research-ai.js'
            code="import {readFileSync} from 'node:fs';const {researchResult}=await import(process.argv[1]);const {strategyHistoryList,strategyHistoryArtifact}=await import(process.argv[2]);const data=JSON.parse(readFileSync(0,'utf8'));researchResult(data.result);strategyHistoryList(data.history,data.result.provided_strategy.account_id,data.result.provided_strategy.market);strategyHistoryArtifact(data.artifact,data.history.items[0]);"
            checked=subprocess.run(['node','--input-type=module','-e',code,source.as_uri(),(source.parent/'strategy-research-history.js').as_uri()],input=json.dumps({'result':result,'history':history.json(),'artifact':artifact.json()}),text=True,capture_output=True,timeout=20)
            assert checked.returncode==0,checked.stderr
    with database() as db:
        row=db.get(DataSnapshot,result['strategy_context_snapshot_id'])
        assert row.metadata_json['reply_status']==result['status']
        assert bool(row.metadata_json['validated_reply'])==(mode=='ok')


def test_strategy_chat_refuses_foreign_or_modified_reference_before_provider(client,isolated_store,monkeypatch):
    seed_identity_options('default-user');configure()
    packet=client.post('/api/v2/workspaces/research/strategy-material',json=body()).json();m=packet['material']
    reference={'snapshot_id':packet['snapshot_id'],**{k:m[k] for k in ['account_id','market','context_version','content_hash']}}
    def forbidden(*args,**kwargs):raise AssertionError('must not construct provider')
    monkeypatch.setattr(HumanControlService,'_provider_from_llm_config',forbidden)
    for patch in [{'context_version':4},{'snapshot_id':'missing'},{'client_parameters':{'amount':0}}]:
        result=client.post(BASE,json={'question':'Review','strategy_context':{**reference,**patch}}).json()
        assert result['status']=='blocked',result


def test_strategy_changes_reject_unauthorized_fields_stale_before_values_and_invalid_amounts():
    from types import SimpleNamespace
    from app.services.strategy_research_material import validate_strategy_changes
    context={'parameters':{'trigger':'weekly','amount':'100'}}
    valid={'field':'trigger','before':'weekly','after':'monthly','rationale':'User budget review','citation_ids':['SP1']}
    assert validate_strategy_changes(SimpleNamespace(evidence={'strategy_parameter_changes':[valid]}),context)==[valid]
    for change in [{**valid,'field':'status'},{**valid,'before':'stale'},{**valid,'citation_ids':['SP2']},{**valid,'extra':'command'},{**valid,'field':'amount','before':'100','after':'NaN'}]:
        with pytest.raises(ValueError):validate_strategy_changes(SimpleNamespace(evidence={'strategy_parameter_changes':[change]}),context)
    with pytest.raises(ValueError):validate_strategy_changes(SimpleNamespace(evidence={'strategy_parameter_changes':[valid,valid]}),context)


def test_grid_parameter_changes_validate_the_combined_configuration():
    from types import SimpleNamespace
    from app.services.strategy_research_material import validate_strategy_changes
    context={'parameters':{'amount':'100','grid':{'kind':'arithmetic_grid','lower':'100','upper':'200','intervals':10}}}
    change={'field':'grid.upper','before':'200','after':'250','rationale':'Hypothetical user range','citation_ids':['SP1']}
    assert validate_strategy_changes(SimpleNamespace(evidence={'strategy_parameter_changes':[change]}),context)==[change]
    for patch in [{'after':'99'},{'field':'grid.intervals','before':'10','after':'2.5'},{'field':'grid.lower','before':'100','after':'300'}]:
        with pytest.raises(ValueError):validate_strategy_changes(SimpleNamespace(evidence={'strategy_parameter_changes':[{**change,**patch}]}),context)
    assert context['parameters']['grid']['upper']=='200'


def test_dca_changes_validate_calendar_and_allow_explicit_removal_without_creating_a_schedule():
    from types import SimpleNamespace
    from app.services.strategy_research_material import validate_strategy_changes
    context={'parameters':{'amount':'100','dca':{'kind':'spot_dca','frequency':'每周','first_run_local':'2027-01-02T09:30','take_profit_percent':'20'}}}
    change={'field':'dca.frequency','before':'每周','after':'每月','rationale':'User plan review','citation_ids':['SP1']}
    assert validate_strategy_changes(SimpleNamespace(evidence={'strategy_parameter_changes':[change]}),context)==[change]
    remove={**change,'field':'dca.take_profit_percent','before':'20','after':''}
    assert validate_strategy_changes(SimpleNamespace(evidence={'strategy_parameter_changes':[remove]}),context)==[remove]
    for patch in [{'after':'每秒'},{'field':'dca.first_run_local','before':'2027-01-02T09:30','after':'2027-02-30T09:30'},{'field':'dca.take_profit_percent','before':'20','after':'-1'}]:
        with pytest.raises(ValueError):validate_strategy_changes(SimpleNamespace(evidence={'strategy_parameter_changes':[{**change,**patch}]}),context)
    assert context['parameters']['dca']['frequency']=='每周'
