import React,{useEffect,useRef,useState} from 'react';
import {apiRequest} from './backend-api.js';
import {strategyHistoryList,strategyHistoryArtifact} from './strategy-research-history.js';
import {ResearchStrategySources} from './research-strategy-ui.jsx';
import {ResearchNewsSources} from './research-news-context.jsx';
export function StrategyResearchHistory({accountId,market,identity}){
 const key=JSON.stringify([identity,accountId,market]),latest=useRef(key);latest.current=key;
 const job=useRef(null),[state,setState]=useState({});const current=state.key===key?state:{};
 useEffect(()=>()=>job.current?.abort(),[key]);
 async function load(row){
  job.current?.abort();const controller=new AbortController();job.current=controller;setState(previous=>({...previous,key,busy:true,error:'',artifact:null}));
  try{const base='/api/v2/workspaces/research/';const value=await apiRequest(row?base+'strategy-history/'+encodeURIComponent(row.snapshot_id):base+'strategy-history?'+new URLSearchParams({account_id:accountId,market}),{signal:controller.signal});
   if(controller.signal.aborted||job.current!==controller||latest.current!==key)return;
   if(!row){strategyHistoryList(value,accountId,market);setState({key,busy:false,items:value.items,hasMore:value.has_more});return;}
   strategyHistoryArtifact(value,row);setState(previous=>({...previous,key,busy:false,artifact:value}));
  }catch{if(!controller.signal.aborted&&job.current===controller&&latest.current===key)setState(previous=>({...previous,key,busy:false,error:'无法读取或核对当前账户的AI策略历史。'}));}
 }
 const artifact=current.artifact,reply=artifact?.validated_reply;
 return <details className="market-research-history"><summary data-terminal-label>已保存的策略 AI研究</summary><p>仅读取此用户、此账户的历史；不会自动把旧材料附到当前问题，不修改当前策略参数或运行状态。</p><button type="button" disabled={current.busy} onClick={()=>load()}>读取此账户的AI策略历史</button>{current.busy&&<p role="status">正在读取…</p>}{current.error&&<p role="alert">{current.error}</p>}{current.items&&<><p>{current.items.length} 条{current.hasMore?' · 仅最近20条':''}</p>{current.items.map(row=><button key={row.snapshot_id} type="button" disabled={current.busy} onClick={()=>load(row)}>{row.reply_status||'结果未确认'} · 上下文 {row.context_version} · {new Date(row.created_at).toLocaleString()}</button>)}</>}{artifact&&<article><blockquote>{artifact.question}</blockquote><p>{reply?.summary||'本条记录没有保存有效AI回复；不代表策略已验证。'}</p>{reply&&<><p>{reply.bullish_case}</p><p>{reply.bearish_case}</p><ul>{reply.key_risks.map((risk,index)=><li key={index}>{risk}</li>)}</ul><p>{reply.suggested_action}</p><p>{reply.limitations}</p></>}<ResearchStrategySources result={{...reply,request_id:artifact.request_id,provided_strategy:artifact.provided_strategy,strategy_context_snapshot_id:artifact.snapshot_id}}/><ResearchNewsSources historical result={{...reply,provided_news:artifact.provided_news,news_context_snapshot_id:artifact.news_context_snapshot_id}}/></article>}</details>;
}
