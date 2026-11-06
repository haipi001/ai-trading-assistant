import {focusedPanelContext,panelLocks,restorePanelLocks} from './panel-host.mjs?v=5';
import {installWorkspaceControls} from './workspace-controls.mjs?v=2';
import {backend} from './backend-service.mjs';
import {MARKETS,initialState,updateContext} from './context.mjs';
import {createMarketWorkspaces} from './market-workspaces.mjs?v=2';
import {installAppearance} from './appearance.mjs';
import {installIdentityControls} from './identity-controls.mjs';
import {identities} from './identity-service.mjs';
import {verifiedIdentity} from './identity-catalog.mjs';
installAppearance();
const key='terminal-integration-context-v1';
let raw;try{raw=localStorage.getItem(key);}catch{}
let state=initialState(raw);
const bar=document.createElement('section');bar.className='integration-bar';bar.setAttribute('aria-label','跨市场研究上下文');
bar.innerHTML='<label>市场 <select id="desk-market"></select></label><label>标的 <input id="desk-instrument" maxlength="128"></label><label>场所 <input id="desk-venue" maxlength="128"></label><label data-chain>链 ID <input id="desk-chain"></label><label data-chain>合约 <input id="desk-contract" class="contract-input" maxlength="42"></label><label>周期 <select id="desk-timeframe"><option>5M</option><option>15M</option><option>1H</option><option>1D</option></select></label><label>模式 <select id="desk-execution"><option value="READ_ONLY">只读</option><option value="PAPER">Paper 模拟</option><option value="LIVE" disabled>Live 未开放</option></select></label><span>实盘关闭</span><button id="desk-ai" aria-expanded="false">AI 研究上下文</button><span id="desk-status" class="integration-status" role="status"></span>';
document.querySelector('.bar').after(bar);
const $=id=>document.getElementById(id);
for(const [value,market] of Object.entries(MARKETS)){const option=new Option(market.label,value);$('desk-market').add(option);}
const drawer=document.createElement('aside');drawer.className='integration-drawer';drawer.hidden=true;drawer.setAttribute('aria-label','AI研究上下文');drawer.innerHTML='<button id="desk-close">关闭</button><h2>当前研究对象</h2><pre id="desk-snapshot"></pre><p>此上下文独立于原终端演示行情；业务数据接入前，演示数字不作为 AI 证据。</p><h2>本页研究动作</h2><div id="desk-actions"></div><pre id="desk-prompt" role="status"></pre>';document.body.append(drawer);
new ResizeObserver(()=>{drawer.style.top=bar.getBoundingClientRect().bottom+'px';}).observe(bar);

