import React,{useEffect,useRef,useState} from 'react';
import {apiRequest} from './backend-api.js';
import {paperReviewHistoryList,paperReviewHistoryArtifact} from './paper-review-research-history.js';
import {ResearchPaperReviewSources} from './research-paper-review-ui.jsx';
import {ResearchNewsSources} from './research-news-context.jsx';
export function PaperReviewResearchHistory({executionId,identity}){
 const key=JSON.stringify([identity,executionId]),latest=useRef(key);latest.current=key;
 const job=useRef(null),[state,setState]=useState({});const current=state.key===key?state:{};
 useEffect(()=>()=>job.current?.abort(),[key]);
 async function load(row){
  job.current?.abort();const controller=new AbortController();job.current=controller;setState(previous=>({...previous,key,busy:true,error:'',artifact:null}));
  try{const base='/production/human-control/llm/chat/';const value=await apiRequest(row?base+'paper-review-context/'+encodeURIComponent(row.snapshot_id):base+'paper-review-contexts?'+new URLSearchParams({execution_id:executionId}),{signal:controller.signal});
   if(controller.signal.aborted||job.current!==controller||latest.current!==key)return;
   if(!row){paperReviewHistoryList(value,executionId);setState({key,busy:false,items:value.items,hasMore:value.has_more});return;}
   paperReviewHistoryArtifact(value,row);setState(previous=>({...previous,key,busy:false,artifact:value}));
  }catch{if(!controller.signal.aborted&&job.current===controller&&latest.current===key)setState(previous=>({...previous,key,busy:false,error:'无法读取或核对当前成交的AI复盘历史。'}));}
 }
 const artifact=current.artifact,reply=artifact?.validated_reply;
 return <details className="market-research-history"><summary data-terminal-label>已保存的Paper AI复盘</summary><p>仅读取此用户、此成交的历史；不会自动把旧材料附到当前问题，不改变人工复盘状态。</p><button type="button" disabled={current.busy} onClick={()=>load()}>读取此成交的AI复盘历史</button>{current.busy&&<p role="status">正在读取…</p>}{current.error&&<p role="alert">{current.error}</p>}{current.items&&<><p>{current.items.length} 条{current.hasMore?' · 仅最近20条':''}</p>{current.items.map(row=><button key={row.snapshot_id} type="button" disabled={current.busy} onClick={()=>load(row)}>{row.reply_status||'结果未确认'} · 上下文 {row.context_version} · {new Date(row.created_at).toLocaleString()}</button>)}</>}{artifact&&<article><blockquote>{artifact.question}</blockquote><p>{reply?.summary||'本条记录没有保存有效AI回复；不代表复盘已完成。'}</p>{reply&&<><p>{reply.bullish_case}</p><p>{reply.bearish_case}</p><ul>{reply.key_risks.map((risk,index)=><li key={index}>{risk}</li>)}</ul><p>{reply.suggested_action}</p><p>{reply.limitations}</p></>}<ResearchPaperReviewSources result={{...reply,provided_paper_review:artifact.provided_paper_review,paper_review_context_snapshot_id:artifact.snapshot_id}}/><ResearchNewsSources historical result={{...reply,provided_news:artifact.provided_news,news_context_snapshot_id:artifact.news_context_snapshot_id}}/></article>}</details>;
}
