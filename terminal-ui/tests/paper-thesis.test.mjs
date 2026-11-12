import {test} from 'node:test';
import assert from 'node:assert/strict';
import {manualPaperThesisBody,manualPaperThesisResponse} from '../../src/paper-thesis.js';
const form={reason:'My explicit original rationale',drivers:'Driver one\nDriver two',invalidation:'Observed break',horizon:'swing',target:'Reassess after the next event',lossPct:'2',confidence:'0.6'};
test('human thesis keeps percent units explicit and does not supply user, snapshot or order fields',()=>{
 const body=manualPaperThesisBody(form,'account','asset');assert.equal(body.max_loss_tolerance_pct,.02);assert.deepEqual(body.key_drivers,['Driver one','Driver two']);assert.equal(body.user_id,undefined);assert.equal(body.data_snapshot_id,undefined);assert.equal(body.order_type,undefined);
});
test('incomplete or nonfinite thesis fields cannot become a server request',()=>{
 for(const change of [{reason:'short'},{drivers:''},{invalidation:''},{horizon:''},{target:'short'},{lossPct:'0'},{lossPct:'101'},{lossPct:'Infinity'},{confidence:''},{confidence:'1.1'},{drivers:'a'.repeat(501)}])assert.throws(()=>manualPaperThesisBody({...form,...change},'account','asset'));
});
test('a reply cannot silently select a different account, asset, source or executable object',()=>{
 const thesis={id:'t',account_id:'account',asset_id:'asset',source:'terminal_manual',status:'active',position_plan_json:{execution_available:false,human_authored:true}};
 assert.equal(manualPaperThesisResponse({thesis,execution_available:false},'account','asset').id,'t');
 for(const change of [{account_id:'other'},{asset_id:'other'},{source:'ai'},{status:'invalidated'},{position_plan_json:{execution_available:true,human_authored:true}}])assert.throws(()=>manualPaperThesisResponse({thesis:{...thesis,...change},execution_available:false},'account','asset'));
});
