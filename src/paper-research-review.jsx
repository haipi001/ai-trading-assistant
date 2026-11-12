import React,{useEffect,useRef,useState} from 'react';
import {apiRequest} from './backend-api.js';
import {getSessionIdentity} from './backend-session.js';
import {tradingContextIdentity} from './terminal-trading-policy.js';
import {researchThesisReviewBody,validateResearchThesisReview} from './paper-research-review.js';
export function PaperResearchReview({report,thesis,disabled}){
 const [decision,setDecision]=useState(''),[summary,setSummary]=useState(''),[confidence,setConfidence]=useState('0.7'),[busy,setBusy]=useState(false),[notice,setNotice]=useState('');
 const pending=useRef(false),mounted=useRef(true),scope=useRef([getSessionIdentity(),tradingContextIdentity()]);
 useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;};},[]);
 const current=()=>mounted.current&&scope.current[0]===getSessionIdentity()&&scope.current[1]===tradingContextIdentity();
 async function save(){
  if(pending.current||!current())return;
  let body;try{body=researchThesisReviewBody(thesis.id,decision,summary,confidence);}catch(error){setNotice(error.message);return;}
  pending.current=true;setBusy(true);setNotice('');
  try{const packet=await apiRequest(`/reports/${encodeURIComponent(report.id)}/review-thesis`,{method:'POST',body});if(!current())return;validateResearchThesisReview(packet,report,thesis.id,decision);setNotice(decision==='invalidates'?'已记录假设失效。请停止沿用旧假设，重新读取并修订；不会创建订单。':decision==='weakens'?'已记录假设削弱，假设已转为监控状态。重新读取并修订后再预览计划；不会创建订单。':'已保存人工审阅。核对数量、价格和理由后，可单独预览研究计划；不会自动创建订单。');}
  catch(error){if(current())setNotice(error.local?error.message:error.status===403?'当前角色无人工审阅权限。':'人工审阅保存未确认，请重新读取证据后再继续。');}
  finally{pending.current=false;if(current())setBusy(false);}
 }
 return <section aria-label="报告与投资假设人工审阅"><h4 data-terminal-label>审阅报告与投资假设</h4><p>{report.summary}</p><p>报告 {report.id} · 来源快照 {report.data_snapshot_id} · {report.agent_name}。报告结论仍需人工核对。</p><details><summary data-terminal-label>查看报告全文与记录来源</summary><p>报告生成时间：{report.created_at||'未记录'}（不代表来源时间）</p><h5 data-terminal-label>支持情景</h5><p>{report.bullish_case||'未提供'}</p><h5 data-terminal-label>反对情景</h5><p>{report.bearish_case||'未提供'}</p><h5 data-terminal-label>关键风险</h5><pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{JSON.stringify(report.key_risks||{},null,2)}</pre><h5 data-terminal-label>报告建议</h5><p>{report.suggested_action||'未提供'}</p><h5 data-terminal-label>局限与未知项</h5><p>{report.limitations||'未提供；没有列出局限不表示不存在风险。'}</p><h5 data-terminal-label>报告输入记录</h5><pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{JSON.stringify(report.input_facts||{},null,2)}</pre><h5 data-terminal-label>来源与引用记录</h5><pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{JSON.stringify(report.evidence||{},null,2)}</pre><p>以上为报告保存的输入与引用记录，未在此重新获取来源或独立核实事实。快照 ID 仅标识记录，不是可交易报价。</p></details><p>假设：{thesis.entry_reason}</p><label>我的判断<select value={decision} disabled={disabled||busy} onChange={event=>setDecision(event.target.value)}><option value="">请选择</option><option value="supports">支持假设</option><option value="weakens">削弱假设</option><option value="invalidates">使假设失效</option></select></label><label>人工审阅理由<textarea value={summary} maxLength={2000} disabled={disabled||busy} onChange={event=>setSummary(event.target.value)}/></label><label>主观判断强度（不替代数据与门禁）<input type="number" min="0" max="1" step="0.05" value={confidence} disabled={disabled||busy} onChange={event=>setConfidence(event.target.value)}/></label><button type="button" disabled={disabled||busy||!decision||summary.trim().length<8} onClick={save}>保存人工审阅，不创建订单</button>{notice&&<p role="status">{notice}</p>}</section>;
}
