import React,{useEffect,useRef,useState} from 'react';
import {apiRequest} from './backend-api.js';
import {marketHistoryList,marketHistoryArtifact} from './market-research-history.js';
import {ResearchMarketSources} from './research-market-ui.jsx';
import {ResearchNewsSources} from './research-news-context.jsx';
const statuses={ok:'已保存回复',failed:'调用或响应验证失败'};
export function MarketResearchHistory({symbol='',marketType='',identity=''}){
 const key=JSON.stringify([identity,symbol,marketType]);
 const job=useRef(null),latestKey=useRef(key);latestKey.current=key;
 const [state,setState]=useState({}),current=state.key===key?state:{};
 useEffect(()=>()=>job.current?.abort(),[key]);
 async function load(row){
  job.current?.abort();const controller=new AbortController();job.current=controller;
  setState(old=>({... (old.key===key?old:{}),key,busy:true,error:'',artifact:null}));
  try{
   const base='/production/human-control/llm/chat/';
   const value=await apiRequest(row?base+'market-context/'+encodeURIComponent(row.snapshot_id):base+'market-contexts?'+new URLSearchParams({symbol,market_type:marketType}),{signal:controller.signal});
   if(controller.signal.aborted||job.current!==controller||latestKey.current!==key)return;
   if(row){marketHistoryArtifact(value,row);setState(old=>({...old,key,busy:false,artifact:value}));}
   else{marketHistoryList(value);setState({key,busy:false,items:value.items,hasMore:value.has_more});}
  }catch(error){if(!controller.signal.aborted&&job.current===controller&&latestKey.current===key)setState(old=>({... (old.key===key?old:{}),key,busy:false,error:'无法读取或验证历史材料，请检查后端会话及来源记录。'}));}
 }
 const artifact=current.artifact,reply=artifact?.validated_reply;
 const source=artifact?{...reply,provided_market:artifact.provided_market,market_context_snapshot_id:artifact.snapshot_id,provided_news:artifact.provided_news,news_context_snapshot_id:artifact.news_context_snapshot_id}:null;
 return <details className="market-research-history"><summary>已保存行情研究</summary><p>当前筛选：{symbol||'所有标的'} · {marketType==='stock'?'股票':marketType==='spot'?'加密现货':'所有市场'}。仅读取本用户历史记录，不调用模型，不自动附带到新研究。</p><button type="button" disabled={current.busy} onClick={()=>load()}>读取最近研究记录</button>{current.busy&&<p role="status">正在读取服务端研究记录…</p>}{current.error&&<p role="alert">{current.error}</p>}{current.items&&<><p>{current.items.length} 条{current.hasMore?' · 仅显示最近20条':''}</p>{current.items.map(row=><button type="button" key={row.snapshot_id} disabled={current.busy} onClick={()=>load(row)}>{row.symbol}/{row.quote_currency} · {row.venue} · {row.timeframe} · {row.kind} · {statuses[row.reply_status]||'未保存完整回复'} · {new Date(row.created_at).toLocaleString()}</button>)}</>}{artifact&&<article><h4>历史研究 · {artifact.provided_market.symbol} · {statuses[artifact.reply_status]||'未保存完整回复'}</h4><blockquote>{artifact.question||'此前记录未保存原始问题。'}</blockquote><p>这是原请求的冻结材料，不代表当前报价或当前账户。未读取账户持仓，历史 M1／N1 引用不能替代本次研究材料。原页面：{artifact.workspace_labels?.page||'未记录'}。</p>{reply?<><p>{reply.summary}</p><h4>有利情景</h4><p>{reply.bullish_case}</p><h4>不利情景</h4><p>{reply.bearish_case}</p><h4>风险与缺失项</h4><ul>{reply.key_risks.map((risk,index)=><li key={index}>{risk}</li>)}</ul><p>{reply.suggested_action}</p><p>{reply.limitations}</p>{typeof reply.confidence==='number'&&<p>模型自报置信度 {reply.confidence}，不代表事实核验。</p>}<small>{artifact.provider} / {artifact.model} · {artifact.request_id}</small></>:<p>本条记录未保存有效研究回复。</p>}<ResearchMarketSources result={source} historical/><ResearchNewsSources result={source} historical/></article>}</details>;
}
