import assert from 'node:assert/strict';
import {apiRequest} from '../src/backend-api.js';
const original=globalThis.fetch;
let seenSignal;
globalThis.fetch=async(url,init)=>{seenSignal=init.signal;return new Promise((resolve,reject)=>{const abort=()=>reject(Object.assign(new Error('aborted'),{name:'AbortError'}));if(init.signal.aborted)abort();else init.signal.addEventListener('abort',abort,{once:true});});};
try {
 const external=new AbortController();
 await assert.rejects(apiRequest('/fixture',{signal:external.signal,timeout:15}),{name:'AbortError'});
 assert.equal(external.signal.aborted,false);assert.equal(seenSignal.aborted,true);
 const cancel=new AbortController();const pending=apiRequest('/fixture',{signal:cancel.signal,timeout:1000});cancel.abort();await assert.rejects(pending,{name:'AbortError'});
 const already=new AbortController();already.abort();await assert.rejects(apiRequest('/fixture',{signal:already.signal}),{name:'AbortError'});
 globalThis.fetch=async()=>({ok:true,json:async()=>({ok:true})});assert.deepEqual(await apiRequest('/fixture'),{ok:true});
} finally {globalThis.fetch=original;}
console.log('API request cancellation: deadline with external signal, user abort, pre-abort and success passed');
