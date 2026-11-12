import React,{useEffect,useMemo,useRef,useState} from 'react';
import {apiRequest} from './backend-api.js';
import {getSessionIdentity,getBackendSession} from './backend-session.js';
import {tradingContextIdentity} from './terminal-trading-policy.js';
import {paperReviewBody,paperReviewResponse} from './paper-review.js';
import {paperReviewBufferKey,readPaperReviewBuffer,savePaperReviewBuffer,migratePaperReviewBuffer} from './paper-review-buffer.js';
export function PaperReviewEditor({context,onSaved}){
 const bufferKey=paperReviewBufferKey(getBackendSession()?.user_id,tradingContextIdentity(),context);
 const loaded=useMemo(()=>{let notes=context.post_trade_review.review_json?.terminal_manual_review?.notes||'',error=bufferKey?'':'身份尚未校验，笔记仅保留在当前页面，不能恢复会话草稿。';try{migratePaperReviewBuffer(sessionStorage,getSessionIdentity(),tradingContextIdentity(),context,bufferKey);notes=readPaperReviewBuffer(sessionStorage,bufferKey,notes);}catch{error='会话草稿读取失败，请保留当前页面。';}return {key:bufferKey,notes,error};},[bufferKey]);
 const [buffer,setBuffer]=useState(loaded),active=buffer.key===bufferKey?buffer:loaded,notes=active.notes;
 function setNotes(value){let error=bufferKey?'':'身份尚未校验，笔记仅保留在当前页面，不能恢复会话草稿。';try{savePaperReviewBuffer(sessionStorage,bufferKey,value);}catch{error='会话草稿保存失败，请保留当前页面并手动保存。';}setBuffer({key:bufferKey,notes:value,error});}
 const [busy,setBusy]=useState(false),[notice,setNotice]=useState('');
 const mounted=useRef(true),pending=useRef(false);
 const identity=useRef({session:getSessionIdentity(),workspace:tradingContextIdentity()});
 useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;};},[]);
 function current(){return mounted.current&&identity.current.session===getSessionIdentity()&&identity.current.workspace===tradingContextIdentity();}
 async function save(complete){
  if(pending.current||!current())return;
  let body;try{body=paperReviewBody(context,notes,complete);}catch(error){setNotice(error.message);return;}
  pending.current=true;setBusy(true);setNotice('');
  try{
   const saved=await apiRequest(`/post-trade-reviews/${encodeURIComponent(context.post_trade_review.id)}`,{method:'PATCH',body});
   if(!current())return;
   const verified=paperReviewResponse(saved,context,body);
   try{if(bufferKey)sessionStorage.removeItem(bufferKey);}catch{}
   onSaved(verified);setNotice(complete?'已保存并由你确认完成复盘。':'复盘笔记已保存；完成状态未改变。');
  }catch(error){if(current())setNotice(error.local?error.message:error.status===409?'复盘已被其他页面修改。请重新读取成交复盘后再编辑，当前笔记仍保留。':error.status===403?'当前会话无复盘保存权限。':'保存结果未确认。请重新读取复盘核对，不要直接重复提交。');}
  finally{pending.current=false;if(current())setBusy(false);}
 }
 return <section aria-label="人工编辑成交复盘"><label>我的复盘笔记<textarea value={notes} disabled={busy} maxLength={8000} onChange={event=>setNotes(event.target.value)} placeholder="比较原始理由、实际成交和偏离；记录下次需要改进的事项。"/></label><p>未提交笔记仅缓存在当前浏览器会话，关闭会话后可能清除；服务端记录更新后不会自动套用旧版本草稿。保存只修改此成交的复盘记录，不改变订单、审批、成交或策略规则。完成复盘需由你单独确认。</p><button type="button" disabled={busy||!notes.trim()} onClick={()=>save(false)}>保存复盘笔记</button><button type="button" disabled={busy||!notes.trim()||context.post_trade_review.status==='completed'} onClick={()=>save(true)}>保存并确认完成复盘</button>{active.error&&<p role="alert">{active.error}</p>}{notice&&<p role="status">{notice}</p>}</section>;
}
