import test from 'node:test';
import assert from 'node:assert/strict';
import {backtestAttachment,backtestRequestReference} from '../../src/research-backtest.js';
test('backtest attachments send references only and reject changed owner, workspace and age',()=>{
 const now=Date.now(),run={id:'r',strategy_playbook_id:'p'},packet={snapshot_id:'s',execution_available:false,material:{schema_version:1,source:'saved_application_backtest',backtest_run_id:'r',strategy_playbook_id:'p',execution_available:false,usable_for_trading:false,independently_verified:false,captured_at:new Date(now).toISOString(),content_hash:'a'.repeat(64),research_packet:{backtest_run_id:'r',strategy_playbook_id:'p',packet_status:'blocked',blockers:[],warnings:[],checks:[],execution_available:false,order_creation_allowed:false}}};
 const attachment=backtestAttachment(packet,run,'u','scope');
 assert.deepEqual(Object.keys(backtestRequestReference(attachment,'u','scope',now)).sort(),['backtest_run_id','content_hash','snapshot_id']);
 for(const [user,scope,time] of [['other','scope',now],['u','changed',now],['u','scope',now+600001]])assert.throws(()=>backtestRequestReference(attachment,user,scope,time));
});

test('backtest successful replies reject mismatched material, malformed text and missing citations',async()=>{
 const {validateBacktestResult}=await import('../../src/research-backtest.js');
 const material={schema_version:1,source:'saved_application_backtest',backtest_run_id:'r',strategy_playbook_id:'p',execution_available:false,usable_for_trading:false,independently_verified:false,captured_at:new Date().toISOString(),content_hash:'a'.repeat(64),research_packet:{backtest_run_id:'r',strategy_playbook_id:'p',packet_status:'blocked',blockers:[],warnings:[],checks:[],execution_available:false,order_creation_allowed:false}};
 const attachment={material,reference:{snapshot_id:'s',backtest_run_id:'r',content_hash:material.content_hash}};
 const result={status:'ok',execution_available:false,context_scope:'owned_frozen_backtest_material',provided_backtest:material,backtest_context_snapshot_id:'chat-snapshot',cited_backtest_ids:['BT1'],summary:'Review [BT1]',bullish_case:'',bearish_case:'',limitations:'',suggested_action:'',key_risks:[]};
 assert.equal(validateBacktestResult(result,attachment),result);
 for(const patch of [{summary:null},{summary:'No marker'},{cited_backtest_ids:['BT2']},{provided_backtest:{...material,content_hash:'b'.repeat(64)}},{provided_backtest:{...material,usable_for_trading:true}},{key_risks:[{}]},{context_scope:'unrelated'}])assert.throws(()=>validateBacktestResult({...result,...patch},attachment));
});
