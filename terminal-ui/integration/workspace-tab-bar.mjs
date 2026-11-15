import {displayContext} from './display-context.mjs';
// Actual open pages, separate from the complete function directory.
const container=document.querySelector('.workspace-tabs'),view=document.getElementById('view');
const list=document.createElement('div');list.className='open-workspace-tabs';list.setAttribute('role','tablist');list.setAttribute('aria-label','已打开工作页');container.prepend(list);
let tabStorageBlocked=false;let pages=new Map();let currentId=null;const recentlyClosed=[];
const feedback=document.createElement('span');feedback.setAttribute('role','status');feedback.className='workspace-tab-feedback';container.append(feedback);
const rebuild=document.createElement('button');rebuild.textContent='重建标签列表';rebuild.hidden=true;rebuild.onclick=()=>{if(!confirm('重建将替换未完整恢复的原标签列表，保留当前打开页面；不会删除业务数据。确定继续？'))return;tabStorageBlocked=false;rebuild.hidden=true;persistTabs();};container.append(rebuild);
function persistTabs(){if(tabStorageBlocked){feedback.textContent='原标签配置未完整恢复，已保留原记录；当前标签仅在本次会话有效';return;}try{localStorage.setItem('terminal.open-tabs.v1:'+(localStorage.getItem('terminal.user')||'GUEST'),JSON.stringify([...pages.values()].map(({id,title,snapshot,pinned,fixedContext})=>({id,title,snapshot,pinned:Boolean(pinned),fixedContext:displayContext(fixedContext)}))));}catch{feedback.textContent='标签列表保存失败';}}
function loadTabs(){tabStorageBlocked=false;rebuild.hidden=true;pages.clear();recentlyClosed.length=0;try{const saved=JSON.parse(localStorage.getItem('terminal.open-tabs.v1:'+(localStorage.getItem('terminal.user')||'GUEST'))||'[]');const codes=window.TerminalWorkspace?.codes()||[];if(!Array.isArray(saved))throw Error('invalid');let skipped=false;for(const item of saved){if(typeof item?.id!=='string'||!item.id||item.id.length>200||pages.has(item.id)||typeof item.title!=='string'||!codes.includes(item.snapshot?.func)||!['1','2','4'].includes(item.snapshot?.layout)||!Array.isArray(item.snapshot?.panels)||item.snapshot.panels.length!==4){skipped=true;continue;}pages.set(item.id,{id:item.id,title:item.title.slice(0,100),snapshot:item.snapshot,pinned:item.pinned===true,fixedContext:displayContext(item.fixedContext),frame:null});}if(skipped){tabStorageBlocked=true;rebuild.hidden=false;feedback.textContent='部分标签暂不可恢复，已保留原记录';}}catch{tabStorageBlocked=true;rebuild.hidden=false;feedback.textContent='标签列表读取失败，已保留原记录';}}
function activate(page){try{window.dispatchEvent(new CustomEvent('terminal:activate-instance',{detail:{id:page.id}}));window.TerminalWorkspace.restore(page.snapshot);}catch{feedback.textContent='此标签无法恢复，请从全部功能重新打开';}}
const menu=document.createElement('dialog');menu.className='workspace-tab-menu';menu.setAttribute('aria-label','标签操作');document.body.append(menu);
function closePages(requested){const targets=requested.filter(page=>!page.pinned);if(!targets.length||!confirm(`关闭${targets.length}个页面会丢弃其中未保存的编辑。请先保存需要的内容，确定继续？`))return;const closing=new Set(targets.map(page=>page.id));for(const page of targets){pages.delete(page.id);recentlyClosed.unshift({...page,frame:null});window.dispatchEvent(new CustomEvent('terminal:instance-closed',{detail:{id:page.id,frame:page.frame}}));page.frame?.remove();}recentlyClosed.splice(20);if(closing.has(currentId)){const next=[...pages.values()].at(-1);if(next)activate(next);else{document.getElementById('cmd').value='WEI';document.getElementById('gobtn').click();}}persistTabs();render();}
function showMenu(page){menu.replaceChildren();const add=(text,action,disabled=false)=>{const b=document.createElement('button');b.textContent=text;b.disabled=disabled;b.onclick=()=>{menu.close();action();};menu.append(b);};
 add(page.pinned?'取消固定':'固定标签',()=>{page.pinned=!page.pinned;persistTabs();render();});
 for(const [text,delta] of [['左移',-1],['右移',1]]){const entries=[...pages],index=entries.findIndex(([id])=>id===page.id);add(text,()=>{[entries[index],entries[index+delta]]=[entries[index+delta],entries[index]];pages=new Map(entries);persistTabs();render();},index+delta<0||index+delta>=entries.length);}
 add('关闭标签',()=>closePages([page]),page.pinned);
 const all=[...pages.values()],position=all.indexOf(page);
 add('关闭其他标签',()=>closePages(all.filter(item=>item.id!==page.id)),!all.some(item=>item.id!==page.id&&!item.pinned));
 add('关闭右侧标签',()=>closePages(all.slice(position+1)),!all.slice(position+1).some(item=>!item.pinned));
 add('重新打开最近关闭',()=>{const last=recentlyClosed.shift();if(last){pages.set(last.id,last);activate(last);persistTabs();render();}},!recentlyClosed.length);
 if(page.frame?.isConnected){add('新建同功能实例',()=>{const copy={...page,id:crypto.randomUUID(),pinned:false,frame:null};pages.set(copy.id,copy);activate(copy);persistTabs();});add('固定当前市场与对象',()=>window.dispatchEvent(new CustomEvent('terminal:panel-binding-request',{detail:{instanceId:page.frame.dataset.workspaceInstance,binding:'fixed'}})));add('跟随全局市场与对象',()=>window.dispatchEvent(new CustomEvent('terminal:panel-binding-request',{detail:{instanceId:page.frame.dataset.workspaceInstance,binding:'global'}})));}
 add('取消',()=>{});menu.showModal();
}

