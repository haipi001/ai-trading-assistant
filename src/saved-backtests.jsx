import React,{useEffect,useRef,useState} from 'react';
import {apiRequest} from './backend-api.js';
import {getBackendSession,getSessionIdentity} from './backend-session.js';
import {tradingContextIdentity} from './terminal-trading-policy.js';
import {savedBacktests,backtestReviewPacket,backtestReviewQuestion,savedBacktestMaterial} from './saved-backtests.js';
export function SavedBacktests(){
 const userId=getBackendSession()?.user_id,identity=getSessionIdentity(),scope=tradingContextIdentity(),key=JSON.stringify([userId,identity,scope]);
 const latest=useRef(key);latest.current=key;const job=useRef(null),[state,setState]=useState({}),current=state.key===key?state:{};
 useEffect(()=>()=>job.current?.abort(),[key]);
 async function load(){
  if(!userId)return;job.current?.abort();const controller=new AbortController();job.current=controller;setState({key,busy:true});
  const valid=()=>!controller.signal.aborted&&latest.current===key&&job.current===controller&&identity===getSessionIdentity()&&scope===tradingContextIdentity();
  try{const runs=savedBacktests(await apiRequest('/backtest-runs?limit=100',{signal:controller.signal}),userId);if(valid())setState({key,runs});}
  catch{if(valid())setState({key,error:'无法读取后端回测记录，请检查登录、权限和连接；未使用示例替代。'});}
 }
 async function prepare(run){
  if(!current.runs?.some(row=>row.id===run.id)||identity!==getSessionIdentity()||scope!==tradingContextIdentity())return;
  job.current?.abort();const controller=new AbortController();job.current=controller;setState(previous=>({...previous,busy:true,error:'',packet:null,artifact:null}));
  const valid=()=>!controller.signal.aborted&&latest.current===key&&job.current===controller&&identity===getSessionIdentity()&&scope===tradingContextIdentity();
  try{const artifact=savedBacktestMaterial(await apiRequest('/backtest-runs/'+encodeURIComponent(run.id)+'/research-material',{method:'POST',signal:controller.signal}),run);if(valid())setState(previous=>({...previous,busy:false,artifact,packet:artifact.material.research_packet}));}
  catch{if(valid())setState(previous=>({...previous,busy:false,error:'无法准备此回测研究包；未发送AI或启动回测。'}));}
 }
 function review(){
  if(!current.packet||identity!==getSessionIdentity()||scope!==tradingContextIdentity())return;
  try{const detail={includeMarket:false,question:backtestReviewQuestion({...current.packet,source_snapshot_id:current.artifact.snapshot_id,source_content_hash:current.artifact.material.content_hash,source_captured_at:current.artifact.material.captured_at})};window.dispatchEvent(new CustomEvent('ai-trading-assistant-research-intent',{detail}));setState(previous=>({...previous,error:detail.accepted?'已准备到AI面板，请核对文本后手动发送。尚未调用模型。':'AI面板未接收，请重新打开后重试。'}));}
  catch(error){setState(previous=>({...previous,error:error.message}));}
 }
 return <section aria-label="后端保存的回测记录"><h3>后端保存的回测记录</h3><p>读取当前用户最近100条，可能包含其他标的和测试导入数据。记录未绑定交易账户；不会运行当前脚本，也不产生订单。来源为本地K线不代表已验证的交易所行情。</p><button disabled={!userId||current.busy} onClick={load}>{current.busy?'正在读取…':'读取后端回测记录'}</button>{!userId&&<p>请先登录以读取本人记录。</p>}{current.error&&<p role="alert">{current.error}</p>}{current.packet&&<section aria-label="回测研究包预览"><p>快照：{current.artifact.snapshot_id} · 冻结时间：{current.artifact.material.captured_at} · SHA-256：{current.artifact.material.content_hash}</p><h4>冻结研究包预览 · {current.packet.packet_status}</h4><pre style={{whiteSpace:'pre-wrap',maxHeight:360,overflow:'auto'}}>{JSON.stringify(current.packet,null,2)}</pre><p>仅准备历史材料，不自动调用AI、不重新运行脚本、不解除阻断。AI草稿为显式提供文本，已冻结来源快照；AI回复尚未接入专用引用校验。</p><button disabled={current.busy} onClick={review}>准备到AI面板审阅</button></section>}{current.runs&&<><p role="status">已读取 {current.runs.length} 条{current.runs.length===100?'，可能还有更早记录':''}。</p>{current.runs.map(run=><details key={run.id}><summary>{run.name} · {run.status} · {run.created_at}</summary><p>日期范围：{run.date_from} 至 {run.date_to}；初始资金：{String(run.initial_capital)}。币种以原配置为准，未换汇。</p><button disabled={current.busy} onClick={()=>prepare(run)}>准备此记录的研究包</button><h4>原配置</h4><pre style={{whiteSpace:'pre-wrap'}}>{JSON.stringify(run.parameters_json,null,2)}</pre><h4>数据来源、结果及阻断原因</h4><pre style={{whiteSpace:'pre-wrap',maxHeight:360,overflow:'auto'}}>{JSON.stringify(run.results_json,null,2)}</pre></details>)}</>}</section>;
}
