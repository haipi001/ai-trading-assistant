import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
const source=readFileSync(new URL('../../src/backtest-reply-history.jsx',import.meta.url),'utf8');
const start=source.indexOf(' async function load('),end=source.indexOf('\n return <details>',start);
assert.ok(start>=0&&end>start);
for(const changed of ['identity','scope'])test('shipped backtest history reader discards delayed '+changed+' results',async()=>{
 let settle,identity='user',scope='workspace',state={},writes=0;
 const deferred=new Promise(resolve=>{settle=resolve;});
 const sandbox={identity,scope,key:'original',run:{id:'run'},current:{},job:{current:null},latest:{current:'original'},AbortController,encodeURIComponent,Set,Date,Error,getSessionIdentity:()=>identity,tradingContextIdentity:()=>scope,apiRequest:()=>deferred,setState:update=>{writes++;state=typeof update==='function'?update(state):update;}};
 vm.runInNewContext(source.slice(start,end)+';globalThis.load=load;',sandbox);
 const work=sandbox.load();assert.equal(writes,1);
 if(changed==='identity')identity='other';else scope='other';
 settle({backtest_run_id:'run',execution_available:false,has_more:false,items:[{snapshot_id:'old-private',created_at:new Date().toISOString(),reply_status:'ok'}]});
 await work;assert.equal(writes,1);assert.equal(state.items,undefined);
});
