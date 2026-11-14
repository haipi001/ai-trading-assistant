import {NAV_GROUPS,cleanNavigationGroups} from './navigation-model.mjs';
// Display preferences never contain credentials, account snapshots or execution rights.
export const WORKSPACE_VERSION=1;
export const BINDINGS=Object.freeze(['page','global','fixed','aggregate']);
export function normalizePreferences(input={},featureCodes=[],toolIds=[]){
 input=input&&typeof input==='object'&&!Array.isArray(input)?input:{};
 const unique=(values,allowed)=>[...new Set((Array.isArray(values)?values:[]).filter(x=>allowed.includes(x)))];
 const order=(values,allowed)=>{const selected=unique(values,allowed);return [...selected,...allowed.filter(x=>!selected.includes(x))];};
 const groups=cleanNavigationGroups(input.navigation?.groups,featureCodes),groupNames=[...new Set(['收藏',...NAV_GROUPS,...Object.values(groups)])];
 return {version:WORKSPACE_VERSION,navigation:{groupOrder:order(input.navigation?.groupOrder,groupNames),expanded:Object.fromEntries(Object.entries(input.navigation?.expanded||{}).filter(([k,v])=>k.length<=32&&typeof v==='boolean')),groups,order:order(input.navigation?.order,featureCodes),hidden:unique(input.navigation?.hidden,featureCodes),favorites:unique(input.navigation?.favorites,featureCodes)},tools:{overflow:unique(input.tools?.overflow,toolIds),order:order(input.tools?.order,toolIds),hidden:unique(input.tools?.hidden,toolIds),pinned:unique(input.tools?.pinned,toolIds)},panels:Object.fromEntries(Object.entries(input.panels||{}).filter(([id])=>toolIds.includes(id)).map(([id,p])=>[id,{expanded:p?.expanded===true,width:Math.max(320,Math.min(800,Number(p?.width)||360)),binding:BINDINGS.includes(p?.binding)?p.binding:'page'}]))};
}
export function preferenceStore(storage,userId,featureCodes,toolIds){
 const key=`terminal.workspace.preferences.v1:${encodeURIComponent(userId||'GUEST')}`;
 return {load(){try{return {value:normalizePreferences(JSON.parse(storage.getItem(key)||'{}'),featureCodes,toolIds),error:null};}catch(error){return {value:normalizePreferences({},featureCodes,toolIds),error:'配置读取失败，已使用默认展示；原存储未覆盖。'};}},save(value){const normalized=normalizePreferences(value,featureCodes,toolIds);try{storage.setItem(key,JSON.stringify(normalized));return {value:normalized,error:null};}catch(error){return {value:normalized,error:'配置保存失败；当前修改仅在本次会话有效。'};}}};
}
