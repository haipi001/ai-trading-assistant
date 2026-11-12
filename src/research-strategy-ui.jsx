import React,{useEffect,useRef,useState} from 'react';
import {apiRequest} from './backend-api.js';
import {getSessionIdentity} from './backend-session.js';
import {getTerminalTradingContext,tradingContextIdentity} from './terminal-trading-policy.js';
import {strategySuggestionDraft} from './strategy-suggestion-draft.js';
import {strategyHistoryArtifact} from './strategy-research-history.js';
import {strategyParameterChanges} from './strategy-parameter-changes.js';
export function ResearchStrategyControl({attachment,enabled,onChange,onClear,disabled,valid}){
 if(!attachment)return null;
 return <section className="research-ai-notice"><label><input type="checkbox" checked={enabled} disabled={disabled} onChange={e=>onChange(e.target.checked)}/>附带已保存的策略参数</label><p>{valid?'用户参数草稿，尚未验证市场、费用或回测。':'材料范围已变化或已过期，请重新准备。'}</p><details><summary>查看参数附件</summary><pre>{JSON.stringify(attachment.material.parameters,null,2)}</pre></details><button type="button" disabled={disabled} onClick={onClear}>取消策略准备</button></section>;
}
export function ResearchStrategySources({result}){
 if(!result?.provided_strategy)return null;
 return <details><summary>策略来源 [SP1] · 用户参数</summary><p>快照 {result.strategy_context_snapshot_id} · {result.provided_strategy.captured_at}。不代表策略启动或独立证据。</p><pre>{JSON.stringify(result.provided_strategy.parameters,null,2)}</pre><StrategyParameterSuggestions key={result.strategy_context_snapshot_id} result={result}/></details>;
}

function StrategyParameterSuggestions({result}){
 const changes=result.strategy_parameter_changes||[];
 const [edits,setEdits]=useState(()=>Object.fromEntries(changes.map(c=>[c.field,c.after]))),[busy,setBusy]=useState(false),[notice,setNotice]=useState('');
 const mounted=useRef(true),pending=useRef(false);
 useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;};},[]);
 async function review(){
  if(pending.current)return;
  const principal=getSessionIdentity(),scope=tradingContextIdentity();
  pending.current=true;setBusy(true);setNotice('');
  try{
   const artifact=await apiRequest('/api/v2/workspaces/research/strategy-history/'+encodeURIComponent(result.strategy_context_snapshot_id));
   if(!mounted.current||principal!==getSessionIdentity()||scope!==tradingContextIdentity())return;
   const material=result.provided_strategy;
   strategyHistoryArtifact(artifact,{snapshot_id:result.strategy_context_snapshot_id,request_id:result.request_id,account_id:material.account_id,market:material.market,context_version:material.context_version});
   if(artifact.reply_status!=='ok'||JSON.stringify(artifact.validated_reply.strategy_parameter_changes)!==JSON.stringify(changes)||artifact.provided_strategy.content_hash!==material.content_hash)throw Error('研究记录已变化，请重新读取。');
   const context=getTerminalTradingContext(),draft=strategySuggestionDraft(result,edits,context);
   const detail={draft,principal,scope};window.dispatchEvent(new CustomEvent('terminal:strategy-suggestion-draft',{detail}));
   if(!detail.accepted)throw Error('当前工作区未接收草稿，请重新打开原策略页面。');
  }catch(error){if(mounted.current&&principal===getSessionIdentity()&&scope===tradingContextIdentity())setNotice(error.local?error.message:error.message.startsWith('API ')?'无法核对研究记录，请检查登录和后端连接。':error.message);}
  finally{pending.current=false;if(mounted.current)setBusy(false);}
 }

 if(!changes.length)return <p>没有保存结构化参数修改建议；请先核对证据缺口。</p>;
 try{strategyParameterChanges(changes,result.provided_strategy);}catch{return <p role="alert">参数建议校验失败，不能使用。</p>;}
 const labels={amount:'投入金额',risk:'风险偏好',trigger:'触发条件',invalidation:'失效/停止条件',constraints:'预算与风险约束','grid.lower':'网格下界','grid.upper':'网格上界','grid.intervals':'网格数量','dca.frequency':'DCA频率','dca.first_run_local':'首次计划时间','dca.take_profit_percent':'止盈意向（%）'};
 return <section><h4>待审阅参数建议</h4><p>以下建议尚未应用，不代表回测通过或策略启动。</p><table><thead><tr><th>参数</th><th>原值</th><th>建议值</th><th>理由</th></tr></thead><tbody>{changes.map(c=><tr key={c.field}><th>{labels[c.field]}</th><td>{c.before||'未填写'}</td><td><textarea aria-label={'建议'+labels[c.field]} maxLength={c.field==='constraints'?400:c.field==='risk'?64:c.field==='amount'||c.field==='grid.lower'||c.field==='grid.upper'?30:c.field==='grid.intervals'?3:c.field==='dca.frequency'?8:c.field==='dca.first_run_local'?19:c.field==='dca.take_profit_percent'?30:200} value={edits[c.field]} disabled={busy} onChange={e=>setEdits({...edits,[c.field]:e.target.value})}/></td><td>{c.rationale} [SP1]</td></tr>)}</tbody></table><button type="button" disabled={busy} onClick={review}>{busy?'正在核对来源…':'审阅并另存为新草稿'}</button><p role="status">{notice}</p></section>;
}