const connection=document.createElement('section');connection.innerHTML='<h2>后端连接</h2><button id="desk-health">检查后端</button><pre id="desk-health-result" role="status">尚未检查连接</pre>';drawer.append(connection);
$('desk-health').onclick=async()=>{const button=$('desk-health');button.disabled=true;$('desk-health-result').textContent='正在检查';try{const result=await backend.request('/health/status',{timeout:4000});$('desk-health-result').textContent='后端响应：'+String(result.status||'已收到')+'；认证与业务接口仍需分别验证';}catch(error){$('desk-health-result').textContent='后端不可用或跨域未配置：'+error.message;}finally{button.disabled=false;}};
function persist(){try{localStorage.setItem(key,JSON.stringify(state));}catch{$('desk-status').textContent='偏好保存失败，本次会话仍可使用';}}
function render(){const c=state.current;if(![...$('desk-timeframe').options].some(option=>option.value===c.timeframe))$('desk-timeframe').add(new Option(c.timeframe,c.timeframe));$('desk-market').value=c.market;$('desk-execution').value=c.executionMode;$('desk-execution').querySelector('[value="PAPER"]').disabled=c.market==='onchain';$('desk-instrument').value=c.instrumentId;$('desk-venue').value=c.venue;$('desk-chain').value=c.chainId||'';$('desk-contract').value=c.contractAddress;$('desk-timeframe').value=c.timeframe;bar.querySelectorAll('[data-chain]').forEach(el=>el.hidden=c.market!=='onchain');$('desk-status').textContent='上下文 v'+c.contextVersion+' · 演示与业务数据分别标识';window.dispatchEvent(new CustomEvent('terminal:context',{detail:structuredClone(c)}));updateResearchContext();}
function applyWorkspaceState(next){const version=state.current.contextVersion;state=initialState(JSON.stringify(next));state.current.contextVersion=version+1;persist();render();}
const rootWorkspace=()=>{if(!window.TerminalWorkspace)throw Error('终端尚未就绪');return window.TerminalWorkspace;};
const marketWorkspaces=createMarketWorkspaces({getState:()=>state,applyState:applyWorkspaceState,getLayout:()=>rootWorkspace().snapshot(),applyLayout:value=>rootWorkspace().restore(value),getLocks:panelLocks,applyLocks:restorePanelLocks,codes:()=>rootWorkspace().codes()});
$('desk-market').onchange=e=>{try{marketWorkspaces.switchTo(e.target.value);$('desk-status').textContent+=' · 独立市场布局';}catch(error){render();$('desk-status').textContent='市场布局切换失败，原布局已保留：'+error.message;}};
for(const [id,field] of Object.entries({'desk-instrument':'instrumentId','desk-venue':'venue','desk-chain':'chainId','desk-contract':'contractAddress','desk-timeframe':'timeframe','desk-execution':'executionMode'}))$(id).onchange=e=>{try{if(field==='executionMode'&&e.target.value==='PAPER'&&!verifiedIdentity(state.current,identities.snapshot()).paperEligible)throw Error('请先选择已校验的兼容Paper账户');state=updateContext(state,{[field]:e.target.value});persist();render();}catch(error){render();$('desk-status').textContent=error.message;}};
$('desk-ai').onclick=()=>{drawer.hidden=!drawer.hidden;$('desk-ai').setAttribute('aria-expanded',String(!drawer.hidden));};$('desk-close').onclick=()=>{drawer.hidden=true;$('desk-ai').setAttribute('aria-expanded','false');$('desk-ai').focus();};
function updateResearchContext(){const c=focusedPanelContext()||state.current,catalog=identities.snapshot(),account=catalog?.accounts.find(a=>a.id===c.accountId),wallet=catalog?.wallets.find(w=>w.id===c.walletId);$('desk-snapshot').textContent=[MARKETS[c.market].label,c.instrumentId||'未选择标的',c.venue||'未选择场所',c.chainId?'链 '+c.chainId:'',c.contractAddress,c.timeframe,c.accountId?'账户 '+(account?.label||'待校验')+' · '+c.accountId.slice(0,8):'未选择账户',c.walletId?'钱包 '+(wallet?.label||'待校验')+' · '+c.walletId.slice(0,8):'',(c.executionMode==='PAPER'?'Paper 模拟':'只读')+' · 上下文 '+c.contextVersion].filter(Boolean).join(' · ');}
function actions(){updateResearchContext();const title=document.querySelector('.qcell.focus .qfn')?.textContent||$('phTitle')?.textContent||'HELP';const code=title.trim().split(' ')[0];const specific={GP:'分析周期与技术形态',DEPTH:'检查流动性与价差',TOP:'梳理新闻事件与来源',N:'核对标的相关新闻',PORT:'检查资产集中度',ORD:'解释订单状态与风险',FA:'分析财务与估值',OPT:'分析期权情景风险',ALRT:'拟定监控规则'};const host=$('desk-actions');host.replaceChildren();const frame=document.querySelector('.qcell.focus iframe[data-terminal-feature]')||document.querySelector('#view:not(.quadmode) iframe[data-terminal-feature]');const feature=(window.TERMINAL_FEATURES||[]).find(item=>item.code===frame?.dataset.terminalFeature);for(const label of feature?.aiActions||['总结本页',specific[code]||'解释本页字段与数据需求','检查风险与缺失数据']){const button=document.createElement('button');button.textContent=label;button.onclick=()=>{window.dispatchEvent(new CustomEvent('terminal:research-request',{detail:{question:label+'。请仅依据当前工作区真实可用材料，区分事实与推断，说明缺失数据、来源及时间限制。'}}));$('desk-prompt').textContent=JSON.stringify({action:label,page:title,context:focusedPanelContext()||structuredClone(state.current),evidence:[],status:'已准备研究问题；业务面板内可审阅材料并发送，尚未发起模型调用'},null,2);};host.append(button);}}
const viewNode=$('view');if(viewNode)new MutationObserver(actions).observe(viewNode,{childList:true});document.addEventListener('click',actions);render();actions();

installWorkspaceControls({host:drawer,getState:()=>structuredClone(state),applyState:applyWorkspaceState,getMarketWorkspaces:()=>marketWorkspaces.snapshot(),applyMarketWorkspaces:value=>marketWorkspaces.replace(value)});

window.addEventListener('terminal:context-edit',event=>{try{state=updateContext(state,event.detail);persist();render();}catch(error){$('desk-status').textContent='工作区选择未更改：'+error.message;}});

window.addEventListener('terminal:focus-context',actions);

window.addEventListener('terminal:session-changed',()=>{marketWorkspaces.clearIdentities();state=updateContext(state,{accountId:'',walletId:'',executionMode:'READ_ONLY'});state.memories=Object.fromEntries(Object.entries(state.memories).map(([market,value])=>[market,{...value,accountId:'',walletId:'',executionMode:'READ_ONLY'}]));persist();render();});
installIdentityControls({bar,getState:()=>state,update:patch=>{state=updateContext(state,patch);persist();render();}});
