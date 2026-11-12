import {test} from 'node:test';
import assert from 'node:assert/strict';
import {researchThesisReviewBody,validateResearchThesisReview,previewResearchPaperOrder} from '../../src/paper-research-review.js';
const report={id:'r',data_snapshot_id:'s'},thesis={id:'t',asset_id:'a',account_id:'acct',status:'active'};
const form={evidenceMode:'report',reportId:'r',thesisId:'t',accountId:'acct',assetId:'a',side:'buy',quantity:'1',price:'100',rationale:'Human rationale'};
const trace={research_report_id:'r',data_snapshot_id:'s',thesis_id:'t',thesis_checkpoint_id:'c',checkpoint_decision:'supports'};
const packet=()=>({execution_available:false,all_gates_passed:true,order_intent:{id:'i',account_id:'acct',asset_id:'a',investment_thesis_id:'t',source_type:'research_report',source_id:'r',side:'buy',order_type:'limit',quantity:1,limit_price:100},trace:{...trace},gates:['RESEARCH_GATE','THESIS_GATE','RISK_GATE','BEHAVIOR_GATE','EXECUTION_GATE'].map(gate_type=>({gate_type,order_intent_id:'i',status:'PASSED'}))});
test('manual review requires an explicit judgement and bounded human explanation',()=>{
 assert.equal(researchThesisReviewBody('t','supports','Reviewed original sources',.7).decision,'supports');
 for(const args of [['t','','Reviewed sources',.7],['t','supports','short',.7],['t','supports','Reviewed sources',2]])assert.throws(()=>researchThesisReviewBody(...args));
 const review={execution_available:false,report_id:'r',thesis_id:'t',checkpoint:{id:'c',thesis_id:'t'},trace};
 assert.equal(validateResearchThesisReview(review,report,'t','supports'),review);
 assert.throws(()=>validateResearchThesisReview(review,report,'t','invalidates'));
});
test('reviewed report preview uses the traceability endpoint and creates only a pending draft',async()=>{
 const paths=[];
 const result=await previewResearchPaperOrder(async(path,options)=>{paths.push(path);return path.includes('create-plan')?packet():{id:'d',order_intent_id:'i',approval_status:'pending'};},form,report,[thesis]);
 assert.equal(result.draft.id,'d');assert.deepEqual(paths,['/reports/r/create-plan-and-evaluate','/orders/intents/i/draft']);
});
test('blocked gates return their reasons without creating a draft',async()=>{
 let count=0;const plan=packet();plan.all_gates_passed=false;plan.gates[0].status='BLOCKED';
 const result=await previewResearchPaperOrder(async()=>{count++;return plan;},form,report,[thesis]);assert.equal(result.draft,null);assert.equal(count,1);
});
test('foreign objects, changed terms and incomplete passing gates cannot become a draft',async()=>{
 for(const mutate of [p=>p.order_intent.account_id='foreign',p=>p.order_intent.side='sell',p=>p.order_intent.limit_price=101,p=>p.trace.data_snapshot_id='foreign',p=>p.gates.pop(),p=>p.gates[0].order_intent_id='foreign']){
  let calls=0;const plan=packet();mutate(plan);await assert.rejects(previewResearchPaperOrder(async()=>{calls++;return plan;},form,report,[thesis]),e=>e.local);assert.equal(calls,1);
 }
 let calls=0;await assert.rejects(previewResearchPaperOrder(async()=>calls++,form,report,[{...thesis,account_id:'foreign'}]));assert.equal(calls,0);
});
