import assert from 'node:assert/strict';
import {researchResult,researchStatus,researchText,researchHistory} from '../src/research-ai.js';
const valid={status:'ok',summary:'Fixture answer',execution_available:false,external_call_attempted:true,provider_mode:'bring_your_own',provider:'deepseek',model:'fixture-model',request_id:'chat-12345678-1234-1234-1234-123456789abc',context_scope:'question_history_and_workspace_labels_only',key_risks:['Missing data'],limitations:'No live data'};
assert.equal(researchResult(valid).summary,'Fixture answer');
for(const delta of [{provider_mode:'mock'},{provider:'unknown'},{external_call_attempted:false},{execution_available:true},{request_id:'fake'},{summary:''},{model:''},{context_scope:'live_account'}])assert.throws(()=>researchResult({...valid,...delta}));
assert.equal(researchResult({status:'blocked',execution_available:false}).status,'blocked');
assert.equal(researchStatus({can_request:false,external_call_attempted:false,execution_available:false}).can_request,false);
assert.throws(()=>researchStatus({can_request:true,external_call_attempted:true,execution_available:false}));
assert.equal(researchStatus({can_request:true,external_call_attempted:false,execution_available:false,provider:'openai',model:'fixture-model'}).can_request,true);
assert.throws(()=>researchStatus({can_request:true,external_call_attempted:false,execution_available:false,provider:'unknown',model:''}));
assert.match(researchText(valid),/Missing data/);assert.match(researchText(valid),/No live data/);
console.log('Research AI: provenance, mock rejection, execution flags, and risk/limitations formatting passed.');

const news={...valid,context_scope:'question_history_workspace_and_news_snapshot',news_context_snapshot_id:'12345678-1234-1234-1234-123456789abc',cited_news_ids:['N1'],provided_news:{provider:'cointelegraph',fetched_at:'2026-10-30T00:00:00Z',stale:false,content_hash:'a'.repeat(64),articles:[{id:'N1',title:'Fixture news',url:'https://example.com/fixture'}]}};
assert.equal(researchResult(news).provided_news.articles.length,1);
assert.throws(()=>researchResult({...news,cited_news_ids:['N99']}));
assert.throws(()=>researchResult({...news,provided_news:{...news.provided_news,articles:[{id:'N1',title:'Unsafe',url:'javascript:alert(1)'}]}}));
const history=researchHistory([{role:'ai',text:'Prior claim [N1] '+ 'x'.repeat(3000),result:news}]);
assert.equal(history[0].content.length,2000);assert.match(history[0].content,/Historical news snapshot/);assert.match(history[0].content,/N1=https:\/\/example.com\/fixture/);
