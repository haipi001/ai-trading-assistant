import {useRef,useState} from 'react';
import {commitLayoutListLocked,LAYOUT_STORAGE_KEY} from './chart-layout-storage.js';
export function useChartLayoutTabs(initial){
 const [loaded]=useState(()=>{try{const raw=localStorage.getItem(LAYOUT_STORAGE_KEY),value=raw?JSON.parse(raw):initial;if(!Array.isArray(value)||!value.length)throw new Error('布局列表无效');return {raw,value};}catch{return {raw:undefined,value:initial};}});
 const pending=useRef(false),expected=useRef(loaded.raw),[value,setValue]=useState(loaded.value),[error,setError]=useState('');
 const commit=async next=>{if(pending.current){setError('布局正在保存，请稍后重试');return false;}pending.current=true;try{if(expected.current===undefined)throw new Error('布局存储损坏或不可读取，请先导出当前图表备份');expected.current=await commitLayoutListLocked(localStorage,navigator.locks,expected.current,next);setValue(next);setError('');return true;}catch(error){setError(error.message);return false;}finally{pending.current=false;}};
 const reload=()=>{if(pending.current)return;try{const raw=localStorage.getItem(LAYOUT_STORAGE_KEY),next=raw?JSON.parse(raw):initial;if(!Array.isArray(next)||!next.length)throw new Error('布局列表无效');expected.current=raw;setValue(next);setError('');}catch(error){setError(error.message);}};
 return [value,commit,error,reload];
}
