import {toolBindingStore} from './tool-binding-store.mjs';
import {displayContext} from './display-context.mjs';
import {selectPanelContext} from './panel-context-policy.mjs';
import {validatePageAIIntent} from './page-ai-actions.mjs';
import {marketContext,updateContext} from './context.mjs';
import {identities} from './identity-service.mjs';
import {verifiedIdentity,identitiesFor} from './identity-catalog.mjs';
let current=null;
const entries=new Map((window.TERMINAL_FEATURES||[]).map(item=>[item.code,item]));
const locks=new Map();
const toolBindings=new Map();
let retainedContexts=new WeakMap();
const researchDeliveries=new Map();
for(const eventName of ['terminal:session-changed','terminal:profile-changed'])window.addEventListener(eventName,()=>{for(const pending of researchDeliveries.values())clearTimeout(pending.timer);researchDeliveries.clear();});
window.addEventListener('message',event=>{if(event.origin!==location.origin||event.data?.type!=='terminal:research-received')return;const pending=researchDeliveries.get(event.data.requestId);if(!pending||pending.frame.contentWindow!==event.source)return;clearTimeout(pending.timer);researchDeliveries.delete(event.data.requestId);window.dispatchEvent(new CustomEvent('terminal:research-delivery',{detail:{requestId:event.data.requestId,status:event.data.accepted===true?'received':'rejected'}}));});
function frames(){return [...document.querySelectorAll('iframe[data-terminal-feature]')];}
// Only slot keys can be persisted in a workspace snapshot. Tool drawers and tab
// instances use their own keys, which the saved-workspace schema rejects, so they
// are kept in memory and never exported.
const LOCK_KEY=/^(main|[0-3]):[A-Z][A-Z0-9_]{0,31}$/;
function panelKey(frame){if(frame.hasAttribute('data-terminal-tool-frame'))return 'global-tool-drawer:'+(frame.dataset.toolId||'ai');const legacy=`${frame.closest('.qcell')?.dataset.cell||'main'}:${frame.dataset.terminalFeature}`;const key=frame.dataset.workspaceInstance||legacy;if(key!==legacy&&locks.has(legacy)&&!locks.has(key)){locks.set(key,locks.get(legacy));locks.delete(legacy);}return key;}
function effective(frame){
 if(frame.hasAttribute('data-terminal-tool-frame')){
  const tool=frame.dataset.toolId||'ai';
  if(!toolBindings.has(tool)){try{const saved=toolBindingStore(localStorage,localStorage.getItem('terminal.user')).read(tool);if(saved){toolBindings.set(tool,tool==='trade'?'fixed':saved.binding);if(saved.context&&saved.binding==='fixed')locks.set(panelKey(frame),marketContext(saved.context.market,saved.context));}}catch{}}
  const binding=toolBindings.get(tool)||(tool==='trade'?'fixed':'page');
  const focused=document.querySelector('.qcell.focus iframe[data-terminal-feature]:not([hidden])')||document.querySelector('#view:not(.quadmode) iframe[data-terminal-feature]:not([hidden])');
  const base=binding==='page'&&focused?effective(focused):current;
  if(binding==='fixed'&&!locks.has(panelKey(frame))&&base)locks.set(panelKey(frame),structuredClone(base));
  const resolved=selectPanelContext({current:base,locked:binding==='fixed'?locks.get(panelKey(frame)):null});return resolved?{...resolved,contextSource:binding==='page'?(focused?'focused_business_page':'global_fallback'):binding}:null;
 }
 return selectPanelContext({current,locked:locks.get(panelKey(frame)),retained:retainedContexts.get(frame),supportedMarkets:entries.get(frame.dataset.terminalFeature)?.supportedMarkets||[]});
}
function runtimeContext(frame){const context=effective(frame);if(!context)return null;const catalog=identities.snapshot(),verified=verifiedIdentity(context,catalog);return {...context,...verified,panelId:panelKey(frame),identityUserId:catalog?.userId||null,accountCurrency:verified.accountVerified?catalog.accounts.find(account=>account.id===context.accountId)?.baseCurrency||null:null,executionMode:context.executionMode==='PAPER'&&verified.paperEligible?'PAPER':'READ_ONLY'};}
function send(frame){const target=entries.get(frame.dataset.terminalFeature),context=runtimeContext(frame);if(context&&target){if(!context.marketRetained)retainedContexts.set(frame,structuredClone(context));if(frame.hasAttribute('data-terminal-tool-frame')){const binding=toolBindings.get(frame.dataset.toolId)||(frame.dataset.toolId==='trade'?'fixed':'page');const select=document.getElementById('shell-tool-binding');if(select){select.value=binding;select.disabled=frame.dataset.toolId==='trade';}const note=document.querySelector('.shell-tool-context');if(note)note.textContent=`研究对象：${context.market} · ${context.instrumentId||context.contractAddress||'未选择标的'} · ${context.venue||'场所未选择'}${context.contextSource==='global_fallback'?' · 当前原生页暂无结构化资料，使用全局对象':''} · ${binding==='fixed'?'固定对象':binding==='page'?'跟随当前页面':'跟随全局'}`;}
 frame.dataset.actualMarket=context.market;frame.dataset.actualInstrument=context.instrumentId||context.contractAddress||'';frame.dataset.contextBinding=locks.has(panelKey(frame))?'fixed':'global';frame.dataset.retainedMarket=context.marketRetained?context.market:'';window.dispatchEvent(new CustomEvent('terminal:panel-context-sent',{detail:{instanceId:frame.dataset.workspaceInstance,binding:frame.dataset.contextBinding,context:displayContext(context)}}));frame.contentWindow?.postMessage({type:'terminal:feature-context',active:!frame.hidden,target,context:structuredClone(context),appearance:{colorMode:document.documentElement.dataset.terminalColorMode||'dark',palette:document.getElementById('thbtn')?.dataset.theme||'AMBER'}},location.origin);}}
