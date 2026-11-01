import assert from 'node:assert/strict';
import {depthChartModel} from '../src/market-depth-chart.js';
const data={asks:[{price:101,quantity:2},{price:102,quantity:3}],bids:[{price:100,quantity:4},{price:99,quantity:5}]};
const model=depthChartModel(data,.001);assert.equal(model.mid,100.5);assert.equal(model.buyTotal,9);assert.equal(model.sellTotal,5);assert.equal(model.buy.at(-1).value,9);assert.equal(depthChartModel(data,.001,'增量深度').buy.at(-1).value,5);
const grouped=depthChartModel(data,.1);assert.equal(grouped.buy.length,1);assert.equal(grouped.buy[0].quantity,9);assert.equal(grouped.sell[0].quantity,5);assert.ok(grouped.buy[0].price<grouped.sell[0].price);assert.equal(depthChartModel(null),null);assert.throws(()=>depthChartModel(data,0));
console.log('Real depth chart: visible base-quantity totals, conservative price buckets, cumulative/incremental modes and empty state passed');
