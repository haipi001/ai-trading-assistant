import { validatePriceRange } from "./chart-axis.js";
export function validLogicalRange(range) {
  return !!range && Number.isFinite(range.from) && Number.isFinite(range.to) && range.to>range.from && Math.abs(range.from)<1e7 && Math.abs(range.to)<1e7 && range.to-range.from<=100000;
}
export function validateViewport(value) {
  if(value===null || value===undefined) return null;
  if(typeof value.key!=='string'||value.key.length>500||!validLogicalRange(value.logical)||![value.first,value.last].every(time=>Number.isSafeInteger(time)&&time>0)||value.last<value.first) throw new Error('图表视口无效');
  if(value.barCount!==undefined&&(!Number.isSafeInteger(value.barCount)||value.barCount<1||value.barCount>10000))throw new Error('图表视口数据长度无效');
  if(value.timeRange && (!Number.isFinite(value.timeRange.from)||!Number.isFinite(value.timeRange.to)||value.timeRange.from<=0||value.timeRange.to<=value.timeRange.from)) throw new Error('图表日期范围无效');
  if(value.priceRange){validatePriceRange(value.priceRange);if(!["linear","logarithmic"].includes(value.priceMode))throw new Error("价格范围模式无效");}
  return structuredClone(value);
}
export function viewportRange(view, key, candles) {
  if(!view || view.key!==key || !candles.length) return null;
  if(view.first===candles[0].time && view.last===candles.at(-1).time) return {logical:view.logical};
  // Preserve right-edge following only when the user was already at the latest bar.
  if(Number.isSafeInteger(view.barCount)&&view.barCount>0&&validLogicalRange(view.logical)&&view.logical.to>=view.barCount-1&&candles.at(-1).time>view.last&&candles[0].time<=view.last){
    const offset=candles.length-view.barCount;
    return {logical:{from:view.logical.from+offset,to:view.logical.to+offset}};
  }
  if(view.timeRange && view.timeRange.to>=candles[0].time && view.timeRange.from<=candles.at(-1).time) return {time:view.timeRange};
  return null;
}
export function zoomLogicalRange(range,factor) {
  if(!validLogicalRange(range)||!Number.isFinite(factor)||factor<=0) return null;
  const span=Math.min(100000,Math.max(5,(range.to-range.from)*factor));
  return {from:range.to-span,to:range.to};
}
