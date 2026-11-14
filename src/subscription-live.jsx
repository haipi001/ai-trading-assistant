import {panelVisibility} from './panel-visibility.js';
import {observeVisibleInterval} from './visible-interval.js';
import React,{useCallback,useEffect,useRef,useState} from 'react';
import {subscribeBackendSession} from './backend-session.js';
import {apiRequest} from './backend-api.js';
import {subscriptionStale} from './subscription-live-model.js';
import './subscription-live.css';
export function useSubscriptions(target){
 const [rows,setRows]=useState([]),[busy,setBusy]=useState(false),[error,setError]=useState(''),[clock,setClock]=useState(Date.now());
 const active=useRef(null);
 const refresh=useCallback(()=>active.current?.(),[]);
 useEffect(()=>{
  let stopped=false,pending=false,generation=0,controller=null;const page=panelVisibility(document);
  const load=async()=>{
   if(stopped||pending||page.hidden)return;
   pending=true;const version=generation;controller=new AbortController();setBusy(true);
   try{
    const list=await apiRequest(`/subscriptions/feed/${target}`,{signal:controller.signal});
    if(stopped||version!==generation)return;setRows(list);setError('');
    const due=list.filter(row=>!row.checked_at||Date.now()-Date.parse(row.checked_at)>=row.refresh_seconds*1000);
    // Bounded batches avoid flooding a user's sources; backend coalesces across panels.
    for(let i=0;i<due.length;i+=3){
     await Promise.all(due.slice(i,i+3).map(async row=>{
      try{const updated=await apiRequest(`/subscriptions/${encodeURIComponent(row.id)}/refresh`,{method:'POST',signal:controller.signal,timeout:30000});if(!stopped&&version===generation)setRows(previous=>previous.map(item=>item.id===updated.id?updated:item));}
      catch{if(!stopped&&version===generation)setError('部分订阅刷新未完成，保留上次结果。');}
     }));if(stopped||version!==generation)return;
    }
   }catch{if(!stopped&&version===generation)setError('订阅服务连接失败，当前数据可能已陈旧。');}
   finally{if(!stopped&&version===generation){pending=false;setBusy(false);}}
  };
  const reset=()=>{++generation;controller?.abort();pending=false;setRows([]);setError('');load();};
  const unsubscribe=subscribeBackendSession(reset);
  const visibility=()=>{if(page.hidden){++generation;controller?.abort();pending=false;setBusy(false);}};page.addEventListener('visibilitychange',visibility);
  active.current=load;const stopPolling=observeVisibleInterval(()=>{setClock(Date.now());load();},target==='quotes'?5000:15000,{page});
  window.addEventListener('subscriptions-saved',reset);window.addEventListener('terminal:session-changed',reset);window.addEventListener('backend-session-changed',reset);
  return()=>{unsubscribe();stopped=true;controller?.abort();stopPolling();active.current=null;page.removeEventListener('visibilitychange',visibility);window.removeEventListener('subscriptions-saved',reset);window.removeEventListener('terminal:session-changed',reset);window.removeEventListener('backend-session-changed',reset);};
 },[target]);
 return {rows,busy,error,refresh,clock};
}
const time=value=>value?new Date(value).toLocaleString('zh-CN',{hour12:false}):'未知';
export function SubscriptionQuotes({openOverlay}){
 const {rows,busy,error,refresh,clock}=useSubscriptions('quotes');
 return <section className="subscription-quotes" aria-label="订阅行情"><header><b>订阅行情 · {rows.length} 个来源</b><button disabled={busy} onClick={refresh}>{busy?'读取中…':'刷新订阅'}</button><button onClick={()=>openOverlay('settings','连接与订阅')}>管理来源与字段映射</button></header><p>按配置间隔自动轮询，页面隐藏时暂停；来源本身可能延迟。报价独立展示，不作为下单价格。</p>{error&&<p role="alert">{error}</p>}{!rows.length&&<p>在连接与订阅中添加 JSON 数据接口并配置报价字段，即可在此显示。</p>}{rows.map(row=><section key={row.id}><b>{row.name} · {row.status==='error'?'读取失败，保留旧报价':row.fetched_at?(subscriptionStale(row,clock)?'数据陈旧':'已更新'):'等待首次读取'}</b><small>获取：{time(row.fetched_at)} · 每 {row.refresh_seconds} 秒检查 · {row.last_error||''}</small><div className="subscription-quote-grid">{(row.result?.quotes||[]).map((quote,index)=><article key={`${quote.symbol}:${index}`} className={subscriptionStale(row,clock)?'stale':''}><strong>{quote.symbol}</strong><b>{quote.price.toLocaleString('en-US',{maximumFractionDigits:8})} {quote.currency}</b><span>涨跌幅 {quote.change==null?'未知':`${quote.change}%`} · 成交量 {quote.volume??'未知'}</span><small>{quote.market} / {quote.venue} · 来源时点：{time(quote.timestamp)}{!quote.timestamp?' · 来源未提供有效时点':clock-Date.parse(quote.timestamp)>row.refresh_seconds*2000?' · 来源数据已陈旧':''}</small></article>)}</div>{!row.result?.quotes?.length&&<p>尚无有效报价；请核对 JSON 根路径及价格、标的字段映射。</p>}</section>)}</section>;
}
