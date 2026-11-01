import {validateMarketBars} from './market-chart-model.js';

// Fixed UTC periods only. Never fill gaps or combine venues/symbols.
export function aggregateMarketCandles(rows,baseSeconds,targetSeconds,now=Date.now()){
 if(!Number.isSafeInteger(baseSeconds)||!Number.isSafeInteger(targetSeconds)||baseSeconds<=0||targetSeconds<=baseSeconds||targetSeconds%baseSeconds||!Number.isFinite(now))throw new Error('Invalid aggregation period');
 const bars=validateMarketBars(rows),groups=new Map(),ratio=targetSeconds/baseSeconds;
 for(const bar of bars){
  if(bar.time%baseSeconds||bar.time>now/1000)throw new Error('Invalid source period alignment');
  const start=Math.floor(bar.time/targetSeconds)*targetSeconds;
  if(!groups.has(start))groups.set(start,[]);
  groups.get(start).push(bar);
 }
 const candles=[];let skipped=0,partial=false;
 for(const [start,group] of groups){
  const current=start<=now/1000&&now/1000<start+targetSeconds;
  const contiguous=group.every((bar,index)=>bar.time===start+index*baseSeconds);
  const expected=current?Math.floor((now/1000-start)/baseSeconds)+1:ratio;
  if(!contiguous||group.length!==expected){skipped++;continue;}
  candles.push({time:start,open:group[0].open,high:Math.max(...group.map(bar=>bar.high)),low:Math.min(...group.map(bar=>bar.low)),close:group.at(-1).close,volume:group.reduce((sum,bar)=>sum+bar.volume,0)});
  if(current)partial=true;
 }
 return {candles:validateMarketBars(candles),skipped,partial};
}
