import {decodeMarketTickers,loadMarketTickers} from './market-tickers.js';
import {observeMarketSnapshot} from './market-refresh.js';
export function decodeBinanceTickerEvent(payload,symbols){
 const row=payload?.data;
 if(row?.e!=='24hrTicker'||typeof row.s!=='string'||payload.stream!==`${row.s.toLowerCase()}@ticker`)throw new Error('invalid ticker stream');
 const quotes=decodeMarketTickers([{symbol:row.s,lastPrice:row.c,openPrice:row.o,highPrice:row.h,lowPrice:row.l,quoteVolume:row.q,closeTime:row.E}],'binance',symbols);
 if(!Object.keys(quotes).length)throw new Error('unexpected ticker');
 return quotes;
}
export function decodeOkxTickerEvent(payload,symbols){
 if(payload?.arg?.channel!=='tickers'||!Array.isArray(payload.data)||payload.data.length!==1||payload.data[0]?.instId!==payload.arg.instId)throw new Error('invalid OKX ticker stream');
 const quotes=decodeMarketTickers({code:'0',data:payload.data},'okx',symbols);
 if(!Object.keys(quotes).length)throw new Error('unexpected OKX ticker');
 return quotes;
}
export function decodeBitgetTickerEvent(payload,symbols){
 if(payload?.arg?.instType!=='spot'||payload.arg.topic!=='ticker'||payload.action!=='snapshot'||!Array.isArray(payload.data)||payload.data.length!==1||!Number.isSafeInteger(payload.ts))throw new Error('invalid Bitget ticker stream');
 const row=payload.data[0];
 const quotes=decodeMarketTickers([{symbol:payload.arg.symbol,lastPrice:row.lastPrice,openPrice:row.openPrice24h,highPrice:row.highPrice24h,lowPrice:row.lowPrice24h,quoteVolume:row.turnover24h,closeTime:payload.ts}],'binance',symbols);
 if(!Object.keys(quotes).length)throw new Error('unexpected Bitget ticker');
 return quotes;
}
export function mergeTickerQuotes(previous,next){
 const result={...previous};
 for(const [symbol,row] of Object.entries(next))if(!result[symbol]||row.timestamp>=result[symbol].timestamp)result[symbol]=row;
 return result;
}
export function observePublicTickers(venue,symbols,receive,env={}){
 const page=env.page||document,schedule=env.schedule||setTimeout,cancel=env.cancel||clearTimeout;
 const poll=env.poll||observeMarketSnapshot;
 const supported=["币安","欧易OKX","Bitget"].includes(venue);
 let stopped=false,socket=null,retry=null,watchdog=null,attempt=0,live=false,quotes={},lastPoll=null,eventTime=null;
 const send=()=>{
   if(stopped)return;
   if(live)receive({status:'connected',quotes,source:`${venue}公开现货 · WebSocket实时报价 · 24小时涨跌 · 推送时间 ${new Date(eventTime).toISOString()} · REST每30秒校准`});
   else if(lastPoll)receive({...lastPoll,source:`${lastPoll.source}${supported?' · 实时推送未连接，使用轮询':''}`});
 };
 const stopSocket=()=>{
   if(watchdog!==null){cancel(watchdog);watchdog=null;}
   const old=socket;socket=null;
   if(old){old.onopen=old.onmessage=old.onerror=old.onclose=null;old.close();}
   live=false;
 };
 const reconnect=()=>{
   stopSocket();quotes=lastPoll?.quotes||{};send();
   if(!stopped&&page.visibilityState!=='hidden'&&retry===null)retry=schedule(()=>{retry=null;connect();},Math.min(30000,1000*2**Math.min(attempt++,5)));
 };
 const arm=()=>{if(watchdog!==null)cancel(watchdog);watchdog=schedule(reconnect,15000);};
 const connect=()=>{
   if(stopped||socket||page.visibilityState==='hidden'||!supported)return;
   const available=venue!=='币安'?Object.keys(lastPoll?.quotes||{}):symbols;
   if(!available.length)return;
   try{
     const streams=[...new Set(symbols)].map(symbol=>`${symbol.toLowerCase()}usdt@ticker`).join('/');
     socket=(env.openSocket||(url=>new WebSocket(url)))(venue==='币安'?`wss://data-stream.binance.vision/stream?streams=${streams}`:venue==='Bitget'?'wss://ws.bitget.com/v3/ws/public':'wss://ws.okx.com/ws/v5/public');
     const current=socket;arm();
     if(venue!=='币安')socket.onopen=()=>{if(socket===current&&!stopped)current.send(JSON.stringify({op:"subscribe",args:available.map(symbol=>venue==='Bitget'?{instType:"spot",topic:"ticker",symbol:`${symbol}USDT`}:{channel:"tickers",instId:`${symbol}-USDT`})}));};
     socket.onmessage=event=>{
       if(stopped||socket!==current)return;
       try{
         if(typeof event.data!=='string'||event.data.length>65536)throw new Error('message');
         if(venue!=='币安'&&event.data==='pong')return;
         const payload=JSON.parse(event.data);
         if(venue!=='币安'&&payload.event==='subscribe')return;
         const next=venue==='币安'?decodeBinanceTickerEvent(payload,symbols):venue==='Bitget'?decodeBitgetTickerEvent(payload,available):decodeOkxTickerEvent(payload,available);
         const now=(env.now||Date.now)();
         if(Object.values(next).some(row=>row.timestamp<now-30000||row.timestamp>now+60000))throw new Error("stale stream");
         quotes=mergeTickerQuotes(quotes,next);eventTime=Math.max(eventTime||0,...Object.values(next).map(row=>row.timestamp));
         live=true;attempt=0;arm();send();
       }catch{reconnect();}
     };
     socket.onclose=socket.onerror=()=>{if(socket===current)reconnect();};
   }catch{reconnect();}
 };
 const stopPoll=poll(signal=>loadMarketTickers(venue,symbols,signal),result=>{
   if(stopped)return;
   lastPoll=result;
   if(result.status==='connected')quotes=live?mergeTickerQuotes(quotes,result.quotes):result.quotes;
   send();if(venue!=='币安')connect();
 },env);
 const visibility=()=>{
   if(page.visibilityState==='hidden'){if(retry!==null){cancel(retry);retry=null;}stopSocket();send();}
   else connect();
 };
 if(supported&&symbols.length&&symbols.every(symbol=>/^[A-Z0-9]{1,24}$/.test(symbol))){page.addEventListener('visibilitychange',visibility);connect();}
 return ()=>{stopped=true;stopPoll();if(retry!==null)cancel(retry);stopSocket();page.removeEventListener('visibilitychange',visibility);};
}
