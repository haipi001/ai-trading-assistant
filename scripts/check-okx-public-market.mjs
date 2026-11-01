import assert from 'node:assert/strict';
import { loadOkxPublicCandles } from '../src/okx-public-market.js';
import { loadBackendCandles } from '../src/market-api.js';
const row=['1793145600000','10','12','9','11','1.234','13','13','0'];
let requests=[];
const options={venue:'欧易OKX',quoteCurrency:'USDT',publicFetch:async(url,init)=>{requests.push([url,init]);return {ok:true,json:async()=>({code:'0',data:[row,['1793142000000',...row.slice(1)]]})}}};
const result=await loadOkxPublicCandles('BTC','1h',options);
assert.equal(result.status,'connected');assert.equal(result.candles[0].time,1793142000);assert.equal(result.asset.symbol,'BTC-USDT');
assert.equal(requests[0][1].credentials,'omit');assert.equal(requests[0][1].redirect,'error');
for(const [period,bar] of [['1d','1Dutc'],['1wk','1Wutc'],['1mo','1Mutc'],['3mo','3Mutc']]){await loadOkxPublicCandles('BTC/USDT',period,options);assert.equal(new URL(requests.at(-1)[0]).searchParams.get('bar'),bar);}
const count=requests.length;
for(const change of [{venue:'币安'},{quoteCurrency:'USD'}])assert.equal((await loadOkxPublicCandles('BTC','1h',{...options,...change})).status,'unsupported');
assert.equal((await loadOkxPublicCandles('BTC','8h',options)).status,'unsupported');assert.equal(requests.length,count);
for(const data of [[row,row],[[...row.slice(0,8),'x']],[[row[0],'10','1',...row.slice(3)]],null])assert.equal((await loadOkxPublicCandles('BTC','1h',{...options,publicFetch:async()=>({ok:true,json:async()=>({code:'0',data})})})).status,'invalid');
assert.equal((await loadOkxPublicCandles('BTC','1h',{...options,publicFetch:async()=>({ok:true,json:async()=>({code:'51000',msg:'ignored'})})})).status,'error');
assert.equal((await loadBackendCandles('BTC','1h',{...options,publicMarket:true,request:async()=>[]})).status,'connected');
console.log('OKX public candles: venue identity, UTC calendar periods, strict parsing, sorting and fallback passed');
