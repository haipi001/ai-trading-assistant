import assert from 'node:assert/strict';
import {createNewsFeedReader} from '../src/news-feed-reader.js';
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};};
const snapshot=provider=>({provider,status:'ready',articles:[],settings:{auto_refresh:false}});
const calls=[],events=[];
const reader=createNewsFeedReader({request:(path,options)=>{const value=deferred();calls.push({path,options,...value});return value.promise;},onStart:()=>events.push('start'),onData:value=>events.push(value.provider),onError:()=>events.push('error'),onIdle:()=>events.push('idle')});
const first=reader.load();
assert.equal(await reader.load({refresh:true}),false);assert.equal(calls.length,1);
const replacement=reader.load({replace:true});
assert.equal(calls[0].options.signal.aborted,true);assert.equal(calls[1].path,'/news-feed/latest');assert.equal(calls[1].options.method,'GET');
calls[1].resolve(snapshot('nasdaq'));await replacement;
assert.deepEqual(events,['start','start','nasdaq','idle']);
// A transport may ignore abort: its late result must still be discarded.
calls[0].resolve(snapshot('cointelegraph'));await first;
assert.deepEqual(events,['start','start','nasdaq','idle']);
const old=reader.load({refresh:true,automatic:true});assert.equal(calls[2].path,'/news-feed/refresh?automatic=true');assert.equal(calls[2].options.method,'POST');
const next=reader.load({replace:true});calls[2].reject(Error('old failure'));await old;
assert.equal(events.at(-1),'start'); // Old failure cannot clear the new busy state.
calls[3].resolve(snapshot('newsapi'));await next;assert.equal(events.at(-2),'newsapi');
const invalid=reader.load();calls[4].resolve({provider:'unknown',status:'ready',articles:[]});await invalid;
assert.deepEqual(events.slice(-2),['error','idle']);
const ending=reader.load();const count=events.length;reader.stop();assert.equal(calls[5].options.signal.aborted,true);calls[5].resolve(snapshot('cointelegraph'));await ending;
assert.equal(events.length,count);assert.equal(await reader.load(),false);
console.log('News reader: settings replacement, abort-ignoring late response, coalescing, busy ownership, invalid data and unmount passed');
