import {validateMarketBars} from './market-chart-model.js';
import {loadBackendCandles} from './market-api.js';
import {observeMarketSnapshot} from './market-refresh.js';
export function nextCandleTime(time,interval){
 interval=interval.replace(/utc$/, '').replace(/H$/, 'h').replace(/D$/, 'd').replace(/W$/, 'w');
 if(/^\d+M$/.test(interval)){const date=new Date(time*1000);return Date.UTC(date.getUTCFullYear(),date.getUTCMonth()+Number(interval.slice(0,-1)),1)/1000;}
 const match=/^(\d+)([smhdw])$/.exec(interval);
 if(!match)throw new Error('unsupported interval');
 return time+Number(match[1])*({s:1,m:60,h:3600,d:86400,w:604800})[match[2]];
}
export function decodeBinanceCandleEvent(payload,pair,interval,now=Date.now()){
 const event=payload?.data,k=event?.k;
 if(payload?.stream!==`${pair.toLowerCase()}@kline_${interval}`||event?.e!=='kline'||event.s!==pair||k?.s!==pair||k.i!==interval||typeof k.x!=='boolean'||!Number.isSafeInteger(event.E)||event.E<now-30000||event.E>now+60000||!Number.isSafeInteger(k.t)||k.t%1000||!Number.isSafeInteger(k.T)||k.T!==nextCandleTime(k.t/1000,interval)*1000-1)throw new Error('invalid kline identity');
 const number=value=>typeof value==='string'&&/^\d+(?:\.\d+)?$/.test(value)?Number(value):NaN;
 const bar=validateMarketBars([{time:k.t/1000,open:number(k.o),high:number(k.h),low:number(k.l),close:number(k.c),volume:number(k.v)}])[0];
 if(bar.low<=0||bar.open<=0||bar.close<=0)throw new Error('invalid price');
 return {bar,eventTime:event.E,closed:k.x};
}
export function decodeOkxCandleEvent(payload,pair,interval,now=Date.now()){
 if(payload?.arg?.channel!==`candle${interval}`||payload.arg.instId!==pair||!Array.isArray(payload.data)||payload.data.length!==1)throw new Error('invalid candle identity');
 const row=payload.data[0];
 if(!Array.isArray(row)||row.length!==9||typeof row[0]!=='string'||!/^\d{13}$/.test(row[0])||Number(row[0])%1000||!['0','1'].includes(row[8]))throw new Error('invalid candle shape');
 const number=value=>typeof value==='string'&&/^\d+(?:\.\d+)?$/.test(value)?Number(value):NaN;
 const bar=validateMarketBars([{time:Number(row[0])/1000,open:number(row[1]),high:number(row[2]),low:number(row[3]),close:number(row[4]),volume:number(row[5])}])[0];
 if(bar.low<=0||bar.open<=0||bar.close<=0||bar.time*1000>now+60000)throw new Error('invalid candle');
 return {bar,eventTime:now,closed:row[8]==='1'};
}
export function decodeBitgetCandleEvent(payload,pair,interval,now=Date.now()){
 if(payload?.arg?.instType!=='spot'||payload.arg.topic!=='kline'||payload.arg.symbol!==pair||payload.arg.interval!==interval||!['snapshot','update'].includes(payload.action)||!Array.isArray(payload.data)||payload.data.length<1||payload.data.length>1000||!Number.isSafeInteger(payload.ts)||payload.ts<now-30000||payload.ts>now+60000)throw new Error('invalid Bitget candle identity');
 const number=value=>typeof value==='string'&&/^\d+(?:\.\d+)?$/.test(value)?Number(value):NaN;
 const bars=payload.data.map(row=>{
 if(typeof row?.start!=='string'||!/^\d{13}$/.test(row.start)||Number(row.start)%1000)throw new Error('invalid candle time');
 const bar=validateMarketBars([{time:Number(row.start)/1000,open:number(row.open),high:number(row.high),low:number(row.low),close:number(row.close),volume:number(row.volume)}])[0];
 if(bar.low<=0||bar.open<=0||bar.close<=0||bar.time*1000>now+60000)throw new Error('invalid candle');
 return bar;
 });
 const checked=validateMarketBars(bars);
 return {bar:checked.at(-1),eventTime:payload.ts,closed:null};
}
export function applyCandleEvent(candles,event,interval){
 const last=candles.at(-1);if(!last)throw new Error('missing snapshot');
 if(event.bar.time<last.time)return candles;
 if(event.bar.time===last.time)return [...candles.slice(0,-1),event.bar];
 if(event.bar.time!==nextCandleTime(last.time,interval))throw new Error('kline gap');
 return [...candles,event.bar].slice(-240);
}
export function observeCandleFeed(symbol,timeframe,options,receive,env={}){
 const page=env.page||document,schedule=env.schedule||setTimeout,cancel=env.cancel||clearTimeout,now=env.now||Date.now;
 let stopped=false,socket=null,watchdog=null,base=null,lastEvent=null,live=false;
 const send=()=>{
   if(stopped||!base)return;
   receive(live?{...base,source:`${base.publicProvider==='okx'?'OKX':base.publicProvider==='bitget'?'Bitget':'Binance'} WebSocket实时K线 · ${base.asset.symbol} · ${timeframe} · UTC · ${base.publicProvider==='okx'?'本地接收时间':'推送时间'} ${new Date(lastEvent.eventTime).toISOString()} · ${lastEvent.closed===null?'末根收盘状态未提供':lastEvent.closed?'末根已收盘':'末根未收盘'}`}:{...base,source:`${base.source}${['binance','okx','bitget'].includes(base.publicProvider)?' · 实时K线未连接，轮询校准后重连':''}`});
 };
 const close=()=>{if(watchdog!==null){cancel(watchdog);watchdog=null;}const old=socket;socket=null;if(old){old.onopen=old.onmessage=old.onclose=old.onerror=null;old.close();}live=false;};
 const recover=()=>{if(live&&lastEvent&&base)base={...base,source:`${base.publicProvider==='okx'?'OKX':base.publicProvider==='bitget'?'Bitget':'Binance'} K线推送已断开 · 最近推送 ${new Date(lastEvent.eventTime).toISOString()}`};close();lastEvent=null;send();};
 const arm=()=>{if(watchdog!==null)cancel(watchdog);watchdog=schedule(recover,15000);};
 const connect=()=>{
   if(stopped||socket||page.visibilityState==='hidden'||!['binance','okx','bitget'].includes(base?.publicProvider)||base.status!=='connected')return;
   const pair=base.asset.symbol,interval=base.publicInterval;
   try{
     socket=(env.openSocket||(url=>new WebSocket(url)))(base.publicProvider==='okx'?'wss://ws.okx.com/ws/v5/business':base.publicProvider==='bitget'?'wss://ws.bitget.com/v3/ws/public':`wss://data-stream.binance.vision/stream?streams=${pair.toLowerCase()}@kline_${interval}`);
     const current=socket;arm();
     if(base.publicProvider!=='binance')socket.onopen=()=>{if(socket===current)socket.send(JSON.stringify({op:'subscribe',args:[base.publicProvider==='bitget'?{instType:'spot',topic:'kline',symbol:pair,interval}:{channel:`candle${interval}`,instId:pair}]}));};
     socket.onmessage=event=>{
       if(stopped||socket!==current)return;
       try{
         if(typeof event.data!=='string'||event.data.length>(base.publicProvider==='bitget'?524288:65536))throw new Error('message');
         if(event.data==='pong')return;
         const payload=JSON.parse(event.data);
         if(base.publicProvider!=='binance'&&payload.event==='subscribe')return;
         const decoded=base.publicProvider==='okx'?decodeOkxCandleEvent(payload,pair,interval,now()):base.publicProvider==='bitget'?decodeBitgetCandleEvent(payload,pair,interval,now()):decodeBinanceCandleEvent(payload,pair,interval,now());
         if(decoded.bar.time<base.candles.at(-1).time)return;
         if(lastEvent&&((base.publicProvider==='okx'?decoded.eventTime<lastEvent.eventTime:decoded.eventTime<=lastEvent.eventTime)||decoded.bar.time<lastEvent.bar.time))return;
         if(lastEvent?.closed&&decoded.bar.time===lastEvent.bar.time&&!decoded.closed)return;
         base={...base,candles:applyCandleEvent(base.candles,decoded,interval),observedAt:new Date(now()).toISOString()};
         lastEvent=decoded;live=true;arm();send();
       }catch{recover();}
     };
     socket.onclose=socket.onerror=()=>{if(socket===current)recover();};
   }catch{recover();}
 };
 const stopPoll=(env.poll||observeMarketSnapshot)(async signal=>{
   const startedAt=now();
   const result=await (env.load||loadBackendCandles)(symbol,timeframe,{...options,signal});
   return {result,startedAt};
 },({result,startedAt})=>{
   if(stopped)return;
   result ||= {status:"offline",candles:[],source:"K线读取失败"};
   if(result.status==='connected')result={...result,observedAt:new Date(now()).toISOString()};
   if(result.status!=='connected'||!['binance','okx','bitget'].includes(result.publicProvider)){close();lastEvent=null;base=result;send();return;}
   try{
     if(live&&lastEvent&&lastEvent.eventTime>=startedAt)result={...result,candles:applyCandleEvent(result.candles,lastEvent,result.publicInterval)};
     base=result;send();connect();
   }catch{base=result;recover();}
 },env);
 const visibility=()=>{if(page.visibilityState==='hidden')recover();};
 page.addEventListener('visibilitychange',visibility);
 return ()=>{stopped=true;stopPoll();close();page.removeEventListener('visibilitychange',visibility);};
}
