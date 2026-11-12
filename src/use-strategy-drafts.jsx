import {useEffect,useMemo,useRef,useState} from 'react';
import {strategyStorageKey,readStrategyDrafts} from './strategy-draft-scope.js';
export function useStrategyDrafts(embedded,context,namespace='ai-trading-assistant-strategies',initialValue=[]){
 const key=strategyStorageKey(namespace,embedded,context);
 const loaded=useMemo(()=>({generation:Symbol(),value:readStrategyDrafts(localStorage,key,initialValue)}),[key]);
 const [slot,setSlot]=useState({key,generation:loaded.generation,value:loaded.value});
 const value=slot.key===key&&slot.generation===loaded.generation?slot.value:loaded.value;
 const current=useRef({key,value,generation:loaded.generation});current.current={key,value,generation:loaded.generation};
 useEffect(()=>{
  const receive=event=>{
   if(!key||(current.current.key!==key||current.current.generation!==loaded.generation))return;
   const rows=event.type==='storage'?(event.key===key?readStrategyDrafts(localStorage,key):null):(event.detail?.key===key?event.detail.value:null);
   if(!Array.isArray(rows))return;
   current.current={key,value:rows,generation:loaded.generation};setSlot({key,generation:loaded.generation,value:rows});
  };
  window.addEventListener('ai-trading-assistant-local-state',receive);window.addEventListener('storage',receive);
  return()=>{window.removeEventListener('ai-trading-assistant-local-state',receive);window.removeEventListener('storage',receive);};
 },[key,loaded]);
 const save=next=>{
  if(!key||(current.current.key!==key||current.current.generation!==loaded.generation))return;
  const rows=typeof next==='function'?next(current.current.value):next;
  if(!Array.isArray(rows))return;
  localStorage.setItem(key,JSON.stringify(rows));
  current.current={key,value:rows,generation:loaded.generation};setSlot({key,generation:loaded.generation,value:rows});
  window.dispatchEvent(new CustomEvent('ai-trading-assistant-local-state',{detail:{key,value:rows}}));
 };
 return [value,save];
}
