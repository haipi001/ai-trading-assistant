import assert from 'node:assert/strict';
import {canUpdateCurrentCandle,candleStructureKey} from '../src/chart-live-update.js';
const bars=[{time:1,open:10,high:12,low:9,close:11,volume:1},{time:2,open:11,high:13,low:10,close:12,volume:2}];
const key=candleStructureKey(bars,true),changed=[bars[0],{...bars[1],close:13,volume:3}];
assert.equal(candleStructureKey(changed,true),key);assert.notEqual(candleStructureKey(changed,false),candleStructureKey(bars,false));
assert.notEqual(candleStructureKey([{...bars[0],volume:2},bars[1]],true),key);assert.notEqual(candleStructureKey([...bars,{...bars[1],time:3}],true),key);
assert.equal(canUpdateCurrentCandle(['MA','Volume'],false),true);assert.equal(canUpdateCurrentCandle(['RSI','MACD','KDJ','EMA','BOLL','VWAP'],false),true);assert.equal(canUpdateCurrentCandle(['MA'],true),false);
console.log('Chart current-bar reuse: historical corrections and timeline changes invalidate; replay rebuild retained; standard studies reuse allowed');
