import React,{useEffect,useRef,useState} from 'react';
import {apiRequest} from './backend-api.js';
import {getSessionIdentity} from './backend-session.js';
import {tradingContextIdentity} from './terminal-trading-policy.js';
import {validateBacktestResult} from './research-backtest.js';
import {ResearchBacktestSources} from './research-backtest-ui.jsx';
export function BacktestReplyHistory({run}){
 const identity=getSessionIdentity(),scope=tradingContextIdentity(),key=JSON.stringify([identity,scope,run.id]);
 const latest=useRef(key);latest.current=key;const job=useRef(null),[state,setState]=useState({}),current=state.key===key?state:{};
 useEffect(()=>()=>job.current?.abort(),[key]);
 async function load(item=null){
  if(identity!==getSessionIdentity()||scope!==tradingContextIdentity()||item&&!current.items?.some(row=>row.snapshot_id===item.snapshot_id))return;
  job.current?.abort();const controller=new AbortController();job.current=controller;setState({...current,key,busy:true,error:'',artifact:null,reply:null});
  const valid=()=>!controller.signal.aborted&&latest.current===key&&job.current===controller&&identity===getSessionIdentity()&&scope===tradingContextIdentity();
  try{
   const value=await apiRequest('/backtest-runs/'+encodeURIComponent(run.id)+'/research-replies'+(item?'/'+encodeURIComponent(item.snapshot_id):''),{signal:controller.signal});
   if(item){
    if(value?.snapshot_id!==item.snapshot_id||value.execution_available!==false||value.material?.backtest_run_id!==run.id||!['pending','ok','failed'].includes(value.reply_status))throw Error('invalid history');
    let reply=null;
    if(value.reply_status==='ok')reply=validateBacktestResult({...value.validated_reply,context_scope:'owned_frozen_backtest_material',provided_backtest:value.material,backtest_context_snapshot_id:value.snapshot_id},{material:value.material,reference:{snapshot_id:value.source_snapshot_id,backtest_run_id:run.id,content_hash:value.material.content_hash}});
    if(valid())setState(previous=>({...previous,busy:false,artifact:value,reply}));
   }else{
    if(value?.backtest_run_id!==run.id||value.execution_available!==false||typeof value.has_more!=='boolean'||!Array.isArray(value.items)||value.items.length>20||new Set(value.items.map(row=>row?.snapshot_id)).size!==value.items.length||value.items.some(row=>!row||typeof row.snapshot_id!=='string'||!row.snapshot_id||!Number.isFinite(Date.parse(row.created_at))))throw Error('invalid history');
    if(valid())setState({key,busy:false,items:value.items,hasMore:value.has_more});
   }
  }catch{if(valid())setState(previous=>({...previous,busy:false,error:'无法读取或验证历史回复，未自动重发AI请求。'}));}
 }
 return <details><summary data-terminal-label>已保存的回测 AI 研究</summary><button disabled={current.busy} onClick={()=>load()}>读取研究历史</button>{current.error&&<p role="alert">{current.error}</p>}{current.items&&<><p>{current.items.length} 条{current.hasMore?' · 仅最近20条':''}</p>{current.items.map(item=><button disabled={current.busy} key={item.snapshot_id} onClick={()=>load(item)}>{item.reply_status} · {item.created_at}</button>)}</>}{current.artifact&&<article><p>保存状态：{current.artifact.reply_status}；这是历史回复，不会自动附到当前问题。</p>{current.reply?<><p>{current.reply.summary}</p><p>{current.reply.bullish_case}</p><p>{current.reply.bearish_case}</p><ul>{current.reply.key_risks.map((risk,index)=><li key={index}>{risk}</li>)}</ul><p>{current.reply.limitations}</p><p>{current.reply.suggested_action}</p><ResearchBacktestSources result={current.reply}/></>:<p>没有保存有效回复；不代表回测验证成功。</p>}</article>}</details>;
}
