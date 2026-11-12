import {PaperReviewMaterialPreview} from './paper-review-material.jsx';
import {PaperReviewEditor} from './paper-review-editor.jsx';
import './paper-trade-history.css';
import React,{useEffect,useRef,useState} from 'react';
import {apiRequest} from './backend-api.js';
import {getSessionIdentity} from './backend-session.js';
import {getTerminalTradingContext,tradingContextIdentity} from './terminal-trading-policy.js';
import {paperTradeHistory,paperTradeCsv,paperHistoryReview,appendPaperHistory} from './paper-trade-history.js';
export function PaperTradeHistory(){
 const context=getTerminalTradingContext(),principal=getSessionIdentity(),scope=tradingContextIdentity(),key=JSON.stringify([principal,scope]);
 const latest=useRef(key);latest.current=key;
 const job=useRef(null),[state,setState]=useState({});const current=state.key===key?state:{};
 useEffect(()=>()=>job.current?.abort(),[key]);
 const ready=context?.accountVerified&&context.accountId&&['stocks','cex'].includes(context.market);
 async function load(more=false){
  if(!ready||principal!==getSessionIdentity()||scope!==tradingContextIdentity()||(more&&!current.packet?.next_cursor))return;
  job.current?.abort();const controller=new AbortController();job.current=controller;setState(more?{...current,key,busy:true,error:''}:{key,busy:true});
  try{
   const packet=paperTradeHistory(await apiRequest('/api/v2/workspaces/research/paper-trades?'+new URLSearchParams({account_id:context.accountId,market:context.market,...(more?{after:current.packet.next_cursor}:{})}),{signal:controller.signal}),context);
   if(controller.signal.aborted||latest.current!==key||job.current!==controller||principal!==getSessionIdentity()||scope!==tradingContextIdentity())return;
   setState({... (more?current:{}),key,busy:false,packet:appendPaperHistory(more?current.packet:null,packet,context)});
  }catch(error){if(!controller.signal.aborted&&latest.current===key&&job.current===controller&&principal===getSessionIdentity()&&scope===tradingContextIdentity())setState({... (more?current:{}),key,busy:false,error:more&&error.status===422?'分页位置已不可用，请点击读取当前账户重新加载；已加载记录保持不变。':more?'加载更早记录失败，已加载记录保持不变，可重试。':'无法读取当前账户Paper账本，请检查登录、账户权限和后端连接。'});}
 }
 async function loadReview(row){
  if(row.review_available===false)return;
  if(!ready||principal!==getSessionIdentity()||scope!==tradingContextIdentity()||!current.packet?.entries.some(entry=>entry.execution_id===row.execution_id))return;
  job.current?.abort();const controller=new AbortController();job.current=controller;
  setState(previous=>({...previous,key,busy:true,error:'',reviewContext:null}));
  try{
   const reviewContext=paperHistoryReview(await apiRequest('/paper-executions/'+encodeURIComponent(row.execution_id)+'/review-context',{signal:controller.signal}),row,context);
   if(controller.signal.aborted||latest.current!==key||job.current!==controller||principal!==getSessionIdentity()||scope!==tradingContextIdentity())return;
   setState(previous=>({...previous,key,busy:false,reviewContext}));
  }catch(error){if(!controller.signal.aborted&&latest.current===key&&job.current===controller&&principal===getSessionIdentity()&&scope===tradingContextIdentity())setState(previous=>({...previous,key,busy:false,error:error.status===409?'此历史成交的日志或复盘记录不完整，不能准备AI材料；成交记录保持原样。':'无法读取与此成交对应的日志和复盘，请重新读取当前账户记录。'}));}
 }
 function download(){if(principal!==getSessionIdentity()||scope!==tradingContextIdentity()||!current.packet)return;const blob=new Blob([paperTradeCsv(current.packet)],{type:'text/csv;charset=utf-8'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='paper-trades.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),0);}
 return <section className="paper-ledger-history"><h3>当前账户 Paper 成交记录</h3><p>来自服务端应用账本，非交易所实盘成交；只读取此用户、此账户，每页100条，不汇总收益或换汇。分页期间的新成交需重新读取；此列表不是冻结的全账户快照。</p><button disabled={!ready||current.busy} onClick={()=>load()}>{current.busy?'正在读取…':'读取当前账户'}</button><button disabled={!current.packet} onClick={download}>导出已加载记录 CSV</button>{!ready&&<p>请在顶部选择已校验的股票或CEX账户。</p>}{current.error&&<p role="alert">{current.error}</p>}{current.packet&&<><p role="status">{current.packet.entries.length} 条 · 读取时间 {current.packet.captured_at}{current.packet.has_more?' · 还有更早记录，CSV仅包含已加载部分':' · 已读至当前查询范围末尾'}</p>{current.packet.has_more&&<button disabled={current.busy} onClick={()=>load(true)}>加载更早记录</button>}<div style={{overflowX:'auto'}}><table><thead><tr>{['记录时间','标的/场所','方向/状态','数量','均价','费用','已实现盈亏','资产记录币种','复盘'].map(label=><th key={label}>{label}</th>)}</tr></thead><tbody>{current.packet.entries.map(row=><tr key={row.execution_id}><td>{row.recorded_at}</td><td>{row.symbol} · {row.venue}</td><td>{row.side} · {row.status} · Paper</td><td>{row.quantity}</td><td>{row.price??'未记录'}</td><td>{row.fee}</td><td>{row.realized_pnl}</td><td>{row.asset_currency}</td><td><button disabled={current.busy||row.review_available===false} onClick={()=>loadReview(row)}>{row.review_available===false?'日志/复盘记录不完整':'查看成交复盘'}</button></td></tr>)}</tbody></table></div>{!current.packet.entries.length&&<p>此范围没有Paper记录；不代表没有其他账户或实盘交易。</p>}</>}{current.reviewContext&&<section aria-label="历史成交日志与复盘"><h4>{current.reviewContext.journal_entry.title}</h4><pre style={{whiteSpace:'pre-wrap',font:'inherit'}}>{current.reviewContext.journal_entry.notes}</pre><p>保存状态：{current.reviewContext.post_trade_review.status}。这里只修改当前成交的人工复盘；准备AI时需核对顶部标的及场所与原成交一致。</p><PaperReviewMaterialPreview key={key+'|'+current.reviewContext.execution.id+'|'+current.reviewContext.post_trade_review.updated_at} context={current.reviewContext}/><PaperReviewEditor key={key+'|'+current.reviewContext.execution.id} context={current.reviewContext} onSaved={value=>{if(latest.current===key&&principal===getSessionIdentity()&&scope===tradingContextIdentity())setState(previous=>({...previous,reviewContext:value}));}}/></section>}</section>;
}
