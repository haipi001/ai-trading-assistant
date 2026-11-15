export const STRATEGY_EXAMPLES = {
  '均线突破': {version:1,name:'双均线趋势',type:'sma_cross',fast:10,slow:30},
  'RSI反转': {version:1,name:'RSI反转',type:'rsi',period:14,buyBelow:30,sellAbove:70},
};
export function compileStrategy(text){
 let s;try{s=JSON.parse(text);}catch{throw Error('脚本必须是策略 JSON；请选择模板或使用 AI 生成。');}
 if(!s||s.version!==1||!['sma_cross','rsi'].includes(s.type))throw Error('支持 version:1 的 sma_cross 或 rsi 策略');
 const integer=(n,min,max)=>Number.isInteger(n)&&n>=min&&n<=max;
 if(s.type==='sma_cross'&&(!integer(s.fast,2,200)||!integer(s.slow,3,300)||s.fast>=s.slow))throw Error('均线参数需满足 2 ≤ fast < slow ≤ 300');
 if(s.type==='rsi'&&(!integer(s.period,2,100)||!Number.isFinite(s.buyBelow)||!Number.isFinite(s.sellAbove)||s.buyBelow<=0||s.sellAbove>=100||s.buyBelow>=s.sellAbove))throw Error('RSI 周期为2–100，阈值满足 0 < buyBelow < sellAbove < 100');
 return s;
}
export function runStrategy(code,bars,{capital=10000,fee=0.1,slippage=0.05}={}){
 const s=compileStrategy(code);
 if(!Number.isFinite(capital)||capital<=0||![fee,slippage].every(x=>Number.isFinite(x)&&x>=0&&x<=5))throw Error('资金必须大于0；费率和滑点为0–5%');
 const warm=s.type==='sma_cross'?s.slow:s.period+1;
 if(!Array.isArray(bars)||bars.length<warm+2||bars.length>100000)throw Error(`至少需要 ${warm+2} 根已收盘K线`);
 bars.forEach((b,i)=>{if(![b.time,b.open,b.high,b.low,b.close].every(Number.isFinite)||Math.min(b.open,b.high,b.low,b.close)<=0||b.high<Math.max(b.open,b.close)||b.low>Math.min(b.open,b.close)||b.low>b.high||(i&&b.time<=bars[i-1].time))throw Error('K线价格或时间顺序无效');});
 let cash=capital,qty=0,entry=null,peak=capital,maxDrawdown=0,pending=null,fees=0;
 const trades=[],equity=[];
 const avg=(i,n)=>bars.slice(i-n+1,i+1).reduce((v,b)=>v+b.close,0)/n;
 const signal=i=>{
  if(i<warm)return null;
  if(s.type==='sma_cross')return avg(i,s.fast)>avg(i,s.slow)?'buy':'sell';
  let gain=0,loss=0;for(let j=i-s.period+1;j<=i;j++){const d=bars[j].close-bars[j-1].close;gain+=Math.max(0,d);loss+=Math.max(0,-d);}
  const rsi=loss===0?(gain===0?50:100):100-100/(1+gain/loss);
  return rsi<s.buyBelow?'buy':rsi>s.sellAbove?'sell':null;
 };
 bars.forEach((b,i)=>{
  if(pending==='buy'&&!qty){const price=b.open*(1+slippage/100);qty=cash/(price*(1+fee/100));const cost=qty*price,commission=cost*fee/100;entry={time:b.time,price,cost:cash};fees+=commission;cash=0;}
  else if(pending==='sell'&&qty){const price=b.open*(1-slippage/100),gross=qty*price,commission=gross*fee/100;cash=gross-commission;fees+=commission;trades.push({...entry,exitTime:b.time,exitPrice:price,quantity:qty,pnl:cash-entry.cost});qty=0;entry=null;}
  const value=cash+qty*b.close;peak=Math.max(peak,value);maxDrawdown=Math.max(maxDrawdown,(peak-value)/peak*100);equity.push({time:b.time,value});pending=signal(i);
 });
 const final=equity.at(-1).value;
 return {strategy:s,capital,fee,slippage,final,returnPct:(final/capital-1)*100,maxDrawdown,fees,trades,equity,openPosition:qty?{...entry,quantity:qty,marketValue:qty*bars.at(-1).close}:null,winRate:trades.length?trades.filter(t=>t.pnl>0).length/trades.length*100:null,bars:bars.length,start:bars[0].time,end:bars.at(-1).time};
}
