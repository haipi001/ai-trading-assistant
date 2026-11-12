import React,{useEffect,useRef,useState} from 'react';
import {apiRequest} from './backend-api.js';
import {getSessionIdentity} from './backend-session.js';
import {getTerminalTradingContext,tradingContextIdentity} from './terminal-trading-policy.js';
import {strategyMaterialRequest,strategyMaterialPacket} from './strategy-material.js';
export function StrategyMaterialPreview({form}){
 const [saved,setSaved]=useState(null),[busy,setBusy]=useState(false),[notice,setNotice]=useState('');
 const live=useRef({}),pending=useRef(false),mounted=useRef(true);
 const context=getTerminalTradingContext();
 let request=null;try{request=strategyMaterialRequest(form,context);}catch{}
 const signature=JSON.stringify([getSessionIdentity(),tradingContextIdentity(),request]);live.current={signature};
 useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;};},[]);
 async function prepare(){
  if(pending.current||!request)return;
  pending.current=true;setBusy(true);setNotice('');setSaved(null);
  const expected=signature,identity=getSessionIdentity(),scope=tradingContextIdentity();
  const current=()=>mounted.current&&live.current.signature===expected&&getSessionIdentity()===identity&&tradingContextIdentity()===scope;
  try{
   const packet=strategyMaterialPacket(await apiRequest('/api/v2/workspaces/research/strategy-material',{method:'POST',body:request}),request);
   if(!current())return;
   setSaved({signature:expected,packet});setNotice('已保存私有参数快照；尚未发送给AI。');
  }catch(error){if(current())setNotice(error.status===403?'当前会话没有准备研究材料的权限':error.status===401?'请先登录后端会话':'参数材料保存失败，请核对账户、金额和后端连接后重试。');}
  finally{pending.current=false;if(mounted.current)setBusy(false);}
 }
 const packet=saved?.signature===signature?saved.packet:null;
 return <section className="strategy-material-preview"><h4>策略参数研究材料</h4><small>只保存用户参数，未验证行情、回测或收益，不授予策略启动权限。</small><button type="button" disabled={busy||!request} onClick={prepare}>{busy?'正在保存材料…':'准备后端参数快照'}</button>{!request&&<p>请在顶部选择已校验的股票或CEX账户，并填写有效策略参数。</p>}<p role="status">{saved&&!packet?'参数或工作区已变化，请重新准备材料。':notice}</p>{packet&&<details open><summary>查看保存的参数</summary><p>快照 {packet.snapshot_id} · {packet.material.captured_at}</p><pre>{JSON.stringify(packet.material.parameters,null,2)}</pre></details>}{packet&&<button type="button" onClick={()=>{
 const reference={snapshot_id:packet.snapshot_id,...Object.fromEntries(['account_id','market','context_version','content_hash'].map(key=>[key,packet.material[key]]))};
 const detail={question:'请审阅附带的策略参数，解释触发、失效条件和费用滑点及预算缺口，提出待人工审阅的参数建议。',includeMarket:false,strategyAttachment:{material:packet.material,reference,ownerUserId:context.identityUserId}};
 window.dispatchEvent(new CustomEvent('ai-trading-assistant-research-intent',{detail}));
 if(!detail.accepted)setNotice('AI面板未接收，请重新打开后再试。');
 }}>准备 AI 快照审阅</button>}</section>;
}
