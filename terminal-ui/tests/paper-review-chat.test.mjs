import {test} from 'node:test';
import assert from 'node:assert/strict';
import {researchResult,researchHistory,isResearchMaterialFailure,requestResearchChat} from '../../src/research-ai.js';
import {paperReviewAttachmentMatches,paperReviewReadiness} from '../../src/research-paper-review.js';
import {paperReviewHistoryList,paperReviewHistoryArtifact} from '../../src/paper-review-research-history.js';
const reference={schema_version:1,snapshot_id:'10000000-0000-4000-8000-000000000000',context_version:7,execution_id:'e',account_id:'a',asset_id:'asset',market:'stocks'};
const material={schema_version:1,reference,execution_id:'e',account_id:'a',asset_id:'asset',market:'stocks',instrument:{symbol:'AAPL',asset_type:'stock',venue:'NASDAQ',currency:'USD'},source:'paper_ledger',server_retrieved:true,independently_verified:false,execution_available:false,usable_for_trading:false,captured_at:new Date().toISOString(),content_hash:'a'.repeat(64),entries:[{id:'PR1',kind:'paper_execution',record_id:'e',execution_mode:'paper',filled_quantity:'1',average_fill_price:'100',fill_notional:'100',fee_amount:'0.01',realized_pnl:'0'},{id:'PR2',kind:'original_order_rationale'},{id:'PR3',kind:'saved_review_record',record_id:'review'},{id:'PR4',kind:'trade_journal_record',record_id:'j'},{id:'PR5',kind:'historical_decision_gates',current_authorization_verified:false}]};
const response={status:'ok',execution_available:false,external_call_attempted:true,provider_mode:'bring_your_own',provider:'deepseek',model:'controlled',summary:'Recorded claim [PR2]',bullish_case:'Unknown',bearish_case:'Unknown',key_risks:[],limitations:'Paper only',request_id:'chat-20000000-0000-4000-8000-000000000000',context_scope:'question_history_workspace_and_paper_review_snapshot',provided_paper_review:material,paper_review_context_snapshot_id:'30000000-0000-4000-8000-000000000000',cited_paper_review_ids:['PR2']};
test('selected Paper attachment is bound to account, symbol, market, version and age',()=>{
 const attachment={reference,material},context={market:'stocks',accountId:'a',instrumentId:'AAPL',venue:'NASDAQ',contextVersion:7};assert.equal(paperReviewAttachmentMatches(attachment,context,'AAPL'),true);
 for(const patch of [{accountId:'b'},{market:'cex'},{contextVersion:8},{instrumentId:'MSFT'},{venue:'NYSE'},{instrumentId:'AAPL/EUR'}])assert.equal(paperReviewAttachmentMatches(attachment,{...context,...patch},'AAPL'),false);
 assert.equal(paperReviewAttachmentMatches(attachment,context,'AAPL',Date.now()+601000),false);assert.equal(isResearchMaterialFailure('ai_paper_review_changed'),true);
});
test('Paper reply provenance and history remain explicit and cannot become another source',()=>{
 assert.equal(researchResult(response),response);assert.throws(()=>researchResult({...response,cited_paper_review_ids:['PR999']}));assert.throws(()=>researchResult({...response,context_scope:'question_history_and_workspace_labels_only'}));
 assert.match(researchHistory([{role:'ai',text:'Earlier result',result:response}])[0].content,/Historical Paper review material/);
 const row={snapshot_id:response.paper_review_context_snapshot_id,request_id:response.request_id,execution_id:'e',account_id:'a',asset_id:'asset',market:'stocks',context_version:7,reply_status:'ok',created_at:new Date().toISOString()};
 paperReviewHistoryList({execution_available:false,items:[row],has_more:false},'e');
 const artifact={...row,execution_available:false,provided_paper_review:material,validated_reply:response,provider:response.provider,provider_mode:response.provider_mode,model:response.model};
 assert.equal(paperReviewHistoryArtifact(artifact,row),artifact);assert.throws(()=>paperReviewHistoryArtifact(artifact,{...row,execution_id:'other'}));assert.throws(()=>paperReviewHistoryArtifact({...artifact,reply_status:'failed'},row));
});
test('transport sends only the selected server reference, and rejects a rebound reply',async()=>{
 const requests=[];globalThis.window={location:{hostname:'localhost'},__AI_TRADING_API_BASE__:'http://localhost:8001'};
 const previousFetch=globalThis.fetch;globalThis.fetch=async(_url,options)=>{requests.push(JSON.parse(options.body));return {ok:true,json:async()=>response};};
 try{await requestResearchChat('Review this fill',{page:'market',symbol:'AAPL',paperReviewCapture:reference});assert.deepEqual(requests[0].paper_review_context,reference);assert.equal(requests[0].provided_paper_review,undefined);assert.equal(requests[0].portfolio_context,undefined);await assert.rejects(requestResearchChat('No rebound',{paperReviewCapture:{...reference,execution_id:'other'}}));}
 finally{globalThis.fetch=previousFetch;delete globalThis.window;}
});

test('a dedicated Paper review cannot silently become a generic question without its selected evidence',()=>{
 const attachment={reference,material},context={market:'stocks',accountId:'a',instrumentId:'AAPL',venue:'NASDAQ',contextVersion:7};
 assert.notEqual(paperReviewReadiness(attachment,false,context,'AAPL'),'');assert.equal(paperReviewReadiness(attachment,true,context,'AAPL'),'');assert.notEqual(paperReviewReadiness(attachment,true,context,'AAPL',{includeMarket:true}),'');assert.equal(paperReviewReadiness(null,false,context,'AAPL'),'');
});
