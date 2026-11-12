import {test} from 'node:test';
import assert from 'node:assert/strict';
import {paperReviewMaterial} from '../../src/paper-review-material.js';
const reference={schema_version:1,snapshot_id:'s',context_version:7,execution_id:'e',account_id:'a',asset_id:'asset',market:'stocks'};
const context={execution:{id:'e'},journal_entry:{id:'j',account_id:'a',asset_id:'asset'},post_trade_review:{id:'review'}};
function packet(){return{execution_available:false,reference:{...reference},provided_paper_review:{schema_version:1,reference:{...reference},execution_id:'e',account_id:'a',asset_id:'asset',market:'stocks',source:'paper_ledger',server_retrieved:true,independently_verified:false,execution_available:false,usable_for_trading:false,captured_at:'2026-11-11T00:00:00Z',content_hash:'a'.repeat(64),entries:[{id:'PR1',kind:'paper_execution',record_id:'e',execution_mode:'paper',filled_quantity:'1.0000000001',average_fill_price:'100.01',fill_notional:'100.01',fee_amount:'0.01',realized_pnl:'0'},{id:'PR2',kind:'original_order_rationale'},{id:'PR3',kind:'saved_review_record',record_id:'review'},{id:'PR4',kind:'trade_journal_record',record_id:'j'},{id:'PR5',kind:'historical_decision_gates',current_authorization_verified:false}]}};}
test('Paper material retains decimal strings and accepts equivalent reference key order',()=>{
 const value=packet();value.provided_paper_review.reference=Object.fromEntries(Object.entries(reference).reverse());
 assert.equal(paperReviewMaterial(value,context,{contextVersion:7,market:'stocks'}).entries[0].filled_quantity,'1.0000000001');
});
test('foreign identities, stale context and execution claims cannot become a review attachment',()=>{
 for(const mutate of [p=>p.reference.account_id='other',p=>p.reference.context_version=8,p=>p.provided_paper_review.independently_verified=true,p=>p.provided_paper_review.execution_available=true,p=>p.provided_paper_review.entries.pop(),p=>p.provided_paper_review.entries[0].filled_quantity=1,p=>p.provided_paper_review.entries[4].current_authorization_verified=true]){
  const value=packet();mutate(value);assert.throws(()=>paperReviewMaterial(value,context,{contextVersion:7,market:'stocks'}));
 }
});
