import React,{useEffect,useState} from 'react';
import {observePublicTrades} from './live-market-trades.js';
import {selectLargeTrades} from './large-trades.js';
const format=value=>value.toLocaleString('en-US',{maximumFractionDigits:8});
export function LargeTradesPanel({symbol,venue,marketMode,replayMode,onClose,openOverlay}){
 const [result,setResult]=useState(null),[threshold,setThreshold]=useState('10000'),[side,setSide]=useState('全部');
 const key=`${marketMode}:${venue}:${symbol}:${replayMode}`;
 useEffect(()=>{setResult(null);if(replayMode||marketMode==='stocks')return;return observePublicTrades(symbol,venue,value=>setResult({...value,key}));},[key]);
 const data=result?.key===key?result:null;let rows=[],error='';
 try{if(!threshold.trim())throw new Error('请输入USDT门槛');rows=selectLargeTrades(data?.trades||[],Number(threshold),side);}catch(reason){error=reason.message;}
 return <aside className="chart-feature-panel"><header><div><small>{venue} · {symbol}/USDT · 公开现货</small><h3>大额成交</h3></div><button aria-label="关闭大额成交" onClick={onClose}>关闭</button></header><p role="status">{replayMode?'复盘期间暂停实时成交，避免读取未来成交':marketMode==='stocks'?'股票公开成交尚未接入':data?.source||'正在读取公开成交…'}</p><label>成交额门槛(USDT)<input aria-label="大额成交USDT门槛" type="number" min="0" max="1000000000000" value={threshold} onChange={event=>setThreshold(event.target.value)}/></label><nav>{['全部','买入','卖出'].map(value=><button key={value} className={side===value?'on':''} onClick={()=>setSide(value)}>{value}</button>)}</nav><p>只筛选当前最近20笔成交，非完整大单历史。成交额=成交价×基础币数量；方向按交易所字段，不推断交易者身份。</p>{error&&<p role="alert">{error}</p>}<div className="chart-feature-table">{!error&&rows.map(row=><button key={row.id} onClick={()=>openOverlay('tool','公开成交详情',{description:`${venue} ${symbol}/USDT · ID ${row.id} · ${new Date(row.time).toISOString()} · ${row.side} · 价格${format(row.price)} USDT · 数量${format(row.quantity)} ${symbol} · 成交额${format(row.notional)} USDT`})}><span>{new Date(row.time).toISOString().slice(11,23)}</span><span>{row.side}</span><span>{format(row.price)}</span><span>{format(row.notional)} USDT</span></button>)}</div>{!error&&!rows.length&&<p>当前样本没有符合条件的成交。</p>}</aside>;
}
