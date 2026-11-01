import {decodeMarketTrades,loadMarketTrades} from './market-trades.js';
import {observeMarketSnapshot} from './market-refresh.js';
export function decodeBinanceTradeEvent(payload,symbol,now=Date.now()){
 const row=payload?.data;
 if(payload?.stream!==`${symbol.toLowerCase()}usdt@trade`||row?.e!=='trade'||row.s!==`${symbol}USDT`||!Number.isSafeInteger(row.E)||row.E<now-30000||row.E>now+60000)throw new Error('invalid trade stream');
 return decodeMarketTrades([{id:row.t,price:row.p,qty:row.q,time:row.T,isBuyerMaker:row.m}],'binance',symbol)[0];
}
export function decodeOkxTradeEvent(payload,symbol,now=Date.now()){
 if(payload?.arg?.channel!=='trades-all'||payload.arg.instId!==`${symbol}-USDT`||!Array.isArray(payload.data)||payload.data.length>1000||!payload.data.length)throw new Error('invalid OKX trade stream');
 const rows=[];
 for(let i=0;i<payload.data.length;i+=20)rows.push(...decodeMarketTrades({code:'0',data:payload.data.slice(i,i+20)},'okx',symbol));
 if(rows.some(row=>row.time<now-30000||row.time>now+60000))throw new Error('stale OKX trade');
 return rows;
}
export function decodeBitgetTradeEvent(payload,symbol,now=Date.now()){
 if(payload?.arg?.instType!=='spot'||payload.arg.topic!=='publicTrade'||payload.arg.symbol!==`${symbol}USDT`||!['snapshot','update'].includes(payload.action)||!Array.isArray(payload.data)||!payload.data.length||payload.data.length>1000||!Number.isSafeInteger(payload.ts)||payload.ts<now-30000||payload.ts>now+60000)throw new Error('invalid Bitget trade stream');
 const rows=[];
 for(let i=0;i<payload.data.length;i+=20)rows.push(...decodeMarketTrades({code:'00000',data:payload.data.slice(i,i+20).map(row=>({symbol:`${symbol}USDT`,tradeId:row.i,price:row.p,size:row.v,ts:row.T,side:row.S}))},'bitget',symbol));
 if(rows.some(row=>row.time>now+60000||(payload.action==='update'&&row.time<now-30000)))throw new Error('stale Bitget trade');
 return rows;
}
export function mergeRecentTrades(previous,next){
 const trades=new Map(previous.map(row=>[row.id,row]));
 for(const row of next){
   const old=trades.get(row.id);
   if(old&&(old.price!==row.price||old.quantity!==row.quantity||old.time!==row.time||old.side!==row.side))throw new Error('conflicting trade');
   trades.set(row.id,row);
 }
 return [...trades.values()].sort((a,b)=>b.time-a.time||(BigInt(a.id)<BigInt(b.id)?1:BigInt(a.id)>BigInt(b.id)?-1:0)).slice(0,20);
}
export function observePublicTrades(symbol,venue,receive,env={}){
 const supported=["币安","欧易OKX","Bitget"].includes(venue);
 const page=env.page||document,schedule=env.schedule||setTimeout,cancel=env.cancel||clearTimeout;
 let stopped=false,socket=null,retry=null,watchdog=null,attempt=0,latest=[],lastPoll=null,live=false,delivery=null;
 const flush=()=>{
   delivery=null;
   if(stopped)return;
   if(live&&latest.length)receive({trades:latest,status:'connected',live:true,source:`${venue} ${symbol}/USDT WebSocket实时成交 · 最近20笔 · 最新成交 ${new Date(latest[0].time).toISOString()}`});
   else if(lastPoll)receive({...lastPoll,live:false,source:`${lastPoll.source}${supported?' · 实时成交未连接，使用轮询':''}`});
 };
 const send=()=>{if(!stopped&&delivery===null)delivery=schedule(flush,100);};
 const close=()=>{if(watchdog!==null){cancel(watchdog);watchdog=null;}const old=socket;socket=null;if(old){old.onopen=old.onmessage=old.onclose=old.onerror=null;old.close();}live=false;};
 const reconnect=()=>{
   close();send();
   if(!stopped&&page.visibilityState!=='hidden'&&retry===null)retry=schedule(()=>{retry=null;connect();},Math.min(30000,1000*2**Math.min(attempt++,5)));
 };
 const arm=()=>{if(watchdog!==null)cancel(watchdog);watchdog=schedule(reconnect,15000);};
 const connect=()=>{
   if(stopped||socket||page.visibilityState==='hidden'||!supported)return;
   try{
     latest=[];
     socket=(env.openSocket||(url=>new WebSocket(url)))(venue==='币安'?`wss://data-stream.binance.vision/stream?streams=${symbol.toLowerCase()}usdt@trade`:venue==='Bitget'?'wss://ws.bitget.com/v3/ws/public':'wss://ws.okx.com/ws/v5/business');
     const current=socket;arm();
     if(venue!=='币安')socket.onopen=()=>{if(socket===current&&!stopped)current.send(JSON.stringify({op:"subscribe",args:[venue==='Bitget'?{instType:"spot",topic:"publicTrade",symbol:`${symbol}USDT`}:{channel:"trades-all",instId:`${symbol}-USDT`}]}));};
     socket.onmessage=event=>{
       if(stopped||socket!==current)return;
       try{
         if(typeof event.data!=='string'||event.data.length>65536)throw new Error('message');
         if(venue!=='币安'&&event.data==='pong')return;
         const payload=JSON.parse(event.data);
         if(venue!=='币安'&&payload.event==='subscribe')return;
         const trades=venue==='币安'?[decodeBinanceTradeEvent(payload,symbol,(env.now||Date.now)())]:venue==='Bitget'?decodeBitgetTradeEvent(payload,symbol,(env.now||Date.now)()):decodeOkxTradeEvent(payload,symbol,(env.now||Date.now)());
         latest=mergeRecentTrades(venue==='Bitget'&&!live?[]:latest,trades);
         live=true;attempt=0;arm();send();
       }catch{reconnect();}
     };
     socket.onclose=socket.onerror=()=>{if(socket===current)reconnect();};
   }catch{reconnect();}
 };
 const stopPoll=(env.poll||observeMarketSnapshot)(signal=>loadMarketTrades(symbol,venue,signal),result=>{if(!stopped){lastPoll=result;try{if(result.status==='connected'&&!(venue==='Bitget'&&live))latest=mergeRecentTrades(latest,result.trades);send();}catch{reconnect();}}},env);
 const visibility=()=>{if(page.visibilityState==='hidden'){if(retry!==null){cancel(retry);retry=null;}close();send();}else connect();};
 if(supported&&/^[A-Z0-9]{1,24}$/.test(symbol)){page.addEventListener('visibilitychange',visibility);connect();}
 return ()=>{stopped=true;stopPoll();if(delivery!==null)cancel(delivery);if(retry!==null)cancel(retry);close();page.removeEventListener('visibilitychange',visibility);};
}
