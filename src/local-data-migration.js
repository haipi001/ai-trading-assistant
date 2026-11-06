import {readScriptStore,readScriptBuffer,SCRIPT_STORE_KEY,SCRIPT_BUFFER_KEY} from './script-drafts.js';
import {validateChartLayout} from './chart-layout-state.js';
import {validateAnchoredDrawing} from './chart-drawings.js';
export const MIGRATION_LIMIT=8*1024*1024;
export const MIGRATION_BACKUP_KEY='terminal-r127-data-before-import-v1';
const prefix='ai-trading-assistant-';
const policy={watch:'strings',prefs:'object','sidebar-mode':'string','market-side-tab':'string','market-side-open':'boolean','market-order-open':'closed','market-order-split':'number','market-symbol':'string','market-mode':'mode','chart-pane-count':'panes','chart-pane-sync':'strings','chart-active-layout':'string','chart-drawings':'drawings','chart-tabs':'layouts','chart-snapshots':'objects','chart-traders':'objects','followed-traders':'strings',strategies:'objects','strategy-notes':'notes',groups:'objects','custom-nav':'strings'};
export const MIGRATION_KEYS=Object.freeze([...Object.keys(policy).map(key=>prefix+key),SCRIPT_STORE_KEY,SCRIPT_BUFFER_KEY]);
const dangerous=/^(?:__proto__|constructor|prototype|api[_-]?key|api[_-]?secret|secret|password|passphrase|private[_-]?key|seed[_-]?phrase|session[_-]?token|access[_-]?token|authorization)$/i;
function safeTree(value,depth=0){if(depth>35)throw Error('本机数据嵌套过深');if(value&&typeof value==='object'){for(const [key,item] of Object.entries(value)){if(dangerous.test(key))throw Error('数据包含凭据或不安全字段，未导出或导入');safeTree(item,depth+1);}}}
const text=(value,max=100000)=>typeof value==='string'&&value.length<=max;
function validate(key,raw){
 if(!MIGRATION_KEYS.includes(key)||typeof raw!=='string'||new TextEncoder().encode(raw).length>3*1024*1024)throw Error('不支持的本机数据条目');
 const value=JSON.parse(raw);safeTree(value);
 const list=()=>{if(!Array.isArray(value)||value.length>2000)throw Error('本机列表格式或数量无效');};
 const objects=()=>{list();if(!value.every(x=>x&&typeof x==='object'&&!Array.isArray(x)))throw Error('本机记录格式无效');};
 if(key===SCRIPT_STORE_KEY){readScriptStore({getItem:()=>raw});return raw;}
 if(key===SCRIPT_BUFFER_KEY){readScriptBuffer({getItem:()=>raw});return raw;}
 switch(policy[key.slice(prefix.length)]){
  case 'strings':list();if(!value.every(x=>text(x,128)))throw Error('列表值无效');break;
  case 'object':if(!value||Array.isArray(value)||typeof value!=='object')throw Error('偏好格式无效');break;
  case 'objects':objects();if(['strategies','groups','chart-traders','followed-traders'].includes(key.slice(prefix.length))&&!value.every(x=>text(x.name,1000)))throw Error('记录名称无效');break;
  case 'string':if(!text(value,128))throw Error('偏好字符串无效');break;
  case 'boolean':if(typeof value!=='boolean')throw Error('偏好开关无效');break;
  case 'closed':if(typeof value!=='boolean')throw Error('票据偏好无效');return 'false';
  case 'number':if(typeof value!=='number'||!Number.isFinite(value)||value<20||value>90)throw Error('面板比例无效');break;
  case 'panes':if(![1,2,3,4,5,6,7,8,9,10,12,15,16,18].includes(value))throw Error('图窗数量无效');break;
  case 'mode':if(!['stocks','web3'].includes(value))throw Error('市场偏好无效');break;
  case 'notes':objects();if(!value.every(x=>text(x.id,100)&&text(x.title,1000)&&text(x.body,100000)&&(!x.tags||Array.isArray(x.tags)&&x.tags.every(y=>text(y,100)))&&(!x.links||Array.isArray(x.links)&&x.links.every(y=>text(y,100)))))throw Error('笔记字段无效');break;
  case 'layouts':objects();if(value.length>100||new Set(value.map(x=>x.id)).size!==value.length)throw Error('布局标识无效');for(const item of value){if(!text(item.id,100)||!item.id||!text(item.name,80)||!text(item.symbol,128))throw Error('布局字段无效');if(item.state)validateChartLayout(item.state);}break;
  case 'drawings':objects();for(const item of value){if(item.schema===2)validateAnchoredDrawing(item);else if(!text(item.id,100)||!['趋势线','水平线','平行线','矩形','测量','斐波那契','文本','画笔'].includes(item.type)||![item.x,item.y].every(n=>Number.isFinite(n)&&n>=0&&n<=100))throw Error('旧绘图格式无效');}break;
  default:throw Error('不支持的本机数据条目');
 }
 return raw;
}
export function exportLocalData(storage,{origin='',now=new Date().toISOString()}={}){const entries={};for(const key of MIGRATION_KEYS){const raw=storage.getItem(key);if(raw!==null)entries[key]=validate(key,raw);}const packet={format:'r127-local-data',version:1,origin,exportedAt:now,entries};const raw=JSON.stringify(packet,null,2);if(new TextEncoder().encode(raw).length>MIGRATION_LIMIT)throw Error('数据包超过8MB，请分项导出');return raw;}
export function decodeLocalData(raw){if(typeof raw!=='string'||new TextEncoder().encode(raw).length>MIGRATION_LIMIT)throw Error('数据包最大8MB');const value=JSON.parse(raw);if(value?.format!=='r127-local-data'||value.version!==1||!value.entries||Array.isArray(value.entries)||typeof value.entries!=='object')throw Error('数据包格式或版本不支持');const entries={};for(const [key,item] of Object.entries(value.entries))entries[key]=validate(key,item);return {format:value.format,version:1,origin:text(value.origin,200)?value.origin:'',entries};}
export function previewLocalData(packet,storage){return Object.entries(packet.entries).map(([key,value])=>{const before=storage.getItem(key);return {key,value,before,status:before===null?'new':before===value?'same':'conflict'};});}
export function applyLocalData(plan,selected,storage){
 const keys=new Set(selected);if(!keys.size)throw Error('请选择要迁移的条目');const chosen=plan.filter(row=>keys.has(row.key));if(chosen.length!==keys.size)throw Error('选择条目已变化');
 for(const row of chosen){validate(row.key,row.value);if(storage.getItem(row.key)!==row.before)throw Error('本机数据已被其他页面修改，请重新预览');}
 const future=key=>{const row=chosen.find(item=>item.key===key);return row?row.value:storage.getItem(key);};
 const scriptRaw=future(SCRIPT_STORE_KEY),bufferRaw=future(SCRIPT_BUFFER_KEY);
 if(chosen.some(row=>[SCRIPT_STORE_KEY,SCRIPT_BUFFER_KEY].includes(row.key))&&scriptRaw&&bufferRaw){const script=readScriptStore({getItem:()=>scriptRaw}).data,buffer=readScriptBuffer({getItem:()=>bufferRaw});if(buffer.activeId!==null&&!script.documents.some(item=>item.id===buffer.activeId))throw Error('脚本编辑缓冲与草稿库不匹配，请同时选择对应数据');}
 const tabsRaw=future(prefix+'chart-tabs'),activeRaw=future(prefix+'chart-active-layout');
 if(chosen.some(row=>[prefix+'chart-tabs',prefix+'chart-active-layout'].includes(row.key))&&tabsRaw&&activeRaw&&!JSON.parse(tabsRaw).some(item=>item.id===JSON.parse(activeRaw)))throw Error('当前布局标识与布局目录不匹配，请检查选择');
 const backup={version:1,entries:Object.fromEntries(chosen.map(row=>[row.key,row.before]))};
 storage.setItem(MIGRATION_BACKUP_KEY,JSON.stringify(backup));
 const applied=[];try{for(const row of chosen){storage.setItem(row.key,row.value);applied.push(row);}}catch(error){let restored=true;for(const row of applied.reverse()){try{if(row.before===null)storage.removeItem(row.key);else storage.setItem(row.key,row.before);}catch{restored=false;}}throw Error(restored?'写入失败，已恢复原数据；可减少选择条目后重试':'写入失败；请使用导出的恢复前备份检查本机数据');}
 return {applied:chosen.length,overwritten:chosen.filter(row=>row.before!==null).length};
}
export function restoreLocalData(storage){const raw=storage.getItem(MIGRATION_BACKUP_KEY);if(!raw)throw Error('没有迁移前备份');const packet=JSON.parse(raw);if(packet?.version!==1||!packet.entries||Array.isArray(packet.entries))throw Error('迁移前备份损坏');const previous={};for(const [key,value] of Object.entries(packet.entries)){if(!MIGRATION_KEYS.includes(key)||(value!==null&&typeof value!=='string'))throw Error('迁移前备份条目无效');previous[key]=storage.getItem(key);}storage.setItem(MIGRATION_BACKUP_KEY,JSON.stringify({version:1,entries:previous}));const applied=[];try{for(const [key,value] of Object.entries(packet.entries)){if(value===null)storage.removeItem(key);else storage.setItem(key,value);applied.push(key);}}catch(error){for(const key of applied){const value=previous[key];if(value===null)storage.removeItem(key);else storage.setItem(key,value);}storage.setItem(MIGRATION_BACKUP_KEY,raw);throw error;}return applied.length;}
