// Explicit local conventions: EMA starts at first close; RSI uses Wilder smoothing;
// KDJ(9,3,3) starts K/D at50. These do not execute imported scripts.
export function ema(values, length) {
  if (!values.length) return [];
  const factor = 2 / (length + 1);
  let previous = values[0];
  return values.map(value => previous = previous + factor * (value - previous));
}
export function calculateOscillators(candles) {
  const close = candles.map(row=>row.close), fast=ema(close,12), slow=ema(close,26);
  const dif=fast.map((value,i)=>value-slow[i]), dea=ema(dif,9);
  const macd=candles.map((row,i)=>({time:row.time,dif:dif[i],dea:dea[i],histogram:2*(dif[i]-dea[i])}));
  const rsi=[];
  let gain=0,loss=0;
  for(let i=1;i<close.length;i++) {
    const delta=close[i]-close[i-1], up=Math.max(delta,0), down=Math.max(-delta,0);
    if(i<=14) { gain+=up/14;loss+=down/14; }
    else { gain=(gain*13+up)/14;loss=(loss*13+down)/14; }
    if(i>=14) rsi.push({time:candles[i].time,value:gain+loss===0?50:100*gain/(gain+loss)});
  }
  let k=50,d=50;
  const kdj=[];
  for(let i=8;i<candles.length;i++) {
    const window=candles.slice(i-8,i+1), high=Math.max(...window.map(row=>row.high)),low=Math.min(...window.map(row=>row.low));
    const rsv=high===low?50:100*(close[i]-low)/(high-low);
    k=(2*k+rsv)/3;d=(2*d+k)/3;
    kdj.push({time:candles[i].time,k,d,j:3*k-2*d});
  }
  return {rsi,macd,kdj};
}
