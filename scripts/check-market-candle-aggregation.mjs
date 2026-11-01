import assert from 'node:assert/strict';
import {aggregateMarketCandles} from '../src/market-candle-aggregation.js';
import {loadBackendCandles} from '../src/market-api.js';
const start=1793232000; // Fixed UTC midnight, divisible by 45m and 8h.
const bar=(time,i=0)=>({time,open:10+i,high:13+i,low:9+i,close:11+i,volume:2+i});
const rows=Array.from({length:6},(_,i)=>bar(start+i*900,i));
let result=aggregateMarketCandles(rows,900,2700,(start+5400)*1000);
assert.deepEqual(result.candles,[{time:start,open:10,high:15,low:9,close:13,volume:9},{time:start+2700,open:13,high:18,low:12,close:16,volume:18}]);
assert.equal(result.partial,false);
result=aggregateMarketCandles(rows.slice(0,4),900,2700,(start+2800)*1000);
assert.equal(result.candles.length,2);assert.equal(result.partial,true);
// A missing component cannot be replaced by a synthetic flat candle.
result=aggregateMarketCandles(rows.filter((_,i)=>i!==1),900,2700,(start+5400)*1000);
assert.equal(result.skipped,1);assert.equal(result.candles.length,1);
assert.equal(result.candles[0].time,start+2700);
assert.equal(aggregateMarketCandles(rows.slice(1),900,2700,(start+5400)*1000).skipped,1);
assert.equal(aggregateMarketCandles(rows.slice(0,4),900,2700,(start+3800)*1000).candles.length,1); // Stale current bucket lacks its latest subperiod.
assert.throws(()=>aggregateMarketCandles([bar(start+1)],900,2700,(start+5400)*1000));
assert.throws(()=>aggregateMarketCandles([bar(start+900)],900,2700,start*1000));
assert.throws(()=>aggregateMarketCandles(rows,900,2800));
assert.throws(()=>aggregateMarketCandles([bar(start),bar(start)],900,2700));
assert.throws(()=>aggregateMarketCandles([{...bar(start),volume:Number.MAX_VALUE},{...bar(start+900),volume:Number.MAX_VALUE},{...bar(start+1800),volume:Number.MAX_VALUE}],900,2700,(start+5400)*1000));
result=aggregateMarketCandles([bar(start),bar(start+14400,1)],14400,28800,(start+28800)*1000);
assert.equal(result.candles.length,1);assert.equal(result.candles[0].volume,5);
let calls=[];
const options={publicMarket:true,venue:'币安',quoteCurrency:'USDT',request:async()=>[],publicFetch:async(url)=>{calls.push(new URL(url));return {ok:true,json:async()=>rows.map(row=>[row.time*1000,...['open','high','low','close','volume'].map(key=>String(row[key])),(row.time+900)*1000-1])};}};
result=await loadBackendCandles('BTC','45m',options);
assert.equal(result.status,'connected');assert.equal(result.aggregation.target,'45m');assert.equal(result.publicProvider,undefined);assert.equal(result.publicInterval,undefined);assert.match(result.source,/UTC聚合/);assert.equal(calls[0].searchParams.get('interval'),'15m');
const before=calls.length;
result=await loadBackendCandles('BTC','45m',{...options,request:async()=>{throw Object.assign(new Error(),{status:403});}});
assert.equal(result.status,'unauthorized');assert.equal(calls.length,before);
console.log('UTC candle aggregation: OHLCV, incomplete gaps, partial/latest periods, overflow, identity path and no authorization fallback passed');
for(const venue of ['欧易OKX','Bitget']){
 const sourceRows=[bar(start),bar(start+14400,1)];let requested;
 result=await loadBackendCandles('BTC','8h',{...options,venue,publicFetch:async(url)=>{requested=new URL(url);const data=sourceRows.map(row=>[String(row.time*1000),...['open','high','low','close','volume'].map(key=>String(row[key])),...venue==='Bitget'?['1','1']:['1','1','1']]);return {ok:true,json:async()=>({code:venue==='Bitget'?'00000':'0',data})};}});
 assert.equal(result.status,'connected');assert.equal(result.candles.length,1);assert.equal(result.aggregation.base,'4h');assert.equal(result.publicProvider,undefined);
 assert.equal(venue==='Bitget'?requested.searchParams.get('granularity'):requested.searchParams.get('bar'),venue==='Bitget'?'4h':'4H');
 assert.equal(result.asset.venue,venue==='Bitget'?'bitget':'okx');
}
