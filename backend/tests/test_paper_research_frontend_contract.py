"""Actual backend plan DTOs must pass the shipped terminal validator."""
import json
from pathlib import Path
import shutil
import subprocess
import pytest
from test_terminal_research_paper_loop import run_loop

@pytest.mark.skipif(shutil.which('node') is None,reason='Node required for frontend protocol acceptance')
@pytest.mark.parametrize('args',[
    ('stocks','AAPL','stock','US','NASDAQ',1),
    ('cex','BTC','crypto','GLOBAL','CEX',.001),
])
def test_real_plan_and_draft_dtos_pass_terminal_preview_contract(client,args):
    result=run_loop(client,*args)
    module=(Path(__file__).resolve().parents[2]/'src'/'paper-research-review.js').as_uri()
    code='''import {readFileSync} from 'node:fs';import assert from 'node:assert/strict';
const {previewResearchPaperOrder}=await import(process.argv[1]);
const {manualPaperThesisResponse}=await import(process.argv[2]);
const data=JSON.parse(readFileSync(0,'utf8'));let paths=[];
assert.equal(manualPaperThesisResponse({thesis:data.thesis,execution_available:false},data.account.id,data.asset.id).id,data.thesis.id);
const form={accountId:data.account.id,assetId:data.asset.id,thesisId:data.thesis.id,reportId:data.report.id,evidenceMode:'report',side:'buy',quantity:String(data.quantity),price:String(data.price),rationale:'Explicit human controlled contract acceptance'};
const result=await previewResearchPaperOrder(async path=>{paths.push(path);return path.includes('create-plan-and-evaluate')?data.plan:data.draft;},form,data.report,[data.thesis]);
assert.equal(result.draft.id,data.draft.id);assert.equal(paths.length,2);assert.ok(paths.every(path=>!path.includes('/approve')&&!path.includes('/execute')));
'''
    completed=subprocess.run(['node','--input-type=module','-e',code,module,(Path(__file__).resolve().parents[2]/'src'/'paper-thesis.js').as_uri()],input=json.dumps(result),text=True,capture_output=True,timeout=20)
    assert completed.returncode==0,completed.stderr

@pytest.mark.parametrize('entity',['report','account'])
def test_traceability_rejects_foreign_report_or_account_before_creating_intent(client,entity):
    from app.models import ResearchReport,Account
    from test_server_account_risk import edit_db
    result=run_loop(client,'stocks','AAPL','stock','US','NASDAQ',1)
    from test_manual_paper_thesis import business_counts
    previous=business_counts()
    edit_db(lambda db:setattr(db.get(ResearchReport if entity=='report' else Account,result[entity]['id']),'user_id','foreign-owner'))
    response=client.post(f"/reports/{result['report']['id']}/create-plan-and-evaluate",json={'thesis_id':result['thesis']['id'],'account_id':result['account']['id'],'side':'buy','order_type':'limit','quantity':1,'limit_price':result['price'],'user_rationale':'Explicit own rationale cannot authorize foreign objects.'})
    assert response.status_code==422,response.text
    assert business_counts()==previous
