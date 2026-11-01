import React,{useState} from 'react';
import {parsePriceRange} from './chart-axis.js';
export function ChartPriceRangeControl({index,disabled,readRange,onApply}){
  const [from,setFrom]=useState(''),[to,setTo]=useState(''),[error,setError]=useState('');
  const apply=()=>{try{onApply(parsePriceRange(from,to));setError('');}catch(error){setError(error.message);}};
  return <div className="tv-price-range-fields"><label>价格下限<input aria-label={`第${index+1}窗价格下限`} inputMode="decimal" disabled={disabled} value={from} onChange={event=>setFrom(event.target.value)}/></label><label>价格上限<input aria-label={`第${index+1}窗价格上限`} inputMode="decimal" disabled={disabled} value={to} onChange={event=>setTo(event.target.value)}/></label><button disabled={disabled} onClick={()=>{const range=readRange();if(range){setFrom(String(range.from));setTo(String(range.to));setError('');}}}>读取当前价格范围</button><button disabled={disabled} onClick={apply}>应用价格范围</button>{error&&<p role="alert">{error}</p>}</div>;
}
