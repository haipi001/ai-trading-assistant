import {backend} from './backend-service.mjs';
import {panelLocks,restorePanelLocks} from './panel-host.mjs?v=5';
import {WORKSPACE_KEY,MAX_WORKSPACE_BYTES,decodeWorkspace,workspaceSnapshot,workspaceSaveBody,workspaceRestoreBody} from './workspace-state.mjs?v=2';
const startHash=location.hash, startLayout=new URLSearchParams(location.search).get('lay');
export function installWorkspaceControls({host,getState,applyState,getMarketWorkspaces=()=>({}),applyMarketWorkspaces=()=>{}}){
 const section=document.createElement('section');section.innerHTML='<h2>工作区保存与恢复</h2><p><a href="features/local-data-migration.html" target="_blank" rel="noopener">导入/导出旧版本机数据</a> · <a href="http://localhost:3002/local-data-migration.html" target="_blank" rel="noopener">打开旧版数据导出页</a></p><p>旧版已关闭时，请先启动旧版前端，再从原来的浏览器地址导出。</p><p>保存页面布局与研究选择；不会恢复登录或执行权限。</p><button data-workspace="save">保存到本机</button><button data-workspace="restore">恢复本机工作区</button><button data-workspace="undo-restore">恢复上次恢复前布局</button><button data-workspace="export">导出工作区</button><label>导入工作区 <input type="file" accept="application/json,.json" aria-label="导入终端工作区"></label><button data-workspace="cloud-load">读取后端工作区</button><button data-workspace="cloud-save">保存到后端</button><p role="status" data-workspace-status>工作区偏好自动保存在本机。</p>';host.append(section);
 const status=section.querySelector('[data-workspace-status]');let busy=false,applying=false,timer=null,cloudVersion=null,cloudIdentity=null;
 const root=()=>{if(!window.TerminalWorkspace)throw Error('终端尚未就绪');return window.TerminalWorkspace;};
 const identityMatches=identity=>identity.startsWith('local:')?!backend.identity():identity===backend.identity();
 async function workspaceIdentity(){const identity=backend.identity();if(identity)return identity;const value=await backend.request('/api/v2/workspaces/session/context');if(value.auth_mode!=='local'||typeof value.user_id!=='string'||value.execution_authorized!==false)throw Error('请先在后端会话设置中登录');if(backend.identity())throw Error('登录已变化，请重试');return 'local:'+value.user_id;}
 const capture=()=>workspaceSnapshot({state:getState(),layout:root().snapshot(),locks:panelLocks(),marketWorkspaces:getMarketWorkspaces()},root().codes());
 function save(){const value=capture();localStorage.setItem(WORKSPACE_KEY,JSON.stringify(value));return value;}
 function apply(value){applying=true;try{
  // Validate the entire preference packet before touching current state.
  const parsed=decodeWorkspace(JSON.stringify(value),root().codes());
  const before=capture();localStorage.setItem(WORKSPACE_KEY+':before-restore',JSON.stringify(before));
  try{applyMarketWorkspaces(parsed.marketWorkspaces);restorePanelLocks(parsed.locks);applyState(parsed.state);root().restore(parsed.layout);save();}
  catch(error){applyMarketWorkspaces(before.marketWorkspaces);restorePanelLocks(before.locks);applyState(before.state);root().restore(before.layout);throw error;}
 }finally{applying=false;}}
 function schedule(){if(applying||!window.TerminalWorkspace)return;clearTimeout(timer);timer=setTimeout(()=>{try{save();}catch{status.textContent='自动保存失败；当前布局仍在，可以导出备份。';}},120);}
 for(const name of ['terminal:context','terminal:layout-changed','terminal:panel-locks'])window.addEventListener(name,schedule);
 section.querySelector('input').onchange=async event=>{const file=event.target.files?.[0];if(!file)return;if(busy){status.textContent='工作区操作进行中，请稍后重试';event.target.value='';return;}busy=true;try{if(file.size>MAX_WORKSPACE_BYTES)throw Error('工作区文件超过512KB');const value=decodeWorkspace(await file.text(),root().codes());apply(value);status.textContent='工作区已导入；原布局已保留恢复前备份，登录与交易权限未恢复。';}catch(error){status.textContent='导入失败：'+error.message;}finally{busy=false;event.target.value='';}};
 section.addEventListener('click',async event=>{const action=event.target.closest('[data-workspace]')?.dataset.workspace;if(!action||busy)return;busy=true;
 try{
  if(action==='save'){save();status.textContent='本机工作区已保存。';}
  if(action==='restore'){const raw=localStorage.getItem(WORKSPACE_KEY);if(!raw)throw Error('没有已保存的工作区');apply(decodeWorkspace(raw,root().codes()));status.textContent='本机工作区已恢复。';}
  if(action==='undo-restore'){const raw=localStorage.getItem(WORKSPACE_KEY+':before-restore');if(!raw)throw Error('没有恢复前备份');apply(decodeWorkspace(raw,root().codes()));status.textContent='已恢复上次恢复前布局。';}
  if(action==='export'){const blob=new Blob([JSON.stringify(capture(),null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download='terminal-workspace.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);status.textContent='工作区备份已导出。';}
  if(action.startsWith('cloud-')){
   const identity=await workspaceIdentity();
   if(action==='cloud-load'){
    const beforeRead=JSON.stringify(capture());const packet=await backend.request('/api/v2/workspaces/terminal-integrated');if(beforeRead!==JSON.stringify(capture()))throw Error('读取期间本机工作区已变化，保留当前状态，请重试');if(!identityMatches(identity))throw Error('登录已变化，请重新读取');
    const value=workspaceRestoreBody(packet,root().codes());apply(value);cloudVersion=packet.version;cloudIdentity=identity;status.textContent=`后端工作区已恢复 · 版本${cloudVersion}。`;
   }else{
    if(cloudIdentity!==identity||cloudVersion===null){try{const existing=await backend.request('/api/v2/workspaces/terminal-integrated');if(!identityMatches(identity))throw Error('登录已变化');throw Error('后端已有工作区，请先读取后端版本再保存');}catch(error){if(error.status!==404)throw error;cloudVersion=0;}cloudIdentity=identity;}
    if(!identityMatches(identity))throw Error('登录已变化，请重新读取');
    const packet=await backend.request('/api/v2/workspaces/terminal-integrated',{method:'PUT',body:workspaceSaveBody(capture(),cloudVersion,window.TERMINAL_FEATURES||[])});if(!identityMatches(identity))throw Error('登录已变化，请重新读取');cloudVersion=packet.version;status.textContent=`后端工作区已保存 · 版本${cloudVersion}。`;
   }
  }
 }catch(error){if(error.status===409){cloudVersion=null;status.textContent='后端工作区已被其他页面更新，请先读取后端版本；本机状态保留。';}else status.textContent='操作失败：'+error.message;}finally{busy=false;}
 });
 const startup=()=>{try{const raw=localStorage.getItem(WORKSPACE_KEY);if(!raw)return;const value=decodeWorkspace(raw,root().codes());const route=startHash.replace(/^#\/?/,'').split('/')[0];if((route&&route!==value.layout.func)||(startLayout&&startLayout!==value.layout.layout)){applyMarketWorkspaces(value.marketWorkspaces);restorePanelLocks(value.locks);return;}apply(value);status.textContent='已恢复上次工作区；登录与交易权限未恢复。';}catch(error){status.textContent='未应用已保存工作区：'+error.message;}};
 if(window.TerminalWorkspace)startup();else window.addEventListener('DOMContentLoaded',startup,{once:true});
}
