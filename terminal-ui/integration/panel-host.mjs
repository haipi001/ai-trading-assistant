import {marketContext,updateContext} from './context.mjs';
import {identities} from './identity-service.mjs';
import {verifiedIdentity,identitiesFor} from './identity-catalog.mjs';
let current=null;
const entries=new Map((window.TERMINAL_FEATURES||[]).map(item=>[item.code,item]));
const locks=new Map();
function frames(){return [...document.querySelectorAll('iframe[data-terminal-feature]')];}
function panelKey(frame){return `${frame.closest('.qcell')?.dataset.cell||'main'}:${frame.dataset.terminalFeature}`;}
function effective(frame){
 const locked=locks.get(panelKey(frame));if(!locked)return current;
 const compatible=current&&locked.market===current.market&&locked.accountId===current.accountId&&locked.walletId===current.walletId;
 return {...locked,executionMode:compatible&&current.executionMode==='PAPER'?'PAPER':'READ_ONLY',authorizationVersion:current?.contextVersion};
}
function runtimeContext(frame){const context=effective(frame);if(!context)return null;const catalog=identities.snapshot(),verified=verifiedIdentity(context,catalog);return {...context,...verified,identityUserId:catalog?.userId||null,executionMode:context.executionMode==='PAPER'&&verified.paperEligible?'PAPER':'READ_ONLY'};}
function send(frame){const target=entries.get(frame.dataset.terminalFeature),context=runtimeContext(frame);if(context&&target)frame.contentWindow?.postMessage({type:'terminal:feature-context',target,context:structuredClone(context),appearance:{colorMode:document.documentElement.dataset.terminalColorMode||'dark',palette:document.getElementById('thbtn')?.dataset.theme||'AMBER'}},location.origin);}
window.addEventListener('terminal:identity-options',()=>frames().forEach(send));
window.addEventListener('terminal:session-changed',()=>{for(const [key,context] of locks)locks.set(key,{...context,accountId:'',walletId:'',executionMode:'READ_ONLY'});frames().forEach(send);window.dispatchEvent(new CustomEvent('terminal:panel-locks'));});
window.addEventListener('terminal:appearance',()=>frames().forEach(frame=>frame.contentWindow?.postMessage({type:'terminal:feature-appearance',appearance:{colorMode:document.documentElement.dataset.terminalColorMode||'dark',palette:document.getElementById('thbtn')?.dataset.theme||'AMBER'}},location.origin)));
window.addEventListener('message',event=>{if(event.origin!==location.origin||event.data?.type!=='terminal:feature-appearance-request'||!frames().some(frame=>frame.contentWindow===event.source)||!['dark','light'].includes(event.data.colorMode))return;window.dispatchEvent(new CustomEvent('terminal:appearance-request',{detail:{colorMode:event.data.colorMode}}));});
function controls(){for(const frame of frames()){if(frame.previousElementSibling?.dataset.panelContext)continue;const row=document.createElement('div');row.className='integration-feature-tabs';row.dataset.panelContext='true';const button=document.createElement('button');const sync=()=>{const snapshot=locks.get(panelKey(frame));button.textContent=snapshot?`已锁定 ${snapshot.instrumentId||snapshot.contractAddress||snapshot.market} · 解除锁定`:'跟随全局 · 锁定本面板';button.setAttribute('aria-pressed',String(Boolean(snapshot)));};button.onclick=event=>{event.stopPropagation();const key=panelKey(frame);if(locks.has(key))locks.delete(key);else if(current)locks.set(key,structuredClone(current));sync();send(frame);window.dispatchEvent(new CustomEvent('terminal:panel-locks'));window.dispatchEvent(new CustomEvent('terminal:focus-context'));};sync();row.append(button);frame.before(row);}}
window.addEventListener('terminal:context',event=>{current=structuredClone(event.detail);frames().forEach(send);});
window.addEventListener('message',event=>{if(event.origin!==location.origin||event.data?.type!=='terminal:feature-ready')return;const frame=frames().find(item=>item.contentWindow===event.source);if(frame){controls();send(frame);}});
window.addEventListener('terminal:research-request',event=>{const focused=document.querySelector('.qcell.focus iframe[data-terminal-feature]')||document.querySelector('#view:not(.quadmode) iframe[data-terminal-feature]');if(!focused)return;focused.contentWindow?.postMessage({type:'terminal:feature-research',question:event.detail.question+'\n研究标识（不是行情证据）：'+JSON.stringify({market:effective(focused)?.market,instrument:effective(focused)?.instrumentId,venue:effective(focused)?.venue,chainId:effective(focused)?.chainId,contractAddress:effective(focused)?.contractAddress,timeframe:effective(focused)?.timeframe}),contextVersion:effective(focused)?.contextVersion},location.origin);});

export function panelLocks(){return [...locks].map(([key,context])=>({key,context:structuredClone(context)}));}
export function restorePanelLocks(values){const next=new Map();for(const item of values)next.set(item.key,marketContext(item.context.market,item.context));locks.clear();for(const [key,context] of next)locks.set(key,context);frames().forEach(frame=>{if(frame.previousElementSibling?.dataset.panelContext)frame.previousElementSibling.remove();});controls();frames().forEach(send);}

window.addEventListener('message',event=>{
 if(event.origin!==location.origin||event.data?.type!=='terminal:feature-edit')return;
 const frame=frames().find(item=>item.contentWindow===event.source),value=event.data;
 if(!frame||value.contextVersion!==effective(frame)?.contextVersion)return;
 const patch={};for(const key of ['instrumentId','venue','timeframe','accountId'])if(typeof value.patch?.[key]==='string')patch[key]=value.patch[key];
 if(patch.accountId&&!identitiesFor(effective(frame),identities.snapshot()).accounts.some(a=>a.id===patch.accountId)){send(frame);return;}
 if(!Object.keys(patch).length)return;
 try{if(locks.has(panelKey(frame))){const context=updateContext({current:effective(frame),memories:{}},patch).current;locks.set(panelKey(frame),context);if(frame.previousElementSibling?.dataset.panelContext)frame.previousElementSibling.remove();controls();send(frame);window.dispatchEvent(new CustomEvent('terminal:panel-locks'));}
 else window.dispatchEvent(new CustomEvent('terminal:context-edit',{detail:patch}));}catch{send(frame);}
});

export function focusedPanelContext(){const frame=document.querySelector('.qcell.focus iframe[data-terminal-feature]')||document.querySelector('#view:not(.quadmode) iframe[data-terminal-feature]');const context=frame?effective(frame):current;return context?structuredClone(context):null;}
window.addEventListener('message',event=>{if(event.origin!==location.origin||event.data?.type!=='terminal:feature-focus')return;const frame=frames().find(item=>item.contentWindow===event.source);const cell=frame?.closest('.qcell');if(cell&&!cell.classList.contains('focus'))window.TerminalWorkspace?.focus(Number(cell.dataset.cell));window.dispatchEvent(new CustomEvent('terminal:focus-context'));});
