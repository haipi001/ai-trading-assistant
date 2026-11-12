import React,{useRef,useEffect,useState} from 'react';
import {apiRequest} from './backend-api.js';
import {portfolioHistoryList} from './research-portfolio.js';
import {portfolioHistoryArtifact} from './portfolio-research-artifact.js';
import {ResearchPortfolioSources} from './research-portfolio-ui.jsx';
import {ResearchNewsSources} from './research-news-context.jsx';
export function PortfolioResearchHistory({context,identity}){
 const key=JSON.stringify([identity,context?.market,context?.accountId]),latest=useRef(key);latest.current=key;
 const job=useRef(null),[state,setState]=useState({}),current=state.key===key?state:{};
 useEffect(()=>()=>job.current?.abort(),[key]);
 if(!context||!['stocks','cex'].includes(context.market))return null;
 async function load(row){
  job.current?.abort();const controller=new AbortController();job.current=controller;setState(old=>({... (old.key===key?old:{}),key,busy:true,error:'',artifact:null}));
  try{
   const base='/production/human-control/llm/chat/';
   const value=await apiRequest(row?base+'portfolio-context/'+encodeURIComponent(row.snapshot_id):base+'portfolio-contexts?'+new URLSearchParams({account_id:context.accountId,market:context.market}),{signal:controller.signal});
   if(controller.signal.aborted||job.current!==controller||latest.current!==key)return;
   if(!row){portfolioHistoryList(value,context);setState({key,busy:false,items:value.items,hasMore:value.has_more});return;}
   portfolioHistoryArtifact(value,row,context);
   setState(old=>({...old,key,busy:false,artifact:value}));
  }catch{if(!controller.signal.aborted&&job.current===controller&&latest.current===key)setState(old=>({...old,key,busy:false,error:'无法读取或验证账户研究历史，请检查会话与来源材料。'}));}
 }
 const a=current.artifact,reply=a?.validated_reply;
 return <details className="market-research-history"><summary>已保存账户账本研究</summary><p>仅读取当前用户、所选账户及市场的历史；不自动附带到新研究，不代表当前持仓。</p><button type="button" disabled={current.busy||!context.accountVerified} onClick={()=>load()}>读取最近账户研究</button>{current.busy&&<p role="status">正在读取…</p>}{current.error&&<p role="alert">{current.error}</p>}{current.items&&<><p>{current.items.length} 条{current.hasMore?' · 仅最近20条':''}</p>{current.items.map(row=><button type="button" key={row.snapshot_id} disabled={current.busy} onClick={()=>load(row)}>{row.reply_status||'未完成'} · 原上下文 {row.context_version} · {new Date(row.created_at).toLocaleString()}</button>)}</>}{a&&<article><h4>历史账本研究</h4><blockquote>{a.question}</blockquote><p>{reply?.summary||'本条记录未保存有效回复。'}</p>{reply&&<><p>有利情景：{reply.bullish_case}</p><p>不利情景：{reply.bearish_case}</p><ul>{reply.key_risks.map((risk,index)=><li key={index}>{risk}</li>)}</ul><p>{reply.suggested_action}</p><p>{reply.limitations}</p></>}<ResearchPortfolioSources historical result={{...reply,provided_portfolio:a.provided_portfolio,portfolio_context_snapshot_id:a.snapshot_id}}/><ResearchNewsSources historical result={{...reply,provided_news:a.provided_news,news_context_snapshot_id:a.news_context_snapshot_id}}/></article>}</details>;
}
