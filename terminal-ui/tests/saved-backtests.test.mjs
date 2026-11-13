import test from 'node:test';
import assert from 'node:assert/strict';
import {savedBacktests} from '../../src/saved-backtests.js';
test('saved backend backtests require owned records and explicit nonexecution state',()=>{
 const run={id:'r',user_id:'u',name:'test',status:'blocked',created_at:new Date().toISOString(),parameters_json:{asset_id:'asset'},results_json:{execution_available:false,blocking_reasons:['insufficient_local_candles']}};
 assert.deepEqual(savedBacktests([run],'u'),[run]);assert.throws(()=>savedBacktests([run],'other'));assert.throws(()=>savedBacktests([run,run],'u'));
 assert.throws(()=>savedBacktests([{...run,results_json:{execution_available:true}}],'u'));assert.throws(()=>savedBacktests([run],null));
});

test('backtest AI preparation checks record linkage and refuses silent input truncation',async()=>{
 const {backtestReviewPacket,backtestReviewQuestion}=await import('../../src/saved-backtests.js');
 const run={id:'r',strategy_playbook_id:'p'},packet={backtest_run_id:'r',strategy_playbook_id:'p',packet_status:'blocked',blockers:['missing_candles'],warnings:[],checks:[],execution_available:false,order_creation_allowed:false};
 assert.equal(backtestReviewPacket(packet,run),packet);assert.match(backtestReviewQuestion(packet),/missing_candles/);
 assert.throws(()=>backtestReviewPacket({...packet,backtest_run_id:'other'},run));
 assert.throws(()=>backtestReviewPacket({...packet,order_creation_allowed:true},run));
 assert.throws(()=>backtestReviewQuestion({...packet,payload:'x'.repeat(4000)}));
});

test('frozen backtest material retains source identity and explicit research-only state',async()=>{
 const {savedBacktestMaterial}=await import('../../src/saved-backtests.js');
 const run={id:'r',strategy_playbook_id:'p'},packet={backtest_run_id:'r',strategy_playbook_id:'p',packet_status:'blocked',blockers:[],warnings:[],checks:[],execution_available:false,order_creation_allowed:false};
 const value={snapshot_id:'s',execution_available:false,material:{schema_version:1,source:'saved_application_backtest',backtest_run_id:'r',strategy_playbook_id:'p',execution_available:false,usable_for_trading:false,independently_verified:false,captured_at:new Date().toISOString(),content_hash:'a'.repeat(64),research_packet:packet}};
 assert.equal(savedBacktestMaterial(value,run,'s'),value);
 assert.throws(()=>savedBacktestMaterial(value,run,'another-snapshot'));
 assert.throws(()=>savedBacktestMaterial({...value,material:{...value.material,usable_for_trading:true}},run));
 assert.throws(()=>savedBacktestMaterial(value,{...run,id:'other'}));
});
