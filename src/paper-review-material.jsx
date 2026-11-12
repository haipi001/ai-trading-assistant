import React,{useEffect,useRef,useState} from 'react';
import {apiRequest} from './backend-api.js';
import {getSessionIdentity} from './backend-session.js';
import {getTerminalTradingContext,tradingContextIdentity} from './terminal-trading-policy.js';
import {paperReviewMaterial} from './paper-review-material.js';
const entryLabels={PR1:'模拟成交记录',PR2:'原始订单理由',PR3:'已保存的复盘记录',PR4:'交易日志',PR5:'历史门禁记录'};
function description(entry){if(entry.id==='PR1')return `数量 ${entry.filled_quantity} · 均价 ${entry.average_fill_price??'未记录'} · 费用 ${entry.fee_amount} · 已实现盈亏 ${entry.realized_pnl}（Paper记录）`;if(entry.id==='PR2')return entry.rationale.text+(entry.rationale.truncated?'（内容已截断）':'');if(entry.id==='PR3')return `${entry.status} · ${entry.human_notes?.text||'没有纳入本次材料的终端人工笔记；不代表没有其他复盘记录。'}`;if(entry.id==='PR4')return entry.notes.text+(entry.notes.truncated?'（内容已截断）':'');return '仅记录历史结果，不能替代当前审批。'+entry.gates.map(g=>g.gate_type+'：'+g.status).join('；');}
export function PaperReviewMaterialPreview({context}){
 const [material,setMaterial]=useState(null),[busy,setBusy]=useState(false),[notice,setNotice]=useState('');
 const mounted=useRef(true),pending=useRef(false),scope=useRef([getSessionIdentity(),tradingContextIdentity()]);
 useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;};},[]);
 const current=()=>mounted.current&&scope.current[0]===getSessionIdentity()&&scope.current[1]===tradingContextIdentity();
 async function prepare(){
  if(pending.current||!current())return;
  const terminal=getTerminalTradingContext();
  if(terminal&&(terminal.market==='onchain'||terminal.accountId!==context.journal_entry.account_id)){setNotice('此成交属于其他账户或市场，请回到原工作区。');return;}
  const version=terminal?.contextVersion??0;
  pending.current=true;setBusy(true);setMaterial(null);setNotice('');
  try{const packet=await apiRequest(`/paper-executions/${encodeURIComponent(context.execution.id)}/research-material`,{method:'POST',body:{context_version:version}});if(!current())return;setMaterial(paperReviewMaterial(packet,context,{contextVersion:version,market:terminal?.market}));}
  catch(error){if(current())setNotice(error.local?error.message:error.status===404?'当前后端未提供该成交材料，或记录已不可用。':'未取得有效的复盘材料，请重新读取成交记录。');}
  finally{pending.current=false;if(current())setBusy(false);}
 }
 function openResearch(){if(!material||!current())return;const detail={question:'比较这笔Paper成交的原始理由与已保存复盘，区分记录事实、推断和缺失材料；历史门禁不是当前审批。',paperReviewAttachment:{reference:material.reference,material},includeMarket:false};window.dispatchEvent(new CustomEvent('ai-trading-assistant-research-intent',{detail}));if(!detail.accepted)setNotice('材料不属于当前AI工作区，请回到原账户与标的重新读取。');}
 return <section aria-label="AI复盘材料预览"><button type="button" disabled={busy} onClick={prepare}>读取此成交的AI复盘材料</button><p>只读取并冻结此成交的原始理由、Paper回执、历史门禁及人工复盘。核对材料后可准备AI复盘问题，仍需在AI抽屉勾选附件并手动发送；不会自动调用模型或修改订单。</p>{material&&<details open><summary data-terminal-label>核对冻结的复盘材料</summary><p>冻结时间 {material.captured_at} · 账户 {material.account_id} · {material.instrument?.symbol} · {material.instrument?.venue}</p><p>快照 {material.reference.snapshot_id} · 上下文 v{material.reference.context_version}。记录变化后须重新读取，历史门禁不授予当前执行权限。</p>{material.entries.map(entry=><section key={entry.id}><h5>{entry.id} · <span data-terminal-label>{entryLabels[entry.id]}</span></h5><p style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{description(entry)}</p><details><summary data-terminal-label>查看原始复盘记录</summary><pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{JSON.stringify(entry,null,2)}</pre></details></section>)}<p>{material.limitations}</p><button type="button" disabled={busy} onClick={openResearch}>准备AI复盘问题</button></details>}{notice&&<p role="status">{notice}</p>}</section>;
}
