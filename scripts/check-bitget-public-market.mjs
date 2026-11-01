import assert from 'node:assert/strict';
import {loadBitgetPublicCandles} from '../src/bitget-public-market.js';
import {loadBackendCandles} from '../src/market-api.js';
const row=['1793145600000','10','12','9','11','1.234','13','13'];
let requests=[];const options={venue:'Bitget',quoteCurrency:'USDT',publicFetch:async(url,init)=>{requests.push([url,init]);return {ok:true,json:async()=>({code:'00000',data:[row]})};}};
const result=await loadBitgetPublicCandles('BTC','1h',options);assert.equal(result.status,'connected');assert.equal(result.candles[0].volume,1.234);assert.equal(result.asset.venue,'bitget');assert.match(requests[0][0],/symbol=BTCUSDT&granularity=1h/);assert.equal(requests[0][1].credentials,'omit');assert.equal(requests[0][1].redirect,'error');
for(const [timeframe,expected] of [['1m','1min'],['1d','1Dutc'],['1wk','1Wutc'],['1mo','1Mutc']]){await loadBitgetPublicCandles('BTC/USDT',timeframe,options);assert.equal(new URL(requests.at(-1)[0]).searchParams.get('granularity'),expected);}
for(const data of [[row,row],[[...row,'0']],[[row[0],'10','5',...row.slice(3)]],{}])assert.equal((await loadBitgetPublicCandles('BTC','1h',{...options,publicFetch:async()=>({ok:true,json:async()=>({code:'00000',data})})})).status,'invalid');
assert.equal((await loadBitgetPublicCandles('BTC','8h',options)).status,'unsupported');
assert.equal((await loadBitgetPublicCandles('BTC','1h',{...options,venue:'币安'})).status,'unsupported');
assert.equal((await loadBackendCandles('BTC','1h',{...options,publicMarket:true,request:async()=>[]})).status,'connected');
console.log('Bitget public spot candles: UTC mapping, eight-column parsing, OHLC and provider identity passed');
