import assert from 'node:assert/strict';
import {captureChartLayout,validateChartLayout} from '../src/chart-layout-state.js';
const state={marketMode:'web3',symbol:'BTC',venue:'币安',period:'5分',chartType:'面积图',paneCount:2,paneSync:['十字光标'],studies:['MA'],paneSymbols:['BTC','ETH'],panePeriods:['5分','1时'],paneStudies:[['MA'],['BOLL','RSI']]};
const saved=captureChartLayout(state),restored=validateChartLayout(JSON.parse(JSON.stringify(saved)));
assert.deepEqual(restored,saved);assert.equal(restored.paneSymbols[1],'ETH');assert.deepEqual(restored.paneStudies[1],['BOLL','RSI']);assert.equal(restored.panePeriods.length,18);
state.paneStudies[1].push('EMA');assert.deepEqual(saved.paneStudies[1],['BOLL','RSI']);
for(const corrupt of [{...saved,schema:2},{...saved,paneCount:99},{...saved,period:'未知'},{...saved,paneStudies:[]},{...saved,paneSync:['未知']},{...saved,marketMode:'other'}]) assert.throws(()=>validateChartLayout(corrupt));
assert.deepEqual(saved,restored);
console.log('Chart layouts: full pane roundtrip, immutable capture, unsupported/corrupt rejection passed');
