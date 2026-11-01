import assert from 'node:assert/strict';
import {calculateOscillators,ema} from '../src/market-indicators.js';
const bars=values=>values.map((close,i)=>({time:100+i,open:close,high:close,low:close,close,volume:1}));
const flat=calculateOscillators(bars(Array(50).fill(10)));
assert.equal(flat.rsi.length,36);assert(flat.rsi.every(row=>row.value===50));
assert(flat.macd.every(row=>row.dif===0&&row.dea===0&&row.histogram===0));
assert(flat.kdj.every(row=>row.k===50&&row.d===50&&row.j===50));
const up=calculateOscillators(bars(Array.from({length:30},(_,i)=>i+1)));
assert(up.rsi.every(row=>row.value===100));
assert.equal(calculateOscillators(bars(Array.from({length:30},(_,i)=>30-i))).rsi.at(-1).value,0);
// Published Wilder worked example, first 14-change RSI rounded to70.464.
const wilder=[44.34,44.09,44.15,43.61,44.33,44.83,45.10,45.42,45.84,46.08,45.89,46.03,45.61,46.28,46.28];
assert(Math.abs(calculateOscillators(bars(wilder)).rsi[0].value-70.464135)<0.00001);
assert.equal(calculateOscillators(bars([1,2])).rsi.length,0);
assert.equal(calculateOscillators(bars([1,2])).kdj.length,0);
assert.deepEqual(ema([1,2,3],3),[1,1.5,2.25]);
assert.deepEqual(calculateOscillators([]),{rsi:[],macd:[],kdj:[]});
console.log('Oscillators: Wilder RSI fixture, flat/up/down, EMA seed, warmup and empty input passed');
