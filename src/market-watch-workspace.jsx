import './market-watch-workspace.css';
import React,{useEffect,useMemo,useState} from 'react';
import {observePublicTickers} from './live-market-tickers.js';
export function MarketWatchWorkspace({symbols,venue,marketMode,onVenueChange,onOpenChart,openOverlay}){
 const [result,setResult]=useState(null),[sort,setSort]=useState({field:'turnover',descending:true});
 const identity=`${marketMode}:${venue}:${symbols.join(',')}`;
 useEffect(()=>{setResult(null);if(!symbols.length||marketMode==='stocks')return;return observePublicTickers(venue,symbols,value=>setResult({...value,identity}));},[identity]);
 const data=result?.identity===identity?result:null;
 const rows=useMemo(()=>symbols.map(symbol=>({symbol,quote:data?.quotes?.[symbol]})).sort((a,b)=>{
   const left=a.quote?.[sort.field],right=b.quote?.[sort.field];
   if(left==null||right==null)return left==null?right==null?a.symbol.localeCompare(b.symbol):1:-1;
   return (sort.descending?right-left:left-right)||a.symbol.localeCompare(b.symbol);
 }),[identity,data,sort]);
 const format=value=>value==null?'—':value.toLocaleString('en-US',{maximumFractionDigits:8});
 const order=(field,label)=><button aria-label={`自选按${label}排序`} onClick={()=>setSort(previous=>({field,descending:previous.field===field?!previous.descending:true}))}>{label}{sort.field===field?(sort.descending?' ↓':' ↑'):''}</button>;
 return <div className="list-page market-data-workspace"><div className="channel-title"><h1>我的自选<small> · {symbols.length} 个标的</small></h1><div><select aria-label="自选页面交易所" value={venue} onChange={event=>onVenueChange?.(event.target.value)}>{[...new Set([venue,...(marketMode==='stocks'?[]:['币安','欧易OKX','Hyperliquid','Bitget'])])].map(value=><option key={value}>{value}</option>)}</select><button onClick={()=>openOverlay('addWatch','管理自选')}>＋ 管理自选</button></div></div><p className="market-data-status" data-state={marketMode==='stocks'?'unsupported':data?.status||'loading'} role="status">{marketMode==='stocks'?'股票公开报价尚未接入':data?.source||(!symbols.length?'添加标的后读取行情':'正在读取所选平台报价…')}</p>{symbols.length?<div className="market-data-table-wrap"><table className="market-watch-table"><thead><tr><th>交易对</th><th>平台</th><th>{order('price','最新价')}</th><th>{order('change','24H涨跌')}</th><th>{order('turnover','24H成交额')}</th><th>操作</th></tr></thead><tbody>{rows.map(({symbol,quote})=><tr key={symbol}><td>{symbol}/{marketMode==='stocks'?'USD':'USDT'}</td><td>{venue}</td><td>{format(quote?.price)}</td><td>{quote?`${quote.change>=0?'+':''}${quote.change.toFixed(2)}%`:'—'}</td><td>{format(quote?.turnover)} {marketMode==='stocks'?'USD':'USDT'}</td><td><button aria-label={`查看${symbol}自选图表`} onClick={()=>onOpenChart?.(symbol)}>查看图表</button></td></tr>)}</tbody></table></div>:<div className="market-empty">当前市场暂无自选标的<button onClick={()=>openOverlay('addWatch','添加自选')}>添加自选</button></div>}</div>;
}
