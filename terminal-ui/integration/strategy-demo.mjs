/** Opens the shared strategy workbench in the focused business panel. */
export function installStrategyDemo({bar}) {
 const button=document.createElement('button');button.textContent='通用策略 / 页面演示';bar.append(button);
 const focused=()=>document.querySelector('.qcell.focus iframe[data-terminal-feature]:not([hidden])')||document.querySelector('#view:not(.quadmode) iframe[data-terminal-feature]:not([hidden])');
 const open=frame=>frame?.contentWindow?.postMessage({type:'terminal:feature-demo'},location.origin);
 let pending=false;
 window.addEventListener('message',event=>{if(!pending||event.origin!==location.origin||event.data?.type!=='terminal:feature-ready')return;const frame=focused();if(frame?.dataset.terminalFeature!=='R038'||frame.contentWindow!==event.source)return;pending=false;open(frame);});
 button.onclick=()=>{
  const frame=focused();if(frame){open(frame);return;}
  const status=document.getElementById('desk-status');
  try{const workspace=window.TerminalWorkspace;if(!workspace)throw Error('终端尚未就绪，请稍后重试');const value=workspace.snapshot();value.func='R038';value.panels[value.focus]={func:'R038',sym:''};pending=true;workspace.restore(value);if(status)status.textContent='已打开通用策略演示';}catch(error){pending=false;if(status)status.textContent=error.message;}
 };
}
