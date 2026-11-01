import assert from 'node:assert/strict';
import { loadBinancePublicCandles, loadBackendCandles } from '../src/market-api.js';
const row=[1793145600000,'10','12','9','11','1.234',1793149199999];
let calls=[];
const options={venue:'币安',quoteCurrency:'USDT',publicFetch:async(url,init)=>{calls.push([url,init]);return {ok:true,json:async()=>[row]};}};
assert.equal((await loadBinancePublicCandles('BTC','1h',options)).candles[0].volume,1.234);
assert.match(calls[0][0],/symbol=BTCUSDT&interval=1h&limit=240/);
assert.equal(calls[0][1].credentials,'omit');assert.equal(calls[0][1].redirect,'error');
for(const [period,expected] of [['1wk','1w'],['1mo','1M']]){await loadBinancePublicCandles('BTC/USDT',period,options);assert.equal(new URL(calls.at(-1)[0]).searchParams.get('interval'),expected);}
const n=calls.length;
for(const change of [{venue:'OKX'},{quoteCurrency:'USD'}])assert.equal((await loadBinancePublicCandles('BTC','1h',{...options,...change})).status,'unsupported');
assert.equal((await loadBinancePublicCandles('BTC','45m',options)).status,'unsupported');assert.equal(calls.length,n);
for(const rows of [[row,row],[[row[0],'10','5','9','11','1',row[6]]],[[row[0],null,...row.slice(2)]],{}])assert.equal((await loadBinancePublicCandles('BTC','1h',{...options,publicFetch:async()=>({ok:true,json:async()=>rows})})).status,'invalid');
const denied=await loadBackendCandles('BTC','1h',{...options,publicMarket:true,request:async()=>{throw Object.assign(new Error(),{status:403})}});assert.equal(denied.status,'unauthorized');assert.equal(calls.length,n);
assert.equal((await loadBackendCandles('BTC','1h',{...options,publicMarket:true,request:async()=>[]})).status,'connected');
assert.equal((await loadBinancePublicCandles('BTC','1h',{...options,publicFetch:async()=>({ok:false,status:429})})).status,'error');
console.log('Public market identity, intervals, strict OHLC, request isolation and fallback checks passed');