window.addEventListener('terminal:identity-options',()=>frames().forEach(send));
for(const eventName of ['terminal:session-changed','terminal:profile-changed'])window.addEventListener(eventName,()=>{for(const [key,context] of locks)locks.set(key,{...context,accountId:'',walletId:'',executionMode:'READ_ONLY'});frames().forEach(send);window.dispatchEvent(new CustomEvent('terminal:panel-locks'));});
window.addEventListener('terminal:appearance',()=>frames().forEach(frame=>frame.contentWindow?.postMessage({type:'terminal:feature-appearance',appearance:{colorMode:document.documentElement.dataset.terminalColorMode||'dark',palette:document.getElementById('thbtn')?.dataset.theme||'AMBER'}},location.origin)));
window.addEventListener('message',event=>{if(event.origin!==location.origin||event.data?.type!=='terminal:feature-appearance-request'||!frames().some(frame=>frame.contentWindow===event.source)||!['dark','light'].includes(event.data.colorMode))return;window.dispatchEvent(new CustomEvent('terminal:appearance-request',{detail:{colorMode:event.data.colorMode}}));});
function controls(){for(const frame of frames()){if(frame.hasAttribute('data-terminal-tool-frame'))continue;if(frame.previousElementSibling?.dataset.panelContext)continue;const row=document.createElement('div');row.className='integration-feature-tabs';row.dataset.panelContext='true';const button=document.createElement('button');const sync=()=>{const snapshot=locks.get(panelKey(frame));button.textContent=snapshot?`已锁定 ${snapshot.instrumentId||snapshot.contractAddress||snapshot.market} · 解除锁定`:'跟随全局 · 锁定本面板';button.setAttribute('aria-pressed',String(Boolean(snapshot)));};button.onclick=event=>{event.stopPropagation();const key=panelKey(frame);if(locks.has(key))locks.delete(key);else if(current)locks.set(key,structuredClone(current));sync();send(frame);window.dispatchEvent(new CustomEvent('terminal:panel-locks'));window.dispatchEvent(new CustomEvent('terminal:focus-context'));};sync();row.append(button);frame.before(row);}}
window.addEventListener('terminal:context',event=>{current=structuredClone(event.detail);frames().forEach(send);});
window.addEventListener('message',event=>{if(event.origin!==location.origin||event.data?.type!=='terminal:feature-ready')return;const frame=frames().find(item=>item.contentWindow===event.source);if(frame){controls();send(frame);}});
window.addEventListener('terminal:research-request',event=>{const focused=document.querySelector('.qcell.focus iframe[data-terminal-feature]:not([hidden])')||document.querySelector('#view:not(.quadmode) iframe[data-terminal-feature]:not([hidden])');if(!event.detail||typeof event.detail.question!=='string')return;if(!focused){event.detail.delivery='business_panel_required';return;}try{if(event.detail.pageAction)validatePageAIIntent(event.detail.pageAction,entries.get(focused.dataset.terminalFeature),runtimeContext(focused));}catch{event.detail.delivery='context_changed';return;}if(!focused.contentWindow){event.detail.delivery='panel_unavailable';return;}const requestId=crypto.randomUUID();event.detail.requestId=requestId;researchDeliveries.set(requestId,{frame:focused,timer:setTimeout(()=>{researchDeliveries.delete(requestId);window.dispatchEvent(new CustomEvent('terminal:research-delivery',{detail:{requestId,status:'timeout'}}));},5000)});event.detail.delivery='forwarded';focused.contentWindow.postMessage({type:'terminal:feature-research',requestId,question:event.detail.question+'\n研究标识（不是行情证据）：'+JSON.stringify({market:effective(focused)?.market,instrument:effective(focused)?.instrumentId,venue:effective(focused)?.venue,chainId:effective(focused)?.chainId,contractAddress:effective(focused)?.contractAddress,timeframe:effective(focused)?.timeframe}),contextVersion:effective(focused)?.contextVersion,pageAction:event.detail.pageAction||null},location.origin);});

