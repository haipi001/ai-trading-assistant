import test from 'node:test';
import assert from 'node:assert/strict';
import {strategyHistoryList,strategyHistoryArtifact} from '../../src/strategy-research-history.js';
const row={snapshot_id:'12345678-1234-1234-1234-123456789abc',account_id:'account',market:'cex',context_version:4,reply_status:'failed',created_at:new Date().toISOString()};
const material={schema_version:1,source:'user_local_strategy_parameters',execution_available:false,usable_for_trading:false,independently_verified:false,market:'cex',account_id:'account',context_version:4,content_hash:'a'.repeat(64),captured_at:row.created_at,parameters:{name:'DCA',coin:'ETH',type:'DCA',amount:'10',platform:'mock',risk:'low',trigger:'weekly',invalidation:'manual stop',constraints:'no leverage'}};
test('strategy history is bound to selected account and failed replies cannot masquerade as successful research',()=>{
 const list={execution_available:false,items:[row],has_more:false};assert.equal(strategyHistoryList(list,'account','cex'),list);
 assert.throws(()=>strategyHistoryList(list,'foreign','cex'));
 const artifact={snapshot_id:row.snapshot_id,execution_available:false,provided_strategy:material,reply_status:'failed',validated_reply:null};
 assert.equal(strategyHistoryArtifact(artifact,row),artifact);
 assert.throws(()=>strategyHistoryArtifact({...artifact,validated_reply:{status:'ok'}},row));
 assert.throws(()=>strategyHistoryArtifact({...artifact,provided_strategy:{...material,account_id:'foreign'}},row));
 assert.throws(()=>strategyHistoryArtifact({...artifact,news_context_snapshot_id:'missing'},row));
});
