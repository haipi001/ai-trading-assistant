import {applyBitgetBook,parseDepthMessage} from './bitget-live-book.js';
import {applyOkxBook} from "./okx-live-book.js";
import {decodeMarketDepth,loadMarketDepth} from './market-depth.js';
import {observeMarketSnapshot} from './market-refresh.js';
export function decodeBinanceDepthEvent(payload,symbol){
 if(payload?.stream!==`${symbol.toLowerCase()}usdt@depth20`||!Number.isSafeInteger(payload.data?.lastUpdateId)||payload.data.lastUpdateId<0)throw new Error('invalid depth stream');
 return {...decodeMarketDepth(payload.data,'binance'),sequence:payload.data.lastUpdateId};
}
export function observePublicDepth(symbol,venue,receive,env={}){
 const supported=["币安","欧易OKX","Bitget"].includes(venue);
 const page=env.page||document,schedule=env.schedule||setTimeout,cancel=env.cancel||clearTimeout;
 let stopped=false,socket=null,retry=null,watchdog=null,attempt=0,bookState=null,latest=null,lastPoll=null,live=false;
 const send=()=>{
   if(stopped)return;
   if(live&&latest)receive({...latest,status:'connected',live:true,source:`${venue} ${symbol}/USDT WebSocket实时盘口 · ${venue==='币安'?'前20档快照':venue==='Bitget'?'50档增量维护':'400档增量维护'} · 更新序号 ${latest.sequence}${latest.snapshotTime?` · 交易所时间 ${new Date(latest.snapshotTime).toISOString()}`:''} · 接收于 ${latest.receivedAt}`});
   else if(lastPoll)receive({...lastPoll,live:false,source:`${lastPoll.source}${supported?' · 实时盘口未连接，使用轮询':''}`});
 };
 const close=()=>{if(watchdog!==null){cancel(watchdog);watchdog=null;}const old=socket;socket=null;if(old){old.onopen=old.onmessage=old.onclose=old.onerror=null;old.close();}live=false;};
 const reconnect=()=>{
   close();send();
   if(!stopped&&page.visibilityState!=='hidden'&&retry===null)retry=schedule(()=>{retry=null;connect();},Math.min(30000,1000*2**Math.min(attempt++,5)));
 };
 const arm=()=>{if(watchdog!==null)cancel(watchdog);watchdog=schedule(reconnect,15000);};
 const connect=()=>{
   if(stopped||socket||page.visibilityState==='hidden'||!supported)return;
   try{
     latest=null;bookState=null;
     socket=(env.openSocket||(url=>new WebSocket(url)))(venue==='币安'?`wss://data-stream.binance.vision/stream?streams=${symbol.toLowerCase()}usdt@depth20`:venue==='Bitget'?'wss://ws.bitget.com/v3/ws/public':'wss://ws.okx.com/ws/v5/public');
     const current=socket;arm();
     if(venue!=='币安')socket.onopen=()=>{if(socket===current&&!stopped)current.send(JSON.stringify({op:"subscribe",args:[venue==='Bitget'?{instType:"spot",topic:"books50",symbol:`${symbol}USDT`}:{channel:"books",instId:`${symbol}-USDT`}]}));};
     socket.onmessage=event=>{
       if(stopped||socket!==current)return;
       try{
         if(typeof event.data!=='string'||event.data.length>65536)throw new Error('message');
         if(venue!=='币安'&&event.data==='pong')return;
         const payload=venue==='Bitget'?parseDepthMessage(event.data):JSON.parse(event.data);
         if(venue!=='币安'&&payload.event==='subscribe')return;
         let depth;
         if(venue==='Bitget'){bookState=applyBitgetBook(bookState,payload,symbol);depth={...bookState.depth,sequence:bookState.sequence.toString()};}
         else if(venue==='欧易OKX'){bookState=applyOkxBook(bookState,payload,symbol);depth={...bookState.depth,sequence:bookState.sequence};}
         else {depth=decodeBinanceDepthEvent(payload,symbol);if(latest&&depth.sequence<latest.sequence)return;}
         latest={...depth,receivedAt:new Date((env.now||Date.now)()).toISOString()};
         live=true;attempt=0;arm();send();
       }catch{reconnect();}
     };
     socket.onclose=socket.onerror=()=>{if(socket===current)reconnect();};
   }catch{reconnect();}
 };
 const stopPoll=(env.poll||observeMarketSnapshot)(signal=>loadMarketDepth(symbol,venue,signal),result=>{if(!stopped){lastPoll=result;send();}},env);
 const visibility=()=>{if(page.visibilityState==='hidden'){if(retry!==null){cancel(retry);retry=null;}close();send();}else connect();};
 if(supported&&/^[A-Z0-9]{1,24}$/.test(symbol)){page.addEventListener('visibilitychange',visibility);connect();}
 return ()=>{stopped=true;stopPoll();if(retry!==null)cancel(retry);close();page.removeEventListener('visibilitychange',visibility);};
}