export function panelLocks(){return [...locks].filter(([key])=>LOCK_KEY.test(key)).map(([key,context])=>({key,context:structuredClone(context)}));}
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

export function focusedPanelContext(){const frame=document.querySelector('.qcell.focus iframe[data-terminal-feature]:not([hidden])')||document.querySelector('#view:not(.quadmode) iframe[data-terminal-feature]:not([hidden])');const context=frame?effective(frame):current;return context?{...structuredClone(context),panelId:frame?panelKey(frame):'native:'+(document.querySelector('.qcell.focus')?.dataset.cell||'main')}:null;}
window.addEventListener('message',event=>{if(event.origin!==location.origin||event.data?.type!=='terminal:feature-focus')return;const frame=frames().find(item=>item.contentWindow===event.source);const cell=frame?.closest('.qcell');if(cell&&!cell.classList.contains('focus'))window.TerminalWorkspace?.focus(Number(cell.dataset.cell));window.dispatchEvent(new CustomEvent('terminal:focus-context'));});

for(const eventName of ['terminal:session-changed','terminal:profile-changed'])window.addEventListener(eventName,()=>{retainedContexts=new WeakMap();locks.clear();toolBindings.clear();for(const frame of frames().filter(x=>x.hidden))frame.remove();});

window.addEventListener('terminal:panel-binding-request',event=>{
 const detail=event.detail;if(!detail||!['fixed','global'].includes(detail.binding)||typeof detail.instanceId!=='string')return;
 const frame=frames().find(item=>item.dataset.workspaceInstance===detail.instanceId);if(!frame)return;
 const restored=detail.context?displayContext(detail.context):null;if(detail.context&&!restored)return;const key=panelKey(frame),context=restored?marketContext(restored.market,restored):effective(frame);if(detail.binding==='fixed'){if(!context)return;locks.set(key,structuredClone(context));}else locks.delete(key);
 frame.dataset.contextBinding=detail.binding;send(frame);window.dispatchEvent(new CustomEvent('terminal:panel-locks'));window.dispatchEvent(new CustomEvent('terminal:focus-context'));
});

window.addEventListener('terminal:panel-activity',()=>frames().forEach(frame=>frame.contentWindow?.postMessage({type:'terminal:feature-activity',active:!frame.hidden},location.origin)));

window.addEventListener('terminal:tool-context-activate',()=>frames().filter(frame=>frame.hasAttribute('data-terminal-tool-frame')).forEach(send));
window.addEventListener('terminal:tool-binding-request',event=>{const {tool,binding}=event.detail||{};if(typeof tool!=='string'||!['page','global','fixed'].includes(binding)||tool==='trade'&&binding!=='fixed')return;const frame=frames().find(item=>item.hasAttribute('data-terminal-tool-frame')&&item.dataset.toolId===tool);if(!frame)return;const context=effective(frame);toolBindings.set(tool,binding);if(binding==='fixed'&&context)locks.set(panelKey(frame),structuredClone(context));else locks.delete(panelKey(frame));send(frame);try{const saved=toolBindingStore(localStorage,localStorage.getItem('terminal.user')).write(tool,{binding,context});if(!saved){const note=document.querySelector('.shell-tool-context');if(note)note.textContent+=' · 绑定保存失败，本次会话有效';}}catch{};});
window.addEventListener('terminal:focus-context',()=>frames().filter(frame=>frame.hasAttribute('data-terminal-tool-frame')).forEach(send));

window.addEventListener('terminal:instance-closed',event=>{const {id,frame}=event.detail||{};if(typeof id!=='string')return;locks.delete(id);for(const [requestId,pending] of researchDeliveries)if(pending.frame===frame){clearTimeout(pending.timer);researchDeliveries.delete(requestId);}});

window.addEventListener('message',event=>{if(event.origin!==location.origin||event.data?.type!=='terminal:feature-dirty'||typeof event.data.dirty!=='boolean')return;const frame=frames().find(item=>item.contentWindow===event.source);if(!frame)return;frame.dataset.cacheDirty=String(event.data.dirty);if(typeof event.data.running==='boolean')frame.dataset.cacheRunning=String(event.data.running);window.dispatchEvent(new CustomEvent('terminal:cache-state'));});

window.addEventListener('terminal:instance-suspended',event=>{for(const [requestId,pending] of researchDeliveries)if(pending.frame===event.detail?.frame){clearTimeout(pending.timer);researchDeliveries.delete(requestId);}});
