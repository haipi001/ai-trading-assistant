import {BacktestReplyHistory} from './backtest-reply-history.jsx';
import {backtestAttachment} from './research-backtest.js';
import React,{useEffect,useRef,useState} from 'react';
import {apiRequest} from './backend-api.js';
import {getBackendSession,getSessionIdentity} from './backend-session.js';
import {tradingContextIdentity} from './terminal-trading-policy.js';
import {savedBacktests,backtestReviewPacket,backtestReviewQuestion,savedBacktestMaterial} from './saved-backtests.js';
function BacktestSummary({results}){
 const metrics=results?.metrics,source=results?.data_contract;
 const format=value=>typeof value==='number'&&Number.isFinite(value)?String(value):'未记录';
 return <section aria-label="回测结果摘要"><p>引擎状态：{results?.engine_status||'未记录'}；资料来源：{source?.source||'未记录'}；周期：{source?.timeframe||'未记录'}；K线数：{format(source?.candle_count)}。</p>{results?.engine_status==='completed'&&<table><thead><tr><th>指标</th><th>保存值</th></tr></thead><tbody>{[['模拟总收益（%）','total_return_pct'],['最大回撤（%）','max_drawdown_pct'],['模拟成交次数','trade_count'],['受流动性约束成交数','liquidity_constrained_fills']].map(([label,field])=><tr key={field}><th>{label}</th><td>{format(metrics?.[field])}</td></tr>)}</tbody></table>}{Array.isArray(results?.blocking_reasons)&&results.blocking_reasons.length>0&&<><h4 data-terminal-label>阻断原因（原始代码）</h4><ul>{results.blocking_reasons.map((reason,index)=><li key={index}>{String(reason)}</li>)}</ul></>}<p>指标仅为保存的模拟结果，不代表已核验收益或可执行策略；缺失值不补为零。</p></section>;
}
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
 async function restore(run,snapshotId=null){
  if(!current.runs?.some(row=>row.id===run.id)||identity!==getSessionIdentity()||scope!==tradingContextIdentity())return;
  if(snapshotId&&(current.history?.backtest_run_id!==run.id||!current.history?.items.some(item=>item.snapshot_id===snapshotId)))return;
  job.current?.abort();const controller=new AbortController();job.current=controller;
  setState(previous=>({...previous,busy:true,error:'',packet:null,artifact:null}));
  const valid=()=>!controller.signal.aborted&&latest.current===key&&job.current===controller&&identity===getSessionIdentity()&&scope===tradingContextIdentity();
  try{
   const value=await apiRequest('/backtest-runs/'+encodeURIComponent(run.id)+'/research-material'+(snapshotId?'/'+encodeURIComponent(snapshotId):''),{signal:controller.signal});
   if(snapshotId){const artifact=savedBacktestMaterial(value,run,snapshotId);if(valid())setState(previous=>({...previous,busy:false,artifact,packet:artifact.material.research_packet}));}
   else{if(value?.backtest_run_id!==run.id||value.execution_available!==false||typeof value.has_more!=='boolean'||!Array.isArray(value.items)||value.items.length>20||new Set(value.items.map(item=>item?.snapshot_id)).size!==value.items.length||value.items.some(item=>!item||typeof item.snapshot_id!=='string'||!item.snapshot_id||!Number.isFinite(Date.parse(item.created_at))))throw Error('invalid history');if(valid())setState(previous=>({...previous,busy:false,history:value,historyRun:run}));}
  }catch{if(valid())setState(previous=>({...previous,busy:false,error:'历史材料读取失败，可能无权限或材料校验未通过；未创建新快照。'}));}
 }
 function downloadMaterial(){
  if(!current.artifact||identity!==getSessionIdentity()||scope!==tradingContextIdentity())return;
  const blob=new Blob([JSON.stringify(current.artifact,null,2)],{type:'application/json;charset=utf-8'}),url=URL.createObjectURL(blob),anchor=document.createElement('a');
  anchor.href=url;anchor.download='backtest-research-material.json';anchor.click();setTimeout(()=>URL.revokeObjectURL(url),0);
 }
 function review(){
  if(!current.packet||identity!==getSessionIdentity()||scope!==tradingContextIdentity())return;
  try{const detail={includeMarket:false,question:'请审阅此冻结回测的假设、数据缺口与阻断原因，引用[BT1]，不要生成订单或声称重新运行当前脚本。',backtestAttachment:backtestAttachment(current.artifact,{id:current.artifact.material.backtest_run_id,strategy_playbook_id:current.artifact.material.strategy_playbook_id},userId,scope)};window.dispatchEvent(new CustomEvent('ai-trading-assistant-research-intent',{detail}));setState(previous=>({...previous,error:detail.accepted?'已准备到AI面板，请核对文本后手动发送。尚未调用模型。':'AI面板未接收，请重新打开后重试。'}));}
  catch(error){setState(previous=>({...previous,error:error.message}));}
 }
 return <section aria-label="后端保存的回测记录"><h3 data-terminal-label>后端保存的回测记录</h3><p>读取当前用户最近100条，可能包含其他标的和测试导入数据。记录未绑定交易账户；不会运行当前脚本，也不产生订单。来源为本地K线不代表已验证的交易所行情。</p><button disabled={!userId||current.busy} onClick={load}>{current.busy?'正在读取…':'读取后端回测记录'}</button>{!userId&&<p>请先登录以读取本人记录。</p>}{current.error&&<p role="alert">{current.error}</p>}{current.history&&<section aria-label="冻结材料历史"><h4 data-terminal-label>已冻结材料</h4><p>{current.history.items.length} 份{current.history.has_more?' · 仅列出最近20份':''}；打开后重新校验来源。</p>{current.history.items.map(item=><button key={item.snapshot_id} disabled={current.busy} onClick={()=>restore(current.historyRun,item.snapshot_id)}>{item.created_at} · {item.snapshot_id}</button>)}</section>}{current.packet&&<section aria-label="回测研究包预览"><p>快照：{current.artifact.snapshot_id} · 冻结时间：{current.artifact.material.captured_at} · SHA-256：{current.artifact.material.content_hash}</p><h4 data-terminal-label>冻结研究包预览 · {current.packet.packet_status}</h4><pre style={{whiteSpace:'pre-wrap',maxHeight:360,overflow:'auto'}}>{JSON.stringify(current.packet,null,2)}</pre><p>仅准备历史材料，不自动调用AI、不重新运行脚本、不解除阻断。AI草稿为显式提供文本，已冻结来源快照；AI回复尚未接入专用引用校验。</p><button disabled={current.busy} onClick={downloadMaterial}>导出完整冻结材料 JSON</button><button disabled={current.busy} onClick={review}>准备到AI面板审阅</button></section>}{current.runs&&<><p role="status">已读取 {current.runs.length} 条{current.runs.length===100?'，可能还有更早记录':''}。</p>{current.runs.map(run=><details key={run.id}><summary>{run.name} · {run.status} · {run.created_at}</summary><p>日期范围：{run.date_from} 至 {run.date_to}；初始资金：{String(run.initial_capital)}。币种以原配置为准，未换汇。</p><button disabled={current.busy} onClick={()=>prepare(run)}>准备此记录的研究包</button><button disabled={current.busy} onClick={()=>restore(run)}>读取冻结材料历史</button><BacktestReplyHistory run={run}/><h4 data-terminal-label>原配置</h4><pre style={{whiteSpace:'pre-wrap'}}>{JSON.stringify(run.parameters_json,null,2)}</pre><BacktestSummary results={run.results_json}/><h4 data-terminal-label>完整原始结果</h4><pre style={{whiteSpace:'pre-wrap',maxHeight:360,overflow:'auto'}}>{JSON.stringify(run.results_json,null,2)}</pre></details>)}</>}</section>;
}
