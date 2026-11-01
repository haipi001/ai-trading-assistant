import {periodBounds} from './market-chart-model.js';
import {parseChartTimestamp} from './chart-analysis.js';
export function replayStartIndex(bars,label){
 if(!bars.length)throw new Error('没有可复盘的K线');
 if(!label||label==='数据起点'||label==='最近90天')return Math.min(14,bars.length-1);
 const input=/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?$/.test(label)?`${label.length===16?label+":00":label}Z`:label;
 const time=parseChartTimestamp(input);
 if(time<bars[0].time||time>bars.at(-1).time)throw new Error('起始时间不在已载入K线范围内');
 const index=bars.findIndex(bar=>bar.time>=time);if(index<0)throw new Error('没有匹配的起始K线');return index;
}
export function replayCloseTime(bar,period){return periodBounds(period,bar.time*1000+1).end;}
export function replayVisibleBars(bars,closedThrough,period){return Number.isFinite(closedThrough)?bars.filter(bar=>replayCloseTime(bar,period)<=closedThrough):[];}
export function emptyReplayLedger(){return {quantity:0,average:0,realized:0,trades:[]};}
export function applyReplayTrade(ledger,{side,price,time,quantity=.01}){
 if(!['买入','卖出'].includes(side)||![price,quantity].every(value=>Number.isFinite(value)&&value>0)||!Number.isSafeInteger(time)||time<=0)throw new Error('模拟交易参数无效');
 if(side==='卖出'&&quantity>ledger.quantity+1e-9)throw new Error('模拟持仓不足');
 const next=structuredClone(ledger);
 if(side==='买入'){const total=next.quantity+quantity;next.average=(next.quantity*next.average+quantity*price)/total;next.quantity=Number(total.toFixed(8));}
 else{next.realized+=(price-next.average)*quantity;next.quantity=Number((next.quantity-quantity).toFixed(8));if(next.quantity===0)next.average=0;}
 next.trades.push({side,price,time,quantity});return next;
}
export function replayProfit(ledger,price){return {realized:ledger.realized,unrealized:ledger.quantity?(price-ledger.average)*ledger.quantity:0,total:ledger.realized+(ledger.quantity?(price-ledger.average)*ledger.quantity:0)};}
