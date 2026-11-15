import assert from 'node:assert/strict';
import {observeVisibleInterval,observeVisibleTimeout} from '../src/visible-interval.js';
let hidden=false,calls=0,id=0;const timers=new Map(),listeners=new Set();
const page={get hidden(){return hidden;},addEventListener:(_,fn)=>listeners.add(fn),removeEventListener:(_,fn)=>listeners.delete(fn)};
const stop=observeVisibleInterval(()=>calls++,1000,{page,schedule:fn=>{timers.set(++id,fn);return id;},cancel:id=>timers.delete(id)});
assert.equal(calls,1);assert.equal(timers.size,1);hidden=true;listeners.forEach(fn=>fn());assert.equal(timers.size,0);assert.equal(calls,1);hidden=false;listeners.forEach(fn=>fn());assert.equal(calls,2);assert.equal(timers.size,1);timers.values().next().value();assert.equal(calls,3);assert.equal(timers.size,1);stop();assert.equal(timers.size,0);assert.equal(listeners.size,0);
hidden=true;const stopHidden=observeVisibleInterval(()=>calls++,1000,{page,schedule:()=>{throw Error('hidden timer');}});assert.equal(calls,3);stopHidden();
console.log('PASS visible polling pauses without timers, resumes once and removes listeners');

hidden=false;let clock=0,dismissals=0,scheduledDelay;
const stopNotice=observeVisibleTimeout(()=>dismissals++,20000,{page,now:()=>clock,schedule:(fn,delay)=>{scheduledDelay=delay;timers.set(++id,fn);return id;},cancel:id=>timers.delete(id)});
assert.equal(scheduledDelay,20000);clock=5000;hidden=true;listeners.forEach(fn=>fn());assert.equal(timers.size,0);clock=100000;hidden=false;listeners.forEach(fn=>fn());assert.equal(scheduledDelay,15000);assert.equal(dismissals,0);clock=115000;timers.values().next().value();assert.equal(dismissals,1);assert.equal(timers.size,0);assert.equal(listeners.size,0);stopNotice();assert.equal(dismissals,1);
console.log('PASS notice timeout counts only visible time and cleans up after dismissal');
