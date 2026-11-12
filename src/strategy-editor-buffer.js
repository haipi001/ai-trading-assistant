import {spotDcaConfiguration} from './spot-dca-configuration.js';
import {gridConfiguration} from './grid-parameter-check.js';
const limits={name:200,coin:128,type:128,annualized:64,amount:128,risk:64,platform:200,trigger:200,invalidation:200,constraints:400,source_note_id:128,source_snapshot_id:128,source_request_id:128,source_content_hash:64,budget_currency:12,quote_currency:12};
export function strategyEditorKey(scope,id){return scope?'terminal-strategy-editor-v1:'+JSON.stringify([scope,id==null?'new':String(id)]):null;}
export function strategyEditorFields(value){const fields=Object.fromEntries(Object.entries(limits).filter(([key])=>typeof value?.[key]==='string').map(([key,max])=>[key,value[key].slice(0,max)]));if(value?.grid){try{fields.grid=gridConfiguration(value.grid);}catch{}}if(value?.dca){try{fields.dca=spotDcaConfiguration(value.dca);}catch{}}return fields;}
export function readStrategyEditor(storage,key,initial){
 if(!key)return initial;
 try {const saved=JSON.parse(storage.getItem(key)||'null');return saved?.version===1?{...initial,...strategyEditorFields(saved.fields)}:initial;}catch{return initial;}
}
export function saveStrategyEditor(storage,key,value){
 if(key)storage.setItem(key,JSON.stringify({version:1,fields:strategyEditorFields(value),status:'unsubmitted'}));
}
export function clearStrategyEditor(storage,key){if(key)storage.removeItem(key);}
