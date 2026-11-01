import assert from 'node:assert/strict';
import {selectLargeTrades} from '../src/large-trades.js';
const rows=[{id:'1',price:100,quantity:2,side:'买入'},{id:'2',price:100,quantity:3,side:'卖出'}];
assert.deepEqual(selectLargeTrades(rows,200).map(row=>row.notional),[200,300]);assert.equal(selectLargeTrades(rows,200,'买入').length,1);assert.equal(selectLargeTrades(rows,301).length,0);assert.throws(()=>selectLargeTrades(rows,NaN));assert.throws(()=>selectLargeTrades(rows,-1));assert.equal(rows[0].notional,undefined);
console.log('Large trades: quote notional threshold, side filter, empty sample, invalid input and immutable rows passed');
