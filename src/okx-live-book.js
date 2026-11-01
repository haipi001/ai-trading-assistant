import {decodeMarketDepth} from './market-depth.js';
export function applyOkxBook(previous,payload,symbol){
 if(payload?.arg?.channel!=='books'||payload.arg.instId!==`${symbol}-USDT`||!['snapshot','update'].includes(payload.action)||!Array.isArray(payload.data)||payload.data.length!==1)throw new Error('book identity');
 const row=payload.data[0],snapshot=payload.action==='snapshot';
 if(!Number.isSafeInteger(row.seqId)||row.seqId<0||!Number.isSafeInteger(row.prevSeqId)||typeof row.ts!=='string'||!/^\d{13}$/.test(row.ts))throw new Error('book sequence');
 if(snapshot?row.prevSeqId!==-1:!previous||row.prevSeqId!==previous.sequence)throw new Error('book continuity');
 if(previous&&!snapshot&&Number(row.ts)<previous.time)throw new Error('old book');
 const update=(side,descending)=>{
   const rows=row[side];if(!Array.isArray(rows)||rows.length>400)throw new Error('book shape');
   const levels=new Map(snapshot?[]:previous[side]),seen=new Set();
   for(const level of rows){
     if(!Array.isArray(level)||level.length<2||typeof level[0]!=='string'||typeof level[1]!=='string'||!/^\d+(?:\.\d+)?$/.test(level[0])||!/^\d+(?:\.\d+)?$/.test(level[1]))throw new Error('book level');
     const price=Number(level[0]),size=Number(level[1]);
     if(!Number.isFinite(price)||price<=0||!Number.isFinite(size)||size<0||seen.has(price))throw new Error('book level');
     seen.add(price);if(size===0)levels.delete(price);else levels.set(price,[level[0],level[1]]);
   }
   return new Map([...levels].sort((a,b)=>descending?b[0]-a[0]:a[0]-b[0]).slice(0,400));
 };
 const asks=update('asks',false),bids=update('bids',true);
 const depth=decodeMarketDepth({code:'0',data:[{ts:row.ts,asks:[...asks.values()].slice(0,20),bids:[...bids.values()].slice(0,20)}]},'okx');
 // OKX retired checksum: continuity uses seqId/prevSeqId, including documented resets.
 return {asks,bids,sequence:row.seqId,time:Number(row.ts),depth};
}