function sync(){
 const workspace=window.TerminalWorkspace;if(!workspace)return;const snapshot=workspace.snapshot();
 const activeFrame=view.querySelector(':scope > iframe[data-terminal-feature]:not([hidden])');
 const existing=activeFrame&&!activeFrame.dataset.explicitInstance&&!pages.has(activeFrame.dataset.workspaceInstance)&&[...pages.values()].find(p=>!p.frame&&p.snapshot.func===snapshot.func&&p.snapshot.layout==='1');if(existing)activeFrame.dataset.workspaceInstance=existing.id;
 const id=activeFrame?.dataset.workspaceInstance||`${snapshot.layout}:${snapshot.focus}:${snapshot.func}:${snapshot.sym||''}`;
 const feature=(window.TERMINAL_FEATURES||[]).find(x=>x.code===snapshot.func);
 const title=feature?.label||document.getElementById('phTitle')?.textContent||snapshot.func;
 pages.set(id,Object.assign(pages.get(id)||{},{id,snapshot,title,frame:activeFrame,sleeping:false}));if(activeFrame)activeFrame.dataset.cacheManaged='true';currentId=id;const page=pages.get(id);if(activeFrame&&!activeFrame.dataset.bindingRestored){activeFrame.dataset.bindingRestored='true';if(page.fixedContext)window.dispatchEvent(new CustomEvent('terminal:panel-binding-request',{detail:{instanceId:id,binding:'fixed',context:page.fixedContext}}));}persistTabs();render();
}
function render(){const focused=list.contains(document.activeElement)?document.activeElement.dataset.instanceId:null;list.replaceChildren();for(const page of pages.values()){
 const button=document.createElement('button');button.className='open-workspace-tab';button.dataset.instanceId=page.id;button.type='button';button.setAttribute('role','tab');button.setAttribute('aria-selected',String(page.id===currentId));button.tabIndex=page.id===currentId?0:-1;
 const frame=page.frame;button.textContent=(page.pinned?'⌖ ':'')+page.title+(page.sleeping?' · 休眠':'');button.title=page.title;
 if(frame?.dataset.actualMarket){const badge=document.createElement('small');badge.textContent=[frame.dataset.actualMarket,frame.dataset.actualInstrument,frame.dataset.contextBinding==='fixed'?'固定':frame.dataset.retainedMarket?'保留':''].filter(Boolean).join(' · ');button.append(badge);}
 button.draggable=true;button.ondragstart=event=>event.dataTransfer.setData('text/plain',page.id);button.ondragover=event=>event.preventDefault();button.ondrop=event=>{event.preventDefault();const id=event.dataTransfer.getData('text/plain');if(id===page.id||!pages.has(id))return;const item=pages.get(id),entries=[...pages].filter(([key])=>key!==id);entries.splice(entries.findIndex(([key])=>key===page.id),0,[id,item]);pages=new Map(entries);persistTabs();render();};
 button.onclick=event=>{event.stopPropagation();if(page.id!==currentId)activate(page);};
 button.oncontextmenu=event=>{event.preventDefault();showMenu(page);};
 button.ondblclick=()=>showMenu(page);
 button.onkeydown=event=>{if(event.key==='F10'&&event.shiftKey){event.preventDefault();showMenu(page);return;}if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;event.preventDefault();const buttons=[...list.children],index=buttons.indexOf(button),next=event.key==='Home'?0:event.key==='End'?buttons.length-1:(index+(event.key==='ArrowRight'?1:-1)+buttons.length)%buttons.length;buttons[next].focus();};
 list.append(button);
 }list.querySelector('[aria-selected="true"]')?.scrollIntoView({block:'nearest',inline:'nearest'});if(focused){const restored=[...list.children].find(button=>button.dataset.instanceId===focused);if(restored){restored.focus({preventScroll:true});restored.scrollIntoView({block:'nearest',inline:'nearest'});}}
}
let pending=false;const schedule=()=>{if(pending)return;pending=true;requestAnimationFrame(()=>{pending=false;sync();});};
window.addEventListener('terminal:layout-changed',schedule);
window.addEventListener('terminal:panel-context-sent',event=>{const page=pages.get(event.detail?.instanceId);if(page){page.fixedContext=event.detail.binding==='fixed'?displayContext(event.detail.context):null;persistTabs();}render();});
for(const eventName of ['terminal:session-changed','terminal:profile-changed'])window.addEventListener(eventName,()=>{loadTabs();schedule();});
new MutationObserver(schedule).observe(view,{childList:true});if(window.TerminalWorkspace){loadTabs();schedule();}else window.addEventListener('terminal:workspace-ready',()=>{loadTabs();schedule();},{once:true});

const allTabs=document.createElement('button');allTabs.className='workspace-all-tabs';allTabs.textContent='▾';allTabs.setAttribute('aria-label','全部已打开标签');allTabs.onclick=()=>{menu.replaceChildren();for(const page of pages.values()){const button=document.createElement('button');button.textContent=(page.pinned?'⌖ ':'')+page.title;button.onclick=()=>{menu.close();activate(page);};menu.append(button);}const cancel=document.createElement('button');cancel.textContent='取消';cancel.onclick=()=>menu.close();menu.append(cancel);menu.showModal();};container.insertBefore(allTabs,document.getElementById('directory-toggle'));

window.addEventListener('terminal:instance-suspended',event=>{const page=pages.get(event.detail?.id);if(!page)return;page.frame=null;page.sleeping=true;persistTabs();render();});
window.addEventListener('terminal:resolve-instance',event=>{if(event.detail?.instanceId)return;const page=[...pages.values()].find(item=>item.snapshot.func===event.detail?.featureCode&&item.snapshot.layout==='1'&&!item.frame?.isConnected);if(page)event.detail.instanceId=page.id;});
