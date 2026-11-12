import {test} from 'node:test';
import assert from 'node:assert/strict';
import {marketHistoryList,marketHistoryArtifact} from '../../src/market-research-history.js';
const snapshot='12345678-1234-1234-1234-123456789abc';
const row={snapshot_id:snapshot,symbol:'ETH',market_type:'spot',venue:'Public source',quote_currency:'USDT',timeframe:'1m',kind:'csv',created_at:'2026-11-11T00:00:00Z',reply_status:'ok'};
function artifact(){return {snapshot_id:snapshot,execution_available:false,request_id:'chat-'+snapshot,provider:'openai',provider_mode:'bring_your_own',model:'controlled-test',reply_status:'ok',validated_reply:{status:'ok',summary:'Historical sample [M1]',bullish_case:'Limited sample',bearish_case:'Missing current information',key_risks:['Not current prices'],limitations:'Not independently verified',confidence:0.2,suggested_action:'Research only',cited_market_ids:['M1'],cited_news_ids:[]},provided_market:{...row,source_verified:false,data_semantics:'raw_ohlcv',content_hash:'a'.repeat(64),captured_at:row.created_at,observed_at:null,bars:[{time:100,open:10,high:12,low:9,close:11,volume:2}],statistics:{first_open:10,last_close:11,sample_high:12,sample_low:9,sample_change_pct:10,sample_volume:2}}};}
test('market history list rejects duplicate, oversized or mismatched market identities',()=>{
 const value={execution_available:false,has_more:false,items:[row]};assert.equal(marketHistoryList(value),value);
 for(const change of [{execution_available:true},{has_more:1},{items:[row,row]},{items:Array(21).fill(row)},{items:[{...row,market_type:'stock'}]},{items:[{...row,reply_status:'executed'}]},{items:[{...row,created_at:'unknown'}]}])assert.throws(()=>marketHistoryList({...value,...change}));
});
test('market history artifacts preserve source identity and validate saved replies and citations',()=>{
 assert.equal(marketHistoryArtifact(artifact(),row).validated_reply.summary,'Historical sample [M1]');
 for(const mutate of [v=>v.execution_available=true,v=>v.provided_market.venue='Other',v=>v.provided_market.kind='replay',v=>v.provided_market.source_verified=true,v=>v.provided_market.bars[0].high=8,v=>v.provided_market.statistics=null,v=>v.validated_reply.status='failed',v=>v.validated_reply.cited_market_ids=['M2'],v=>v.validated_reply.cited_news_ids=['N1'],v=>v.validated_reply.confidence=2,v=>v.workspace_labels={page:'assets',symbol:'BTC'}]){const value=artifact();mutate(value);assert.throws(()=>marketHistoryArtifact(value,row));}
});
test('failed and legacy market artifacts cannot claim an effective reply or use unsafe source links',()=>{
 for(const reply_status of ['failed',null]){const value={...artifact(),reply_status,validated_reply:null};assert.equal(marketHistoryArtifact(value,row).validated_reply,null);assert.throws(()=>marketHistoryArtifact({...value,validated_reply:artifact().validated_reply},row));}
 const value={...artifact(),reply_status:'failed',validated_reply:null,news_context_snapshot_id:snapshot,provided_news:{articles:[{id:'N1',title:'Untrusted source',url:'javascript:alert(1)'}]}};
 assert.throws(()=>marketHistoryArtifact(value,row));
 const missing={...artifact(),news_context_snapshot_id:snapshot};assert.throws(()=>marketHistoryArtifact(missing,row));
});

test('market history cannot rebind a snapshot to another request',()=>{const selected={...row,request_id:'chat-'+snapshot};assert.equal(marketHistoryArtifact(artifact(),selected).request_id,selected.request_id);assert.throws(()=>marketHistoryArtifact({...artifact(),request_id:'chat-00000000-0000-0000-0000-000000000000'},selected));});
