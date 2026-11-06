import React,{useEffect,useRef,useState} from 'react';
import {apiRequest} from './backend-api.js';
import {getSessionIdentity,subscribeBackendSession} from './backend-session.js';
import {noticeUpdate,aceReviewUnavailable} from './ace-status.js';
import './ace-status.css';
export function AceAgentDock({children,open=true,onReviewOrder,initialView='Chat'}){
 const [view,setView]=useState(initialView),[generation,setGeneration]=useState(0),[refresh,setRefresh]=useState(0);
 const [packet,setPacket]=useState(null),[loading,setLoading]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState(''),[showAll,setShowAll]=useState(false),[saving,setSaving]=useState(false);
 const epoch=useRef(0),pending=useRef(false),mutation=useRef(0);
 useEffect(()=>subscribeBackendSession(()=>setGeneration(value=>value+1)),[]);
 useEffect(()=>{setPacket(null);setError('');setMessage('');const version=++epoch.current;
  if(!open||view==='Chat')return;
  const controller=new AbortController(),auth=getSessionIdentity();
  const path=view==='Actions'?'/api/v2/agent/actions':'/api/v2/agent/tasks';
  let requestNumber=0;
  async function load(){const request=++requestNumber,change=mutation.current;setLoading(true);try{const result=await apiRequest(path,{signal:controller.signal});if(version===epoch.current&&request===requestNumber&&change===mutation.current&&getSessionIdentity()===auth){setPacket(result);setError('');}}catch(e){if(!controller.signal.aborted&&version===epoch.current&&request===requestNumber&&change===mutation.current){setPacket(null);setError(e.status===401?'请先登录后端会话。':'后端状态暂不可用；未显示为已连接或已完成。');}}finally{if(version===epoch.current&&request===requestNumber)setLoading(false);}}
  load();const timer=setInterval(load,15000);
  return()=>{controller.abort();clearInterval(timer);epoch.current++;};
 },[open,view,generation,refresh]);
 async function changeState(notice,status){if(pending.current)return;pending.current=true;mutation.current++;setSaving(true);setError('');setMessage('');const version=epoch.current,auth=getSessionIdentity();try{
  const result=await apiRequest(`/api/v2/agent/actions/${encodeURIComponent(notice.action_id)}/state`,{method:'PATCH',body:noticeUpdate(notice,status)});
  if(version!==epoch.current||getSessionIdentity()!==auth)return;
  setPacket(previous=>previous?({...previous,records:previous.records.map(row=>row.action_id===result.action_id?result:row)}):null);setMessage('已更新个人通知状态；没有批准或执行订单。');
 }catch(e){if(version===epoch.current)setError(e.status===409?'订单或通知已变化，请刷新后重新确认。':'通知更新未确认，请刷新核对；订单审批未由此操作改变。');}finally{mutation.current++;pending.current=false;setSaving(false);}}
 const records=packet?.records||[];
 return <section className="ace-agent-dock" aria-label="Ace Agent工作区"><nav aria-label="Ace视图">{['Chat','Team','Tasks','Actions'].map(name=><button type="button" key={name} aria-pressed={view===name} onClick={()=>setView(name)}>{name}</button>)}</nav><div className="ace-chat-slot" hidden={view!=='Chat'}>{children}</div>{view!=='Chat'&&<div className="ace-status-body"><header><b>{view==='Actions'?'待处理订单状态':view==='Team'?'已记录的研究角色':'后端任务记录'}</b><button type="button" disabled={loading||saving} onClick={()=>setRefresh(value=>value+1)}>刷新 Ace 状态</button></header><p>仅显示你的服务端记录；不按当前图表自动筛选，不调用模型。{view==='Actions'?'这是存档状态，审批与执行仍需重新检查。':'运行记录与调度配置不等于后台正在运行；启动、取消和费用控制尚未接入此视图。'}</p>{loading&&!packet&&<p role="status">正在读取后端记录…</p>}{packet&&<small>服务端读取时间 {packet.generated_at} · 可见 {records.length} 项{packet.has_more?' · 还有更多记录，当前为有界列表':''}</small>}{error&&<p role="alert">{error}</p>}{message&&<p role="status">{message}</p>}
 {view==='Actions'&&packet&&<label><input type="checkbox" checked={showAll} onChange={e=>setShowAll(e.target.checked)}/>包含已确认或忽略的通知</label>}
 {packet&&records.length===0&&<p role="status">暂无服务端记录；没有创建模拟进度。</p>}
 {view==='Actions'&&records.filter(row=>showAll||row.status==='OPEN').map(row=><article key={row.action_id}><header><b>{row.title}</b><span>{row.status}</span></header><p>{row.instrument.symbol} · {row.instrument.venue} · {row.instrument.currency} · {row.mode.toUpperCase()}</p><p>{row.account_name} · {row.side} · 数量 {row.quantity??'未指定'} · 限价 {row.limit_price??'未指定'} · 委托金额 {row.notional??'按数量与价格计算'}</p><p>风险 {row.risk_status} · 行为 {row.behavior_status} · 审批 {row.approval_status} · 执行 {row.execution_status}</p><small>来源 OrderDraft {row.source_id}<br/>资料 {row.evidence_ids.length?row.evidence_ids.join('，'):'未记录引用'}<br/>最近复核 {row.last_validation_status||'未记录'} {row.last_validation_at||''}</small>{row.blocking_reasons.map((reason,index)=><p className="ace-blocking" key={index}>{reason}</p>)}<div className="ace-notice-actions"><button type="button" title={aceReviewUnavailable(row)||'只读取草稿，审批/执行仍需另行确认'} disabled={saving||Boolean(aceReviewUnavailable(row))||!onReviewOrder} onClick={()=>{try{onReviewOrder(row);}catch(e){setError(e.message||'无法映射订单来源，请刷新后重试');}}}>在原 Paper 票据审查</button><button type="button" disabled={saving||row.status==='ACKNOWLEDGED'} onClick={()=>changeState(row,'ACKNOWLEDGED')}>确认收到（不批准订单）</button><button type="button" disabled={saving} onClick={()=>changeState(row,row.status==='OPEN'?'DISMISSED':'OPEN')}>{row.status==='OPEN'?'忽略此通知':'恢复未读'}</button></div></article>)}
 {view==='Tasks'&&records.map(row=><article key={row.record_id}><header><b>{row.name}</b><span>{row.status}</span></header><p>{row.record_kind==='agent_run'?'研究运行记录':'调度配置'} · {row.source_id}</p><small>创建 {row.created_at}<br/>结束 {row.completed_at||'未记录'} · 最近调度 {row.last_run_at||'未记录'} {row.last_run_status||''}<br/>输入快照 {row.snapshot_id||'未记录'} · 此状态接口未提供费用</small>{row.error_present&&<p>该运行记录含错误；原始工具输出未在此视图展开。</p>}</article>)}
 {view==='Team'&&<><p>以下角色来自已保存的 AgentRun，不代表已启动常驻研究团队。</p>{records.filter(row=>row.record_kind==='agent_run').map(row=><article key={row.record_id}><b>{row.name}</b><p>记录状态 {row.status} · {row.source_id}</p><small>此状态接口未提供模型与费用；不展示推测成功率。</small></article>)}</>}
 </div>}</section>;
}
