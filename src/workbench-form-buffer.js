import {strategyStorageKey} from './strategy-draft-scope.js';
export function workbenchFormKey(namespace,symbol,context){
 const scope=strategyStorageKey(namespace,Boolean(context),context);
 return scope?'terminal-workbench-form-v1:'+JSON.stringify([scope,symbol,context?.instrumentId||null,context?.panelId||'standalone',context?.accountCurrency||null]):null;
}
export function workbenchFormFields(value,defaults){
 const result={};for(const key of Object.keys(defaults)){if(typeof value?.[key]==='string')result[key]=value[key].slice(0,400);}
 return result;
}
export function readWorkbenchForm(storage,key,defaults){
 if(!key)return {...defaults};
 const value=JSON.parse(storage.getItem(key)||'null');
 return value?.version===1?{...defaults,...workbenchFormFields(value.fields,defaults)}:{...defaults};
}
export function saveWorkbenchForm(storage,key,fields,defaults){
 if(key)storage.setItem(key,JSON.stringify({version:1,status:'unsubmitted',fields:workbenchFormFields(fields,defaults)}));
}
