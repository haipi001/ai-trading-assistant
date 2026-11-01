import React,{useEffect,useState} from 'react';
import {observePublicTrades} from './live-market-trades.js';
const number=value=>value.toLocaleString('en-US',{maximumFractionDigits:8});
export function PublicTrades({symbol,venue,marketMode,onPrice}) {
  const key=`${marketMode}:${venue}:${symbol}`;
  const [snapshot,setSnapshot]=useState(null);
  useEffect(()=>{
    setSnapshot(null);
    if(marketMode==='stocks')return;
    return observePublicTrades(symbol,venue,data=>setSnapshot({...data,key}));
  },[symbol,venue,marketMode]);
  const data=snapshot?.key===key?snapshot:null;
  if(data?.status!=='connected')return <div className="book-action-panel" role="status">{marketMode==='stocks'?'股票公开成交尚未接入':data?.source||'正在读取公开成交…'}</div>;
  return <div className="recent-trades"><small role="status">{data.source} · {data.live?"重连间隙可能缺失成交":"非连续成交流"} · {venue==='Bitget'?'方向按交易所成交字段':'方向为主动成交方'}</small><header><span>价格(USDT)</span><span>数量({symbol})</span><span>时间(UTC)</span></header>{data.trades.map(row=><button key={row.id} title={`${row.side} · ${new Date(row.time).toISOString()} · 点击仅预填价格，不提交订单`} onClick={()=>onPrice(row.price,row.side)}><b className={row.side==='买入'?'green':'red'}>{number(row.price)}</b><span>{number(row.quantity)}</span><time>{new Date(row.time).toISOString().slice(11,23)}</time></button>)}{!data.trades.length&&<p>当前快照没有成交</p>}</div>;
}
