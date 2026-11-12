import {useMemo,useRef,useState} from 'react';
import {getTerminalTradingContext} from './terminal-trading-policy.js';
import {workbenchFormKey,readWorkbenchForm,saveWorkbenchForm,workbenchFormFields} from './workbench-form-buffer.js';
export function useWorkbenchForm(namespace,symbol,defaults){
 const key=workbenchFormKey(namespace,symbol,getTerminalTradingContext());
 const loaded=useMemo(()=>{try{return {generation:Symbol(),fields:readWorkbenchForm(sessionStorage,key,defaults),error:key?'':'身份未校验，输入仅保留在当前页面'};}catch{return {generation:Symbol(),fields:{...defaults},error:'会话缓冲读取失败，请保留当前页面并手动保存'};}},[key]);
 const [slot,setSlot]=useState(loaded),state=slot.generation===loaded.generation?slot:loaded;
 const current=useRef(null);current.current={key,generation:loaded.generation,fields:state.fields};
 const update=patch=>{
  if(current.current.key!==key||current.current.generation!==loaded.generation)return;
  const fields={...current.current.fields,...workbenchFormFields(patch,defaults)};let error=key?'':'身份未校验，输入仅保留在当前页面';
  try{saveWorkbenchForm(sessionStorage,key,fields,defaults);}catch{error='会话缓冲保存失败，请保留当前页面并手动保存';}
  current.current={key,generation:loaded.generation,fields};setSlot({generation:loaded.generation,fields,error});
 };
 return [state.fields,update,state.error,key];
}
