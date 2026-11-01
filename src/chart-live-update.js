const supported=new Set(['MA','EMA','BOLL','VWAP','RSI','MACD','KDJ','Volume','价格线','网格线','倒计时','买卖信号','筹码分布','隐藏主图']);
export function canUpdateCurrentCandle(studies,replayMode){return !replayMode&&studies.every(value=>supported.has(value));}
export function candleStructureKey(candles,currentOnly){
 return JSON.stringify(currentOnly?{history:candles.slice(0,-1),lastTime:candles.at(-1)?.time}:candles);
}
