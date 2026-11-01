import assert from 'node:assert/strict';
import { decodeMarketTickers,loadMarketTickers } from '../src/market-tickers.js';
const binance={symbol:'BTCUSDT',lastPrice:'110',openPrice:'100',highPrice:'120',lowPrice:'90',quoteVolume:'1250',closeTime:1793145600000};
assert.equal(Math.round(decodeMarketTickers([binance],'binance',['BTC']).BTC.change),10);
assert.deepEqual(decodeMarketTickers([{...binance,symbol:'BTCUSD'}],'binance',['BTC']),{});
const okx={instId:'BTC-USDT',instType:'SPOT',last:'90',open24h:'100',high24h:'110',low24h:'80',volCcy24h:'12',ts:'1793145600000'};
assert.equal(Math.round(decodeMarketTickers({code:'0',data:[okx]},'okx',['BTC']).BTC.change),-10);
for(const row of [{...binance,lastPrice:'NaN'},{...binance,openPrice:'0'},{...binance,quoteVolume:'-1'}])assert.throws(()=>decodeMarketTickers([row],'binance',['BTC']));
assert.throws(()=>decodeMarketTickers([binance,binance],'binance',['BTC']));
assert.throws(()=>decodeMarketTickers({code:'0',data:[{...okx,instType:'SWAP'}]},'okx',['BTC']));
let called=0;const request=async(url,init)=>{called++;assert.equal(init.credentials,'omit');assert.equal(init.redirect,'error');return {ok:true,json:async()=>[binance]};};
assert.equal((await loadMarketTickers('币安',['BTC'],null,request)).quotes.BTC.turnover,1250);
assert.equal((await loadMarketTickers('Hyperliquid',['BTC'],null,request)).status,'unsupported');assert.equal(called,1);
assert.equal((await loadMarketTickers('币安',['BTC'],null,async()=>({ok:false,status:429}))).status,'error');
console.log('Market tickers: identity, 24h calculation, turnover, malformed/duplicate rejection and safe requests passed');

assert.throws(()=>decodeMarketTickers([{...binance,highPrice:'100'}],'binance',['BTC']));
assert.equal(decodeMarketTickers([binance],'binance',['BTC']).BTC.amplitude,30);
const single=await loadMarketTickers('币安',['BTC'],null,async(url)=>{assert.match(url,/symbol=BTCUSDT/);return {ok:true,json:async()=>binance};});assert.equal(single.quotes.BTC.high,120);
const singleOkx=await loadMarketTickers('欧易OKX',['BTC'],null,async(url)=>{assert.match(url,/market\/ticker\?instId=BTC-USDT/);return {ok:true,json:async()=>({code:'0',data:[okx]})};});assert.equal(singleOkx.quotes.BTC.low,80);

const bitget={symbol:'BTCUSDT',lastPr:'110',open:'100',high24h:'120',low24h:'90',quoteVolume:'1250',ts:'1793145600000'};
assert.equal(Math.round(decodeMarketTickers({code:'00000',data:[bitget]},'bitget',['BTC']).BTC.change),10);
assert.throws(()=>decodeMarketTickers({code:'0',data:[bitget]},'bitget',['BTC']));
assert.throws(()=>decodeMarketTickers({code:'00000',data:[{...bitget,ts:'bad'}]},'bitget',['BTC']));
const bitgetSingle=await loadMarketTickers('Bitget',['BTC'],null,async(url,init)=>{assert.match(url,/api.bitget.com\/api\/v2\/spot\/market\/tickers\?symbol=BTCUSDT/);assert.equal(init.credentials,'omit');return {ok:true,json:async()=>({code:'00000',data:[bitget]})};});assert.equal(bitgetSingle.quotes.BTC.turnover,1250);
