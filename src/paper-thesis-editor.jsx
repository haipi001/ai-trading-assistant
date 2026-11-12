import {emptyManualThesisForm,readManualThesisDraft,saveManualThesisDraft,paperDraftStorageStatus} from './paper-draft-buffer.js';
import React,{useEffect,useRef,useState} from 'react';
import {apiRequest} from './backend-api.js';
import {getSessionIdentity} from './backend-session.js';
import {tradingContextIdentity} from './terminal-trading-policy.js';
import {manualPaperThesisBody,manualPaperThesisResponse} from './paper-thesis.js';
export function PaperThesisEditor({account,asset,disabled,onCreated,draftScope}){
 const [restored]=useState(()=>{try{return readManualThesisDraft(draftScope,account.id,asset.id);}catch{return null;}});
 const [form,setForm]=useState(()=>restored?Object.fromEntries(Object.keys(emptyManualThesisForm()).map(key=>[key,restored[key]])):emptyManualThesisForm()),[busy,setBusy]=useState(false),[notice,setNotice]=useState(()=>restored?.outcome==='unconfirmed'?'此前保存结果未确认。请先重新读取假设列表核对，不会自动重发。':paperDraftStorageStatus()),[uncertain,setUncertain]=useState(restored?.outcome==='unconfirmed'),[saved,setSaved]=useState(false);
 const mounted=useRef(true),pending=useRef(false),scope=useRef([getSessionIdentity(),tradingContextIdentity()]);
 useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;};},[]);
 const current=()=>mounted.current&&scope.current[0]===getSessionIdentity()&&scope.current[1]===tradingContextIdentity();
 const change=(key,value)=>{const next={...form,[key]:value};setForm(next);try{saveManualThesisDraft(draftScope,account.id,asset.id,next);}catch{setNotice('输入仍在当前页面，但未能暂存；请保持页面并检查浏览器存储。');}};
 async function save(){
  if(pending.current||uncertain||saved||!current())return;
  let body;try{body=manualPaperThesisBody(form,account.id,asset.id);}catch(error){setNotice(error.message);return;}
  try{saveManualThesisDraft(draftScope,account.id,asset.id,form,'unconfirmed');}catch{setNotice('未能暂存保存状态，本次未发送。输入仍保留，请检查浏览器存储。');return;}
  pending.current=true;setBusy(true);setNotice('');
  try{const packet=await apiRequest('/theses/manual-paper',{method:'POST',body});if(!current())return;const thesis=manualPaperThesisResponse(packet,account.id,asset.id);setSaved(true);try{saveManualThesisDraft(draftScope,account.id,asset.id,emptyManualThesisForm());}catch{setUncertain(true);}onCreated(thesis);setNotice('人工假设已保存并选入当前票据。尚未审阅报告、创建订单或授予执行权限。');}
  catch(error){if(current()){if(error.local||!error.status||error.status===408||error.status>=500)setUncertain(true);else{try{saveManualThesisDraft(draftScope,account.id,asset.id,form);}catch{setUncertain(true);}}setNotice(error.local?error.message:error.status===403?'当前角色无创建假设权限。':error.status===422?'账户或标的不兼容，或填写内容未通过校验。':'保存结果未确认。请用票据的“重新读取账户与证据”核对假设列表，避免直接重复创建。');}}
  finally{pending.current=false;if(current())setBusy(false);}
 }
 const locked=disabled||busy||saved||uncertain;
 return <details><summary data-terminal-label>创建人工投资假设</summary><p>未保存输入仅暂存在当前标签页，按用户、市场、标的和账户隔离；退出登录会清理，不恢复审批或执行权限。</p><p>{asset.symbol} · {asset.venue} · {account.name}。仅保存你的研究理由，不调用模型或创建订单；原理由文本不会自动变成数据证据。</p><label>原始理由<textarea maxLength={4000} disabled={locked} value={form.reason} onChange={event=>change('reason',event.target.value)}/></label><label>驱动因素（每行一项）<textarea maxLength={10000} disabled={locked} value={form.drivers} onChange={event=>change('drivers',event.target.value)}/></label><label>失效条件（每行一项）<textarea maxLength={10000} disabled={locked} value={form.invalidation} onChange={event=>change('invalidation',event.target.value)}/></label><label>预期持有期限<input maxLength={64} disabled={locked} value={form.horizon} onChange={event=>change('horizon',event.target.value)}/></label><label>目标或重新评估条件<textarea maxLength={2000} disabled={locked} value={form.target} onChange={event=>change('target',event.target.value)}/></label><label>最大损失容忍度（%）<input type="number" min="0.01" max="100" step="0.1" disabled={locked} value={form.lossPct} onChange={event=>change('lossPct',event.target.value)}/></label><label>主观判断强度（0至1）<input type="number" min="0" max="1" step="0.05" disabled={locked} value={form.confidence} onChange={event=>change('confidence',event.target.value)}/></label><button type="button" disabled={locked} onClick={save}>保存人工假设，不创建订单</button>{uncertain&&!busy&&!saved&&<button type="button" onClick={()=>{try{saveManualThesisDraft(draftScope,account.id,asset.id,form);setUncertain(false);setNotice('已由你确认核对列表；恢复编辑，不会自动提交。');}catch{setNotice('暂存仍不可用，未恢复提交。');}}}>已核对假设列表，恢复编辑</button>}{notice&&<p role="status">{notice}</p>}</details>;
}
