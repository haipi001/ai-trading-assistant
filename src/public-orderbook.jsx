import React,{useState,useEffect} from 'react';
import {observePublicDepth} from './live-market-depth.js';
const number=value=>value.toLocaleString('en-US',{maximumFractionDigits:8});
export function PublicOrderBook({symbol,venue,marketMode,onPrice,showDepthBars,suppliedData}) {
  const key=`${marketMode}:${venue}:${symbol}`;
  const [result,setResult]=useState(null);
  useEffect(()=>{
    if(suppliedData!==undefined)return;
    setResult(null);
    if(marketMode==='stocks')return;
    return observePublicDepth(symbol,venue,data=>setResult({...data,key}));
  },[symbol,venue,marketMode,suppliedData!==undefined]);
  const data=suppliedData!==undefined?suppliedData:result?.key===key?result:null;
  const status=marketMode==='stocks'?'股票公开盘口尚未接入':data?.source||'正在读取公开盘口…';
  if(data?.status!=='connected')return <div className="book-action-panel" role="status">{status}</div>;
  const max=Math.max(...data.asks.map(row=>row.total),...data.bids.map(row=>row.total),1);
  const level=(row,side)=><button key={`${side}-${row.price}`} className={`book ${side==='卖出'?'sell':'buy'}`} title={`点击填入${side}快照价格；不会提交订单`} onClick={()=>onPrice(row.price,side)}>{showDepthBars&&<i className="depth-fill" style={{width:`${row.total/max*100}%`}}/>}<span>{number(row.price)}</span><span>{number(row.quantity)}</span><span>{number(row.total)}</span></button>;
  return <><small className="market-ticker-status" role="status">{status}{data.live?"":" · 非实时推送"}</small><div className="book-head"><span>价格(USDT)</span><span>数量({symbol})</span><span>累计({symbol})</span></div>{[...data.asks].reverse().map(row=>level(row,'卖出'))}<div className="last">买卖价差 {data.asks.length&&data.bids.length?number(data.asks[0].price-data.bids[0].price):'—'}</div>{data.bids.map(row=>level(row,'买入'))}{!data.asks.length&&!data.bids.length&&<p>当前快照没有委托</p>}</>;
}
