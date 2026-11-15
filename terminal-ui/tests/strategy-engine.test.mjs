import test from 'node:test';
import assert from 'node:assert/strict';
import {runStrategy,compileStrategy} from '../../src/strategy-engine.js';
const code=JSON.stringify({version:1,type:'sma_cross',fast:2,slow:3});
const bars=[10,11,12,13,14,9,8,7,6].map((close,i)=>({time:1000+i*60,open:close,high:close+1,low:close-1,close}));
test('signal fills only at next open and includes entry and exit fees',()=>{const r=runStrategy(code,bars,{capital:1000,fee:1,slippage:0});assert.equal(r.trades.length,1);assert.equal(r.trades[0].time,bars[4].time);assert.equal(r.trades[0].price,14);assert.equal(r.trades[0].exitPrice,8);assert.ok(Math.abs(r.final-1000/1.01/14*8*.99)<1e-8);assert.ok(r.maxDrawdown>0);});
test('future bars do not change previous equity',()=>{const a=runStrategy(code,bars),b=runStrategy(code,[...bars,{time:2000,open:100,high:101,low:99,close:100}]);assert.deepEqual(a.equity,b.equity.slice(0,-1));});
test('reject malformed scripts, invalid bars, fees and short samples',()=>{assert.throws(()=>compileStrategy('alert(1)'));assert.throws(()=>compileStrategy('{"version":1,"type":"sma_cross","fast":5,"slow":2}'));assert.throws(()=>runStrategy(code,bars,{fee:-1}));assert.throws(()=>runStrategy(code,bars.slice(0,3)));assert.throws(()=>runStrategy(code,[...bars].reverse()));});
test('flat market produces no fabricated trades',()=>{const r=runStrategy(code,bars.map(b=>({...b,open:10,close:10,high:11,low:9})));assert.equal(r.trades.length,0);assert.equal(r.returnPct,0);assert.equal(r.winRate,null);});
