/** Shared, deterministic research engine. This module has no broker or API dependency. */
export const DEMO_STRATEGY_KEY='terminal-demo-strategies-v1';
export const STRATEGY_TEMPLATES=Object.freeze([
 {id:'trend',name:'均线趋势',kind:'trend',lookback:5,threshold:100,allocation:20,stopLoss:5,takeProfit:10,feeBps:10},
 {id:'breakout',name:'区间突破',kind:'breakout',lookback:5,threshold:100,allocation:15,stopLoss:4,takeProfit:8,feeBps:10},
 {id:'price',name:'价格条件',kind:'price',lookback:5,threshold:100,direction:'above',allocation:10,stopLoss:3,takeProfit:6,feeBps:10},
]);
export function validateStrategy(value){
 if(!value||!['trend','breakout','price'].includes(value.kind))throw Error('请选择有效策略类型');
 const name=String(value.name||'').trim();if(!name||name.length>80)throw Error('策略名称须为1至80字');
 const result={...value,name};
 for(const [key,min,max] of [['lookback',2,30],['threshold',0.000001,1e12],['allocation',0.01,100],['stopLoss',0.01,99],['takeProfit',0.01,1000],['feeBps',0,100]]){
  if(value[key]===''||value[key]===null)throw Error('策略参数不能为空');const n=Number(value[key]);if(!Number.isFinite(n)||n<min||n>max)throw Error(`${key} 须在 ${min} 至 ${max} 之间`);result[key]=n;
 }
 if(!Number.isInteger(result.lookback))throw Error('观察周期必须是整数');
 if(result.kind==='price'&&!['above','below'].includes(result.direction))throw Error('请选择价格条件方向');
 return result;
}
export function demoCandles(market='cex',scenario='trend'){
 const base=market==='stocks'?180:market==='onchain'?2:64000;
 if(!['trend','range','fall'].includes(scenario))throw Error('无效模拟场景');
 return Array.from({length:72},(_,i)=>{const drift=scenario==='trend'?i*.003:scenario==='fall'?-i*.003:0;const close=base*(1+drift+Math.sin(i*.58)*.035);return {time:new Date(Date.UTC(2026,0,1+i)).toISOString().slice(0,10),close,volume:1000+i*17};});
}
export function replayStrategy(input,candles,{capital=10000}={}){
 const rule=validateStrategy(input);
 if(!Array.isArray(candles)||candles.length<rule.lookback+2||!Number.isFinite(capital)||capital<=0)throw Error('回放数据或资金无效');
 let previous='';for(const bar of candles){if(!Number.isFinite(bar.close)||bar.close<=0||typeof bar.time!=='string'||bar.time<=previous)throw Error('行情必须按时间递增且价格有效');previous=bar.time;}
 let cash=capital,qty=0,entry=0,peak=capital,maxDrawdown=0,fees=0;const trades=[],curve=[];const fee=rule.feeBps/10000;
 for(let i=0;i<candles.length;i++){
  const bar=candles[i];let action='',reason='';
  // Signals only use earlier closes and execute at the next bar close.
  if(i>rule.lookback){const signal=candles[i-1].close,history=candles.slice(i-1-rule.lookback,i-1).map(x=>x.close),mean=history.reduce((a,b)=>a+b,0)/history.length;
   const enter=rule.kind==='trend'?signal>mean:rule.kind==='breakout'?signal>Math.max(...history):rule.direction==='above'?signal>=rule.threshold:signal<=rule.threshold;
   const exit=rule.kind==='trend'?signal<mean:rule.kind==='breakout'?signal<Math.min(...history):!enter;
   if(qty&&(signal<=entry*(1-rule.stopLoss/100)||signal>=entry*(1+rule.takeProfit/100)||exit)){action='卖出';reason=signal<=entry*(1-rule.stopLoss/100)?'止损条件':signal>=entry*(1+rule.takeProfit/100)?'止盈条件':'退出条件';const gross=qty*bar.close,cost=gross*fee;cash+=gross-cost;fees+=cost;trades.push({time:bar.time,action,reason,price:bar.close,quantity:qty,fee:cost});qty=0;entry=0;}
   else if(!qty&&enter){action='买入';reason='入场条件';const budget=cash*rule.allocation/100,cost=budget*fee/(1+fee);qty=(budget-cost)/bar.close;cash-=budget;fees+=cost;entry=bar.close;trades.push({time:bar.time,action,reason,price:bar.close,quantity:qty,fee:cost});}
  }
  const equity=cash+qty*bar.close;peak=Math.max(peak,equity);maxDrawdown=Math.max(maxDrawdown,(peak-equity)/peak*100);curve.push({time:bar.time,equity});
 }
 const equity=curve.at(-1).equity;
 return {source:'demo',execution:'READ_ONLY',rule,trades,curve,capital,equity,returnPct:(equity/capital-1)*100,maxDrawdown,fees,openQuantity:qty};
}
export function readDemoStrategies(storage){try{const parsed=JSON.parse(storage.getItem(DEMO_STRATEGY_KEY)||'[]');return Array.isArray(parsed)?parsed.slice(0,50).map(validateStrategy):[];}catch{return [];}}
export function saveDemoStrategy(storage,rows,value){const rule=validateStrategy(value),id=rule.id||globalThis.crypto.randomUUID();const next=[{...rule,id},...rows.filter(row=>row.id!==id)].slice(0,50);storage.setItem(DEMO_STRATEGY_KEY,JSON.stringify(next));return next;}
export const DEMO_AUDIT_KEY='terminal-demo-audit-v1';
export function appendDemoAudit(storage,action,detail){
 const allowed=['strategy_saved','strategy_deleted','strategy_replayed'];if(!allowed.includes(action))throw Error('无效演示日志事件');
 try{let rows;try{rows=JSON.parse(storage.getItem(DEMO_AUDIT_KEY)||'[]');}catch{rows=[];}if(!Array.isArray(rows))rows=[];
 storage.setItem(DEMO_AUDIT_KEY,JSON.stringify([{action,source:'demo',execution:'READ_ONLY',at:new Date().toISOString(),detail},...rows].slice(0,100)));return true;}catch{return false;}
}
