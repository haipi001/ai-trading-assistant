import React,{useState} from 'react';
import {apiRequest} from './backend-api.js';
import {workspaceSaveBody} from './workspace-sync.js';
import './ai-integration-settings.css';
export function WorkspaceSyncSettings({context,agentOpen,onRestore}){
 const [snapshot,setSnapshot]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const endpoint='/api/v2/workspaces/terminal-main';
 async function request(save){if(busy)return;setBusy(true);setError('');try{const value=await apiRequest(endpoint,save?{method:'PUT',body:workspaceSaveBody(context,snapshot?.version||0,agentOpen)}:{});setSnapshot(value);}catch(e){setError(e.status===409?'工作区已被其他页面修改。请先读取最新快照，核对后再保存。':e.status===404?'尚无已保存的工作区。':e.status===401?'请先登录后端会话。':'无法同步工作区，请检查后端连接。');}finally{setBusy(false);}}
 function restore(){try{onRestore(snapshot);}catch(e){setError(e.message);}}
 return <section className="ai-integration-settings"><p>保存当前页面、标的、平台、周期及研究侧栏开关。读取仅供核对，点击恢复后才应用；不保存密钥、行情文件或交易授权。</p><p>当前：{context.page} · {context.symbol||'未选标的'} · {context.venue||'未选平台'} · {context.timeframe||'未选周期'}</p>{snapshot&&<p role="status">已读取版本 {snapshot.version} · {snapshot.context.page} · {snapshot.context.symbol||'未选标的'} · {snapshot.context.venue||'未选平台'} · {snapshot.context.timeframe||'未选周期'}</p>}<div className="integration-actions"><button type="button" disabled={busy} onClick={()=>request(false)}>读取服务器快照</button><button type="button" disabled={busy} onClick={()=>request(true)}>保存当前工作区</button><button type="button" disabled={busy||!snapshot} onClick={restore}>恢复已读取工作区</button></div>{error&&<p role="alert">{error}</p>}</section>;
}
