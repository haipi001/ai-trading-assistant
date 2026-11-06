import assert from 'node:assert/strict';
import {paperOrderIntent,previewPaperOrder,paperAccounts,paperExecutionBody,paperUnknownOutcome,paperRestoredEvidence} from '../src/paper-order-workflow.js';
const form={accountId:'paper',assetId:'btc',reportId:'report',side:'buy',quantity:'2',price:'100',rationale:'Explicit manual rationale'};
assert.equal(paperOrderIntent(form).notional,undefined);
assert.equal(paperOrderIntent(form).limit_price,100);
for(const changes of [{quantity:'0'},{price:'Infinity'},{rationale:''},{accountId:''}])assert.throws(()=>paperOrderIntent({...form,...changes}),error=>error.local===true);
assert.equal(paperAccounts([{mode:'paper',id:'p'},{mode:'paper',live_trading_enabled:true},{mode:'live'}]).length,1);
let calls=[];
const request=async(path,options)=>{calls.push({path,options});if(path==='/orders/intents')return{id:'intent'};if(path==='/decision-gates/evaluate')return{all_passed:true,gates:[]};return{id:'draft',approval_status:'pending'};};
const report={id:'report',data_snapshot_id:'snapshot'};
const preview=await previewPaperOrder(request,form,report);
assert.equal(preview.draft.id,'draft');assert.equal(calls.length,3);
assert.ok(calls.every(call=>!call.path.includes('/approve')&&!call.path.includes('/execute')));
assert.deepEqual(calls[2].options.body,{order_intent_id:'intent'});
calls=[];
const blocked=await previewPaperOrder(async(path,options)=>{calls.push(path);return path==='/orders/intents'?{id:'intent'}:{all_passed:false,gates:[{status:'BLOCKED'}]};},form,report);
assert.equal(blocked.draft,null);assert.equal(calls.length,2);
await assert.rejects(previewPaperOrder(request,form,{...report,id:'other'}),error=>error.local===true);
console.log('Paper ticket workflow: positive inputs, Paper-only accounts, evidence identity, gate blocking, server draft and no implicit approval/execution passed');
calls=[];
const manualForm={...form,reportId:'',evidenceMode:'manual'};
assert.deepEqual(paperOrderIntent(manualForm).evidence_json,{});
const manual=await previewPaperOrder(async(path,options)=>{calls.push({path,options});if(path==='/orders/intents')return{id:'manual-intent'};if(path.endsWith('/manual-evidence'))return{order_intent_id:'manual-intent',data_snapshot_id:'server-quote',quote_source:'mock'};if(path==='/decision-gates/evaluate')return{all_passed:true,gates:[]};return{id:'manual-draft'};},manualForm);
assert.equal(manual.draft.id,'manual-draft');assert.equal(calls.length,4);
assert.equal(calls[2].options.body.data_snapshot_id,'server-quote');
assert.ok(calls.every(call=>!call.path.includes('/approve')&&!call.path.includes('/execute')&&!call.path.includes('/reports')));
assert.throws(()=>paperOrderIntent({...manualForm,evidenceMode:'report'}),error=>error.local);
await assert.rejects(previewPaperOrder(async path=>path==='/orders/intents'?{id:'manual-intent'}:{order_intent_id:'other',data_snapshot_id:'server-quote'},manualForm),error=>error.local);
console.log('Manual Paper path: server quote evidence, no report/model dependency, mismatched evidence refusal and explicit approval boundary passed');

const attempts=new Map();let generated=0;
const firstBody=paperExecutionBody('draft','225.12',attempts,()=>`request-${++generated}`);
assert.deepEqual(paperExecutionBody('draft',225.12,attempts,()=>`request-${++generated}`),firstBody);
assert.equal(generated,1);
assert.throws(()=>paperExecutionBody('draft',226,attempts),error=>error.local);
assert.notEqual(paperExecutionBody('another',225.12,attempts,()=>`request-${++generated}`).idempotency_key,firstBody.idempotency_key);
console.log('Paper execution attempts: same draft/terms reuse a request key; changed terms refuse silent retry');

for(const failure of [new Error('network'),{status:503},{status:409,code:'paper_execution_outcome_unknown'}])assert.equal(paperUnknownOutcome(failure),true);
for(const refusal of [{local:true},{status:422},{status:403}])assert.equal(paperUnknownOutcome(refusal),false);
console.log('Unknown Paper outcomes: network/5xx/database ambiguity preserve retry identity; definite refusals remain distinct');

const restored=paperRestoredEvidence({id:'intent',evidence_json:{}},{decision_gate_results:{RESEARCH_GATE:{gate_id:'original'}}},[
{id:'newer',gate_type:'RESEARCH_GATE',order_intent_id:'intent',evidence_json:{research_report_id:'new-report'}},
{id:'original',gate_type:'RESEARCH_GATE',order_intent_id:'intent',evidence_json:{research_report_id:'original-report'}}]);
assert.deepEqual(restored,{evidenceMode:'report',reportId:'original-report'});
assert.deepEqual(paperRestoredEvidence({id:'intent',evidence_json:{manual_snapshot_id:'manual'}},{},[]),{evidenceMode:'manual',reportId:''});
console.log('Paper restoration: exact saved research gate, not latest unrelated report; manual evidence remains distinct');
