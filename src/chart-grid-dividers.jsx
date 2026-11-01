import React,{useRef} from 'react';
import {defaultGridColumns,resizeGridBoundary,resizeGridRowBoundary} from './chart-grid-geometry.js';
export function ChartGridDividers({count,geometry,onChange}){
 const drag=useRef(null),columns=Math.min(count,geometry?.columns??defaultGridColumns(count)),rows=Math.ceil(count/columns);
 const current={...geometry,columns,weights:(geometry?.weights??Array(columns).fill(1)).slice(0,columns)};
 const cancel=()=>{if(drag.current){onChange(drag.current.original);drag.current=null;}};
 return ['column','row'].flatMap(axis=>{
 const weights=axis==='column'?current.weights:Array.from({length:rows},(_,i)=>current.rowWeights?.[i]??1),total=weights.reduce((a,b)=>a+b,0);
 const resize=(base,index,delta)=>axis==='column'?resizeGridBoundary(base,index,delta):resizeGridRowBoundary(base,count,index,delta);
 return Array.from({length:weights.length-1},(_,index)=><button key={`${axis}-${index}`} className={`tv-grid-divider ${axis==='row'?'row-divider':''}`} aria-label={`调整第${index+1}条图窗${axis==='row'?'行':'列'}分隔线`} title="拖动调整；方向键微调；Esc取消；双击等分" style={{[axis==='row'?'top':'left']:`${100*weights.slice(0,index+1).reduce((a,b)=>a+b,0)/total}%`}}
 onPointerDown={event=>{if(event.button!==0)return;event.preventDefault();event.currentTarget.focus();event.currentTarget.setPointerCapture(event.pointerId);const rect=event.currentTarget.parentElement.getBoundingClientRect();drag.current={position:axis==='row'?event.clientY:event.clientX,size:axis==='row'?rect.height:rect.width,base:current,original:geometry,total};}}
 onPointerMove={event=>{const start=drag.current;if(start&&start.size>0)onChange(resize(start.base,index,((axis==='row'?event.clientY:event.clientX)-start.position)/start.size*start.total));}}
 onPointerUp={event=>{drag.current=null;if(event.currentTarget.hasPointerCapture(event.pointerId))event.currentTarget.releasePointerCapture(event.pointerId);}}
 onPointerCancel={cancel} onLostPointerCapture={cancel}
 onKeyDown={event=>{if(event.key==='Escape'){event.preventDefault();cancel();}else if((axis==='row'?['ArrowUp','ArrowDown']:['ArrowLeft','ArrowRight']).includes(event.key)){event.preventDefault();onChange(resize(current,index,(['ArrowRight','ArrowDown'].includes(event.key)?1:-1)*(event.shiftKey?.2:.05)));}}}
 onDoubleClick={()=>onChange(axis==='row'?{...current,rowWeights:Array(rows).fill(1)}:{...current,weights:Array(columns).fill(1)})} onClick={event=>event.currentTarget.focus()}/>);
 });
}
