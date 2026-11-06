import {initialState,marketContext} from './context.mjs';
export const WORKSPACE_KEY='terminal-workspace-v1';
export const MAX_WORKSPACE_BYTES=512*1024;
const copy=value=>JSON.parse(JSON.stringify(value));
export function normalizeView(value,allowedCodes){
 if(!value||typeof value!=='object')throw Error('invalid_market_workspace');
 const validCode=code=>typeof code==='string'&&allowedCodes.includes(code);
 const layout=value.layout;
 if(!layout||!['1','2','4'].includes(String(layout.layout))||!validCode(layout.func))throw Error('invalid_workspace_layout');
 const count=Number(layout.layout);
 if(!Number.isInteger(layout.focus)||layout.focus<0||layout.focus>=count||!Array.isArray(layout.panels)||layout.panels.length!==4)throw Error('invalid_workspace_panels');
 const symbol=s=>{if(typeof s!=='string'||s.length>128||!/^[-A-Za-z0-9./:_]*$/.test(s))throw Error('invalid_workspace_symbol');return s;};
 const panels=layout.panels.map(p=>{if(!validCode(p?.func))throw Error('unknown_workspace_function');return {func:p.func,sym:symbol(p.sym||'')};});
 const split={c:Number(layout.split?.c??.5),r:Number(layout.split?.r??.5)};
 if(Object.values(split).some(n=>!Number.isFinite(n)||n<.2||n>.8))throw Error('invalid_workspace_split');
 const locks=[];if(!Array.isArray(value.locks)||value.locks.length>300)throw Error('invalid_workspace_locks');
 const seen=new Set();for(const lock of value.locks){const match=/^(main|[0-3]):([A-Z][A-Z0-9_]*)$/.exec(lock?.key||'');if(!match||!validCode(match[2])||seen.has(lock.key))throw Error('invalid_workspace_lock');seen.add(lock.key);locks.push({key:lock.key,context:marketContext(lock.context?.market,lock.context)});}
 return {layout:{layout:String(count),func:layout.func,sym:symbol(layout.sym||''),focus:layout.focus,panels,split},locks};
}
export function normalizeMarketViews(value={},allowedCodes){
 if(!value||typeof value!=='object'||Array.isArray(value)||Object.keys(value).length>3)throw Error('invalid_market_workspaces');
 const result={};for(const [market,view] of Object.entries(value)){if(!['stocks','cex','onchain'].includes(market))throw Error('invalid_market_workspace');result[market]=normalizeView(view,allowedCodes);}return result;
}
export function normalizeWorkspace(value,allowedCodes){
 if(!value||value.schema!==1)throw Error('workspace_version_unsupported');
 if(!value.state?.current)throw Error('missing_workspace_context');
 marketContext(value.state.current.market,value.state.current);
 for(const [market,context] of Object.entries(value.state.memories||{}))marketContext(market,context);
 const state=initialState(JSON.stringify(value.state));
 return {schema:1,state,...normalizeView(value,allowedCodes),marketWorkspaces:normalizeMarketViews(value.marketWorkspaces,allowedCodes)};
}
export function decodeWorkspace(raw,allowedCodes){if(typeof raw!=='string'||new TextEncoder().encode(raw).length>MAX_WORKSPACE_BYTES)throw Error('workspace_file_too_large');return normalizeWorkspace(JSON.parse(raw),allowedCodes);}
export function workspaceSnapshot({state,layout,locks,marketWorkspaces={}},allowedCodes){const value=normalizeWorkspace(copy({schema:1,state,layout,locks,marketWorkspaces}),allowedCodes);if(new TextEncoder().encode(JSON.stringify(value)).length>MAX_WORKSPACE_BYTES)throw Error('workspace_file_too_large');return value;}
const timeToServer=value=>value.replace(/MO$/,'mo').replace(/S$/,'s').replace(/M$/,'m').replace(/H$/,'h').replace(/D$/,'d').replace(/W$/,'wk');
const timeFromServer=value=>value?.replace(/mo$/,'MO').replace(/wk$/,'W').toUpperCase()||'1D';
function serverContext(c,target){return {page:target?.page||'more',tab:target?.tab||null,asset_class:c.market==='stocks'?'stock':c.market==='onchain'?'onchain':'crypto_spot',market:c.market,symbol:c.instrumentId||null,venue:c.venue||null,timeframe:timeToServer(c.timeframe),account_id:c.accountId||null,mode:null,chain_id:c.chainId||null,contract_address:c.contractAddress||null,wallet_id:c.walletId||null,context_version:c.contextVersion};}
function clientContext(c){if(c?.mode==='LIVE')throw Error('workspace_live_restore_forbidden');return marketContext(c.market,{instrumentId:c.symbol||'',venue:c.venue||'',timeframe:timeFromServer(c.timeframe),accountId:c.account_id||'',chainId:c.chain_id||'',contractAddress:c.contract_address||'',walletId:c.wallet_id||''});}
export function workspaceSaveBody(snapshot,expectedVersion,registry){
 const targets=new Map(registry.map(x=>[x.code,x]));const count=Number(snapshot.layout.layout);const locks=new Map(snapshot.locks.map(x=>[x.key,x.context]));
 const panels=Array.from({length:count},(_,i)=>{const p=count===1?{func:snapshot.layout.func,sym:snapshot.layout.sym}:snapshot.layout.panels[i];const key=`${count===1?'main':i}:${p.func}`;const locked=locks.has(key);return {panel_id:i,function_code:p.func,terminal_symbol:p.sym||'',locked,context:serverContext(locks.get(key)||snapshot.state.current,targets.get(p.func))};});
 const memories={...snapshot.state.memories,[snapshot.state.current.market]:snapshot.state.current};
 const marketWorkspaces=Object.entries(snapshot.marketWorkspaces||{}).map(([market,view])=>{const base=memories[market]||marketContext(market),viewLocks=new Map(view.locks.map(lock=>[lock.key,lock.context]));return {market,panel_count:Number(view.layout.layout),focused_panel:view.layout.focus,last_function_code:view.layout.func,last_terminal_symbol:view.layout.sym,split_columns:view.layout.split.c,split_rows:view.layout.split.r,
  panels:view.layout.panels.map((p,index)=>({panel_id:index,function_code:p.func,terminal_symbol:p.sym,locked:viewLocks.has(`${index}:${p.func}`),context:serverContext(viewLocks.get(`${index}:${p.func}`)||base,targets.get(p.func))})),
  locked_contexts:view.locks.map(lock=>({key:lock.key,context:serverContext(lock.context,targets.get(lock.key.split(':')[1]))}))};});
 return {expected_version:expectedVersion,context:serverContext(snapshot.state.current,targets.get(snapshot.layout.func)),layout:{agent_open:false,density:'compact',panel_count:count,focused_panel:count===1?0:snapshot.layout.focus,split_columns:snapshot.layout.split.c,split_rows:snapshot.layout.split.r,panels,market_contexts:Object.values(memories).map(c=>serverContext(c,null)),market_workspaces:marketWorkspaces}};
}
export function workspaceRestoreBody(packet,allowedCodes){
 if(packet?.execution_authorized!==false||!Number.isInteger(packet.version)||packet.version<1)throw Error('invalid_workspace_response');
 const count=packet.layout?.panel_count,panels=packet.layout?.panels;if(![1,2,4].includes(count)||!Array.isArray(panels)||panels.length!==count)throw Error('workspace_panels_missing');
 const focus=packet.layout.focused_panel;if(!Number.isInteger(focus)||focus<0||focus>=count)throw Error('invalid_workspace_focus');
 const defaults=Array.from({length:4},()=>({func:'HELP',sym:''}));const locks=[];const ids=new Set();
 for(const p of panels){if(!Number.isInteger(p.panel_id)||p.panel_id<0||p.panel_id>=count||ids.has(p.panel_id))throw Error('invalid_workspace_panel');ids.add(p.panel_id);defaults[p.panel_id]={func:p.function_code,sym:p.terminal_symbol||''};if(p.locked)locks.push({key:`${count===1?'main':p.panel_id}:${p.function_code}`,context:clientContext(p.context)});}
 const memories={};for(const c of packet.layout.market_contexts||[]){if(memories[c.market])throw Error('duplicate_workspace_market');memories[c.market]=clientContext(c);}
 const current=clientContext(packet.context);
 const marketWorkspaces={};for(const view of packet.layout.market_workspaces||[]){if(marketWorkspaces[view.market])throw Error('duplicate_market_workspace');if(!Array.isArray(view.panels)||view.panels.length!==4)throw Error('invalid_market_workspace_panels');const ids=new Set(),rows=Array(4);for(const p of view.panels){if(!Number.isInteger(p.panel_id)||p.panel_id<0||p.panel_id>3||ids.has(p.panel_id))throw Error('invalid_market_workspace_panels');ids.add(p.panel_id);clientContext(p.context);rows[p.panel_id]={func:p.function_code,sym:p.terminal_symbol||''};}if(!Array.isArray(view.locked_contexts))throw Error('invalid_market_workspace_locks');marketWorkspaces[view.market]={layout:{layout:String(view.panel_count),func:view.last_function_code,sym:view.last_terminal_symbol||'',focus:view.focused_panel,panels:rows,split:{c:view.split_columns,r:view.split_rows}},locks:view.locked_contexts.map(lock=>({key:lock.key,context:clientContext(lock.context)}))};}
 // The root server panels describe visible slots only. Preserve dormant slots and
 // locks from the active market's full view as well as those of other markets.
 const activeView=marketWorkspaces[current.market];
 const restoredPanels=activeView?copy(activeView.layout.panels):defaults;
 if(activeView&&count>1)for(const p of panels)restoredPanels[p.panel_id]=defaults[p.panel_id];
 const restoredLocks=new Map((activeView?.locks||[]).map(lock=>[lock.key,lock]));
 for(const p of panels){const key=`${count===1?'main':p.panel_id}:${p.function_code}`;if(!p.locked)restoredLocks.delete(key);}
 for(const lock of locks)restoredLocks.set(lock.key,lock);
 return normalizeWorkspace({schema:1,state:{current,memories},layout:{layout:String(count),func:activeView?.layout.func??defaults[focus].func,sym:activeView?.layout.sym??defaults[focus].sym,focus,panels:restoredPanels,split:{c:packet.layout.split_columns??.5,r:packet.layout.split_rows??.5}},locks:[...restoredLocks.values()],marketWorkspaces},allowedCodes);
}
