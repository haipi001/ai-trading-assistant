export function marketHeadline({replayActive=false,replayBar=null,local=false,candle=null,ticker=null}={}) {
  if (replayActive) return fromCandle(replayBar,'复盘原始K线');
  if (local) return fromCandle(candle,'本地CSV');
  if (ticker && Number.isFinite(ticker.price) && ticker.price>0 && Number.isFinite(ticker.change)) return {price:ticker.price,change:ticker.change,source:'公开现货 · 24h涨跌'};
  return fromCandle(candle,'K线快照 · 本根涨跌');
}
function fromCandle(candle,source) {
  if (!candle || !Number.isFinite(candle.close) || candle.close<=0 || !Number.isFinite(candle.open) || candle.open<=0) return {price:null,change:null,source:'暂无对应报价'};
  const change=(candle.close/candle.open-1)*100;
  return {price:candle.close,change:Number.isFinite(change)?change:null,source};
}
