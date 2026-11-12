import {useRef,useState} from 'react';
import {strategyEditorKey,readStrategyEditor,saveStrategyEditor,clearStrategyEditor} from './strategy-editor-buffer.js';
export function useStrategyEditor(scope,id,initial){
 const key=strategyEditorKey(scope,id);
 const [form,setForm]=useState(()=>{try{return readStrategyEditor(sessionStorage,key,initial);}catch{return initial;}});
 const current=useRef(form);current.current=form;
 const [storageError,setStorageError]=useState(false);
 function update(next){
  const value=typeof next==='function'?next(current.current):next;
  try{saveStrategyEditor(sessionStorage,key,value);setStorageError(false);}catch{setStorageError(true);}
  current.current=value;setForm(value);
 }
 function clear(){try{clearStrategyEditor(sessionStorage,key);}catch{setStorageError(true);}}
 return [form,update,clear,storageError];
}
