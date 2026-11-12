import {test} from 'node:test';
import assert from 'node:assert/strict';
import {paperReviewBody,paperReviewResponse} from '../../src/paper-review.js';
const review={id:'r',execution_id:'e',order_draft_id:'d',trade_journal_entry_id:'j',user_id:'u',updated_at:'2026-11-11T00:00:00Z',review_json:{existing:'preserved'}};
const context={execution:{id:'e',execution_mode:'paper',order_draft_id:'d'},journal_entry:{id:'j'},post_trade_review:review,execution_available:false};
test('saving manual notes preserves other review material and does not mark completion',()=>{
 const body=paperReviewBody(context,' My review ');
 assert.equal(body.status,undefined);assert.equal(body.expected_updated_at,review.updated_at);assert.equal(body.review_json.existing,'preserved');assert.equal(body.review_json.terminal_manual_review.notes,'My review');
 assert.equal(paperReviewBody(context,'Done',true).status,'completed');
});
test('invalid material and blank notes cannot become a save request',()=>{
 for(const bad of [{...context,execution_available:true},{...context,execution:{...context.execution,execution_mode:'live'}},{...context,post_trade_review:{...review,execution_id:'other'}},{...context,post_trade_review:{...review,updated_at:'unknown'}}])assert.throws(()=>paperReviewBody(bad,'notes'));
 for(const bad of ['', ' ', 'a'.repeat(8001)])assert.throws(()=>paperReviewBody(context,bad));
});
test('a reply cannot replace another user, execution, draft or journal record',()=>{
 for(const key of ['id','execution_id','order_draft_id','trade_journal_entry_id','user_id'])assert.throws(()=>paperReviewResponse({...review,[key]:'other'},context));
 assert.equal(paperReviewResponse({...review,status:'completed'},context).post_trade_review.status,'completed');
});

test('an ignored save cannot be reported as persisted or completed',()=>{const body=paperReviewBody(context,'Saved',true);assert.throws(()=>paperReviewResponse({...review,status:'pending'},context,body));assert.throws(()=>paperReviewResponse({...review,status:'completed'},context,body));assert.equal(paperReviewResponse({...review,status:'completed',review_json:body.review_json},context,body).post_trade_review.status,'completed');});
