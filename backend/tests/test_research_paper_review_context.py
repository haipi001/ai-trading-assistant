from datetime import timedelta
import pytest
from sqlalchemy import select
from app.models import DataSnapshot,PostTradeReview,TradeJournalEntry
from app.models.core import utc_now
from app.services.data_sources import DataSourceService
from app.services.data_catalog import DataCatalogService
from test_terminal_research_paper_loop import run_loop
from test_server_account_risk import edit_db
from test_manual_paper_thesis import business_counts


def prepare(client,result):
    response=client.post(f"/paper-executions/{result['execution']['id']}/research-material",json={'context_version':7})
    assert response.status_code==200,response.text
    assert response.headers['cache-control']=='no-store'
    return response.json()


@pytest.mark.parametrize('args', [('stocks','AAPL','stock','US','NASDAQ',1),('cex','BTC','crypto','GLOBAL','CEX',.001)])
def test_owned_paper_records_freeze_for_research_without_trading_or_provider_calls(client,args):
    result=run_loop(client,*args);before=business_counts();packet=prepare(client,result)
    material=packet['provided_paper_review'];reference=packet['reference']
    assert reference['execution_id']==result['execution']['id']
    assert reference['account_id']==result['account']['id']
    assert reference['asset_id']==result['asset']['id']
    assert reference['market']==args[0]
    assert material['server_retrieved'] is True and material['independently_verified'] is False
    assert material['execution_available'] is False and material['usable_for_trading'] is False
    entries={entry['id']:entry for entry in material['entries']}
    assert set(entries)=={'PR1','PR2','PR3','PR4','PR5'}
    assert isinstance(entries['PR1']['filled_quantity'],str)
    assert entries['PR2']['rationale']['text'].startswith('Explicit')
    assert entries['PR3']['human_notes']['text']=='Controlled human review of rationale and mock fill.'
    assert entries['PR5']['current_authorization_verified'] is False
    assert entries['PR5']['complete_five_gates'] is True
    restored=client.post('/paper-research-material/validate',json=reference)
    assert restored.status_code==200,restored.text
    assert restored.json()['provided_paper_review']==material
    assert business_counts()==before
    def inspect(db):
        assert DataSourceService(db).list_snapshots(snapshot_type='terminal_paper_review_context')==[]
        saved=db.get(DataSnapshot,reference['snapshot_id'])
        assert saved.metadata_json['usable_for_trading'] is False
        assert DataCatalogService(db).snapshot_decision_gate(reference['snapshot_id'],decision_scope='order_draft')['status']!='trusted'
    edit_db(inspect)


@pytest.mark.parametrize('kind,code', [('reference','ai_paper_review_identity_mismatch'),('corrupt','ai_paper_review_source_invalid'),('expired','ai_paper_review_stale'),('review_changed','ai_paper_review_changed'),('journal_foreign','ai_paper_review_source_invalid')])
def test_review_material_rejects_changed_stale_or_foreign_sources(client,kind,code):
    result=run_loop(client,'stocks','AAPL','stock','US','NASDAQ',1);packet=prepare(client,result);reference=dict(packet['reference'])
    def modify(db):
        source=db.get(DataSnapshot,reference['snapshot_id'])
        if kind=='corrupt':source.data_json={**source.data_json,'source':'unverified-replacement'}
        if kind=='expired':source.as_of=utc_now()-timedelta(seconds=601)
        if kind=='review_changed':db.get(PostTradeReview,result['review']['id']).review_json={'terminal_manual_review':{'notes':'New manual review','source':'human'}}
        if kind=='journal_foreign':db.get(TradeJournalEntry,result['review']['trade_journal_entry_id']).user_id='foreign'
    edit_db(modify)
    if kind=='reference':reference['context_version']=8
    response=client.post('/paper-research-material/validate',json=reference)
    assert response.status_code==422,response.text
    assert response.json()['detail']['code']==code


def test_material_endpoints_reject_other_users_and_forged_fields(client):
    result=run_loop(client,'stocks','AAPL','stock','US','NASDAQ',1);packet=prepare(client,result)
    foreign={'X-AI-Trading-User':'foreign'}
    assert client.post(f"/paper-executions/{result['execution']['id']}/research-material",json={'context_version':7},headers=foreign).status_code==404
    assert client.post('/paper-research-material/validate',json=packet['reference'],headers=foreign).status_code==404
    assert client.post(f"/paper-executions/{result['execution']['id']}/research-material",json={'context_version':7,'account_id':result['account']['id']}).status_code==422
    assert client.post(f"/paper-executions/{result['execution']['id']}/research-material",json={'context_version':True}).status_code==422



def test_actual_paper_review_material_passes_shipped_frontend_validator(client):
    import json,shutil,subprocess
    from pathlib import Path
    if not shutil.which('node'):pytest.skip('Node required for frontend contract acceptance')
    result=run_loop(client,'cex','BTC','crypto','GLOBAL','CEX',.001)
    packet=prepare(client,result)
    context=client.get(f"/paper-executions/{result['execution']['id']}/review-context").json()
    module=(Path(__file__).resolve().parents[2]/'src'/'paper-review-material.js').as_uri()
    code="""import {readFileSync} from 'node:fs';import assert from 'node:assert/strict';
const {paperReviewMaterial}=await import(process.argv[1]);const {packet,context}=JSON.parse(readFileSync(0,'utf8'));
assert.equal(paperReviewMaterial(packet,context,{contextVersion:7,market:'cex'}).entries.length,5);
assert.throws(()=>paperReviewMaterial(packet,context,{contextVersion:8,market:'cex'}));
"""
    completed=subprocess.run(['node','--input-type=module','-e',code,module],input=json.dumps({'packet':packet,'context':context}),text=True,capture_output=True,timeout=20)
    assert completed.returncode==0,completed.stderr
