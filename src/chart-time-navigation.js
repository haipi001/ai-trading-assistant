import {parseChartTimestamp} from './chart-analysis.js';
export function parseUtcInput(value){return parseChartTimestamp(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?$/.test(value)?`${value.length===16?value+':00':value}Z`:value);}
export function locateChartTime(bars,value,span=60){
 if(!bars.length)throw new Error('当前没有可定位的K线');
 const time=parseUtcInput(value);
 if(time<bars[0].time||time>bars.at(-1).time)throw new Error('该时间超出当前已载入K线范围');
 let low=0,high=bars.length-1;while(low<high){const mid=(low+high)>>1;if(bars[mid].time<time)low=mid+1;else high=mid;}
 const index=low>0&&Math.abs(bars[low-1].time-time)<=Math.abs(bars[low].time-time)?low-1:low;
 const width=Math.min(Math.max(5,span),bars.length+3),from=Math.max(0,Math.min(index-width/2,bars.length+3-width));
 return {logical:{from,to:from+width},actualTime:bars[index].time,index};
}
export function selectChartDates(bars,{start,end}){
 const from=parseChartTimestamp(start),to=parseChartTimestamp(end)+86400-1;
 if(to<from)throw new Error('结束日期不能早于开始日期');
 const first=bars.findIndex(bar=>bar.time>=from&&bar.time<=to);
 if(first<0)throw new Error('所选日期范围没有已载入K线');
 let last=first;while(last+1<bars.length&&bars[last+1].time<=to)last++;
 return {logical:{from:first,to:Math.max(first+.01,last)},first:bars[first].time,last:bars[last].time,count:last-first+1};
}
