import assert from 'node:assert/strict';
import { observeMarketSnapshot } from '../src/market-refresh.js';
let listener, pending, output=[], calls=0, signal, scheduled;
const page={visibilityState:'visible',addEventListener:(name,fn)=>listener=fn,removeEventListener:(name,fn)=>{assert.equal(fn,listener);listener=null;}};
const scheduledTasks=new Map();let id=0;
const env={page,schedule:(fn,ms)=>{assert.equal(ms,30000);scheduledTasks.set(++id,fn);scheduled=id;return id;},cancel:key=>scheduledTasks.delete(key)};
const flush=()=>new Promise(resolve=>setImmediate(resolve));
const stop=observeMarketSnapshot(s=>{calls++;signal=s;return new Promise(resolve=>pending=resolve);},result=>output.push(result),env);
assert.equal(calls,1);assert.equal(scheduledTasks.size,0);
listener();assert.equal(calls,1); // no overlapping requests
pending({status:'connected'});await flush();assert.equal(output.length,1);assert.equal(scheduledTasks.size,1);
page.visibilityState='hidden';listener();assert.equal(scheduledTasks.size,0);
page.visibilityState='visible';listener();assert.equal(calls,2);
stop();assert.equal(signal.aborted,true);assert.equal(listener,null);
pending({status:'connected'});await flush();assert.equal(output.length,1);assert.equal(scheduledTasks.size,0);
page.visibilityState='hidden';const stopHidden=observeMarketSnapshot(()=>{throw new Error('must not run');},()=>assert.fail(),env);assert.equal(scheduledTasks.size,0);stopHidden();
console.log('Market polling: sequential requests, visibility pause/resume, disposal and late-response rejection passed');
