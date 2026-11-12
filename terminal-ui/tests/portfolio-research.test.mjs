import {test} from 'node:test';
import assert from 'node:assert/strict';
import {portfolioContext,portfolioAttachmentMatches,portfolioHistoryList} from '../../src/research-portfolio.js';
import {researchResult,requestResearchChat,isResearchMaterialFailure} from '../../src/research-ai.js';
import {portfolioHistoryArtifact} from '../../src/portfolio-research-artifact.js';
const id='12345678-1234-1234-1234-123456789abc',reportId='87654321-1234-1234-1234-123456789abc';
const context={identityUserId:'u',accountId:'a',accountVerified:true,market:'stocks',contextVersion:2};
function material(){const account={account_id:'a',account_type:'brokerage',mode:'paper',base_currency:'USD'};return {schema_version:1,reference:{schema_version:1,snapshot_id:id,account_id:'a',market:'stocks',context_version:2},source_snapshot_id:id,account_id:'a',market:'stocks',context_version:2,account,source:'application_ledger',server_retrieved:true,independently_verified:false,valuation_freshness:'unknown',captured_at:new Date().toISOString(),ledger_revision:'a'.repeat(64),content_hash:'b'.repeat(64),total_position_count:1,included_count:1,truncated:false,entries:[{id:'H1',kind:'account_ledger',source:'application_ledger',account,total_position_count:1,included_count:1,truncated:false},{id:'H2',kind:'position_ledger',source:'application_ledger',record_id:'p',instrument:{asset_id:'asset',symbol:'AAPL',currency:'USD',venue:'NASDAQ'},quantity:'1.123456789',recorded_average_cost:'10',recorded_market_price:'0',recorded_market_value:'0',record_updated_at:new Date().toISOString(),quote_as_of:null,valuation_verified:false}]};}
function reply(){return {status:'ok',external_call_attempted:true,execution_available:false,request_id:'chat-'+reportId,provider:'deepseek',provider_mode:'bring_your_own',model:'controlled',context_scope:'question_history_workspace_and_portfolio_snapshot',summary:'Ledger claims [H1] [H2]',bullish_case:'Unknown valuations',bearish_case:'Missing live balances',key_risks:['Stored records only'],suggested_action:'Review only',confidence:0.1,limitations:'Not live prices',provided_portfolio:material(),portfolio_context_snapshot_id:reportId,cited_portfolio_ids:['H1','H2'],cited_news_ids:[]};}
test('portfolio material preserves exact strings and refuses false valuation or mismatched identity',()=>{
 assert.equal(portfolioContext(material()).entries[1].quantity,'1.123456789');
 for(const mutate of [v=>v.account_id='foreign',v=>v.reference.context_version=3,v=>v.independently_verified=true,v=>v.valuation_freshness='fresh',v=>v.entries[1].quantity=1,v=>v.entries[1].valuation_verified=true,v=>v.entries[1].quote_as_of=new Date().toISOString(),v=>v.entries[1].id='H9',v=>v.truncated=true]){const value=material();mutate(value);assert.throws(()=>portfolioContext(value));}
});
test('account, market, version, verification and expiry bind a portfolio attachment',()=>{
 const preview=material(),attachment={reference:preview.reference,preview};assert.equal(portfolioAttachmentMatches(attachment,context),true);
 for(const patch of [{accountId:'b'},{market:'cex'},{contextVersion:3},{accountVerified:false}])assert.equal(portfolioAttachmentMatches(attachment,{...context,...patch}),false);
 assert.equal(portfolioAttachmentMatches(attachment,context,Date.parse(preview.captured_at)+600001),false);
});
test('portfolio replies reject fabricated citations and histories reject foreign or effective failed records',()=>{
 assert.equal(researchResult(reply()).status,'ok');assert.throws(()=>researchResult({...reply(),cited_portfolio_ids:['H99']}));
 const artifact={...reply(),snapshot_id:reportId,reply_status:'ok',validated_reply:reply()};const row={snapshot_id:reportId,request_id:artifact.request_id,account_id:'a',market:'stocks',context_version:2,created_at:new Date().toISOString(),reply_status:'ok'};
 assert.equal(portfolioHistoryList({items:[row],execution_available:false,has_more:false},context).items.length,1);
 assert.equal(portfolioHistoryArtifact(artifact,row,context).reply_status,'ok');
 assert.throws(()=>portfolioHistoryArtifact(artifact,row,{...context,accountId:'foreign'}));
 assert.throws(()=>portfolioHistoryArtifact({...artifact,reply_status:'failed'},row,context));
 assert.throws(()=>portfolioHistoryArtifact({...artifact,reply_status:'failed',validated_reply:null,provided_news:{articles:[{url:'javascript:alert(1)'}]}},row,context));
});
test('chat transmits only the portfolio reference and rejects a rebound reply',async()=>{
 const result=reply(),ref=structuredClone(result.provided_portfolio.reference);
 globalThis.window={location:{origin:'http://127.0.0.1:8850'},parent:{location:{origin:'http://127.0.0.1:8850'},TerminalBackend:{session:()=>null,request:async(path,options)=>{assert.deepEqual(options.body.portfolio_context,ref);assert.equal(options.body.portfolio_context.entries,undefined);return result;}}}};
 globalThis.document={documentElement:{hasAttribute:()=>true}};
 try{assert.equal((await requestResearchChat('Review ledger',{portfolioCapture:ref})).status,'ok');result.provided_portfolio.reference.context_version=99;result.provided_portfolio.context_version=99;await assert.rejects(requestResearchChat('Review ledger',{portfolioCapture:{...ref,context_version:2}}),/identity mismatch/);}finally{delete globalThis.window;delete globalThis.document;}
});
test('recoverable material failures never masquerade as missing model configuration',()=>{for(const reason of ['ai_portfolio_changed','ai_portfolio_stale','ai_onchain_stale','ai_market_identity_mismatch','ai_news_missing'])assert.equal(isResearchMaterialFailure(reason),true);for(const reason of ['ai_permission_required','ai_configuration_required','ai_budget_required'])assert.equal(isResearchMaterialFailure(reason),false);});

test('ordinary chat does not send a new field to older backends without portfolio support',async()=>{const result={...reply(),context_scope:'question_history_and_workspace_labels_only',provided_portfolio:null,cited_portfolio_ids:[]};globalThis.window={location:{origin:'http://127.0.0.1:8850'},parent:{location:{origin:'http://127.0.0.1:8850'},TerminalBackend:{session:()=>null,request:async(path,options)=>{assert.equal(Object.hasOwn(options.body,'portfolio_context'),false);return result;}}}};globalThis.document={documentElement:{hasAttribute:()=>true}};try{assert.equal((await requestResearchChat('Explain fields')).status,'ok');}finally{delete globalThis.window;delete globalThis.document;}});
