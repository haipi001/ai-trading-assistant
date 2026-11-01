import {decodeMarketDepth} from './market-depth.js';
const seq=value=>typeof value==='string'&&/^\d{1,30}$/.test(value)?BigInt(value):Number.isSafeInteger(value)&&value>=0?BigInt(value):null;
export function parseDepthMessage(text){
 // Preserve exchange sequence integers before JSON.parse rounds them.
 return JSON.parse(text.replace(/("(?:pseq|seq)"\s*:\s*)(\d+)(?=\s*[,}])/g,'$1"$2"'));
}
export function applyBitgetBook(previous,payload,symbol){
 if(payload?.arg?.instType!=='spot'||payload.arg.topic!=='books50'||payload.arg.symbol!==`${symbol}USDT`||!['snapshot','update'].includes(payload.action)||!Array.isArray(payload.data)||payload.data.length!==1)throw new Error('book identity');
 const row=payload.data[0],sequence=seq(row?.seq),prior=seq(row?.pseq);
 if(sequence===null||prior===null||typeof row.ts!=='string'||!/^\d{13}$/.test(row.ts))throw new Error('book sequence');
 const snapshot=payload.action==='snapshot',time=Number(row.ts);
 if(!snapshot){
   if(!previous||prior===0n||sequence<=previous.sequence||time<previous.time)throw new Error('book reset or stale');
   if(previous.initial?!(prior<=previous.sequence&&previous.sequence<=sequence):prior!==previous.sequence)throw new Error('book gap');
 }
 const update=(old,levels,descending)=>{
   if(!Array.isArray(levels)||levels.length>1000)throw new Error('book levels');
   const result=new Map(snapshot?[]:old),seen=new Set();
   for(const level of levels){
     if(!Array.isArray(level)||level.length!==2||level.some(value=>typeof value!=='string'||!/^\d+(?:\.\d+)?$/.test(value)))throw new Error('book level');
     const price=Number(level[0]),quantity=Number(level[1]);
     if(!Number.isFinite(price)||price<=0||!Number.isFinite(quantity)||quantity<0||seen.has(price))throw new Error('book value');
     seen.add(price);if(quantity===0)result.delete(price);else result.set(price,[level[0],level[1]]);
   }
   return new Map([...result].sort((a,b)=>descending?b[0]-a[0]:a[0]-b[0]).slice(0,50));
 };
 const asks=update(previous?.asks,row.a,false),bids=update(previous?.bids,row.b,true);
 const depth=decodeMarketDepth({code:'00000',data:{asks:[...asks.values()].slice(0,20),bids:[...bids.values()].slice(0,20),ts:row.ts}},'bitget');
 return {sequence,time,asks,bids,initial:snapshot,depth};
}
