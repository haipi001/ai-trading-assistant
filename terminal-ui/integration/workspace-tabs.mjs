// Pure instance model: market changes never rewrite the user's tab structure.
export function openTab(state,entry,{duplicate=false,id=()=>crypto.randomUUID()}={}){
 const existing=!duplicate&&state.tabs.find(t=>t.featureCode===entry.featureCode&&t.contextKey===(entry.contextKey||''));
 if(existing)return {...state,activeId:existing.id};
 const tab={id:id(),featureCode:entry.featureCode,contextKey:entry.contextKey||'',binding:entry.binding||'global',pinned:false,dirty:false};
 return {...state,tabs:[...state.tabs,tab],activeId:tab.id};
}
export function closeTab(state,id,{discard=false}={}){
 const index=state.tabs.findIndex(t=>t.id===id),tab=state.tabs[index];
 if(!tab)return {state,blocked:null};
 if(tab.pinned)return {state,blocked:'pinned'};
 if(tab.dirty&&!discard)return {state,blocked:'unsaved'};
 const tabs=state.tabs.filter(t=>t.id!==id);
 return {state:{...state,tabs,activeId:state.activeId===id?(tabs[Math.min(index,tabs.length-1)]?.id||null):state.activeId,recentlyClosed:[tab,...(state.recentlyClosed||[])].slice(0,20)},blocked:null};
}
export function moveTab(state,id,targetId){const source=state.tabs.find(t=>t.id===id);if(!source||id===targetId||!state.tabs.some(t=>t.id===targetId))return state;const tabs=state.tabs.filter(t=>t.id!==id);tabs.splice(tabs.findIndex(t=>t.id===targetId),0,source);return {...state,tabs};}
export function effectiveTabContext(tab,globalContext,pageContext){if(tab.binding==='fixed')return tab.context;if(tab.binding==='page')return pageContext;if(tab.binding==='aggregate')return null;return globalContext;}
