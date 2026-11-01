import {validateMarketBars} from './market-chart-model.js';
export function heikinAshiBars(rows){
 const bars=validateMarketBars(rows),result=[];
 for(const bar of bars){const previous=result.at(-1),open=previous?(previous.open+previous.close)/2:(bar.open+bar.close)/2,close=(bar.open+bar.high+bar.low+bar.close)/4;result.push({...bar,open,close,high:Math.max(bar.high,open,close),low:Math.min(bar.low,open,close)});}
 return result;
}
// AiCoin chart-core bb.getOpen / yb.Draw: previous close forms the next body.
export function hlcPlotBars(rows){
 const bars=validateMarketBars(rows);
 return bars.map((bar,index)=>{const open=index?bars[index-1].close:bar.open;return {...bar,open,high:Math.max(bar.high,open,bar.close),low:Math.min(bar.low,open,bar.close)};});
}
export function chartPriceLineRising(bars,type){
 const last=bars.at(-1);if(!last)return false;
 return last.close>(type==='K线图(HLC)'?(bars.at(-2)?.close??0):last.open);
}
export function chartReadoutRising(bars,index,type){
 const bar=bars[index];if(!bar)return false;
 return bar.close>=(type==='K线图(HLC)'&&index>1?bars[index-1].close:bar.open);
}
export function candleChangeMetrics(bars,index){
 const bar=bars[index],previous=bars[index-1];
 if(!bar||!previous||!Number.isFinite(previous.close)||previous.close<=0)return null;
 const change=bar.close-previous.close,percent=change/previous.close*100,amplitude=(bar.high-bar.low)/previous.close*100;
 return [change,percent,amplitude].every(Number.isFinite)?{change,percent,amplitude}:null;
}
export function cursorPriceDifference(price,baseline){
 if(!Number.isFinite(price)||!Number.isFinite(baseline)||baseline<=0)return null;
 const change=price-baseline,percent=change/baseline*100;
 return [change,percent].every(Number.isFinite)?{price,change,percent}:null;
}
