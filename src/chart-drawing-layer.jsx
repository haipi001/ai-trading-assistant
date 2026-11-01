import React,{useEffect,useRef,useState} from 'react';
import {DRAWING_POINT_COUNTS,anchorAt,anchorLogical,drawingScope,measurement,validateAnchoredDrawing,moveDrawing} from './chart-drawings.js';
export function ChartDrawingLayer({chart,series,candles,symbol,venue,marketMode,drawings=[],tool,locked,magnet,onDraw,onUpdate,revision}){
  const [points,setPoints]=useState([]),[hover,setHover]=useState(null),[text,setText]=useState(''),[textPoint,setTextPoint]=useState(null);
  const svg=useRef(null),drag=useRef(null);
  const [selected,setSelected]=useState(null),[editing,setEditing]=useState(null);
  const brush=useRef(null),scope=drawingScope(symbol,venue,marketMode);
  useEffect(()=>{setPoints([]);setHover(null);setTextPoint(null);brush.current=null;drag.current=null;setEditing(null);setSelected(null);},[tool,scope,locked]);
  useEffect(()=>{const cancel=event=>{if(event.key==="Escape"){drag.current=null;brush.current=null;setEditing(null);setSelected(null);setPoints([]);setTextPoint(null);}};window.addEventListener("keydown",cancel);return()=>window.removeEventListener("keydown",cancel);},[]);
  if(!chart||!series)return null;
  const width=chart.timeScale().width(),height=chart.panes()[0]?.getHeight()||0;
  const project=point=>{const logical=anchorLogical(point.time,candles);if(logical===null)return null;const x=chart.timeScale().logicalToCoordinate(logical),y=series.priceToCoordinate(point.price);return x===null||y===null?null:{x,y};};
  const convert=event=>{const rect=svg.current.getBoundingClientRect();return anchorAt({x:event.clientX-rect.left,y:event.clientY-rect.top,width,height},candles,x=>chart.timeScale().coordinateToLogical(x),y=>series.coordinateToPrice(y),magnet);};
  const save=(anchors,label)=>{const drawing={schema:2,id:crypto.randomUUID(),scope,type:tool,points:anchors,...(label?{text:label}:{})};onDraw(validateAnchoredDrawing(drawing));setPoints([]);setHover(null);};
  const shape=(drawing,preview=false)=>{
    const anchors=drawing.points.map(project);if(anchors.some(point=>!point))return null;
    const [a,b,c]=anchors;if(!a)return null;
    const style={stroke:preview?'#8498b5':drawing.style?.color||'#2979ff',strokeWidth:drawing.style?.width||1.5,fill:'none'};
    if(drawing.type==='水平线')return <line x1={0} y1={a.y} x2={width} y2={a.y} {...style}/>;
    if(drawing.type==='文本')return <text x={a.x} y={a.y} fill={drawing.style?.color||"#2979ff"} fontSize="12">{drawing.text}</text>;
    if(!b)return <circle cx={a.x} cy={a.y} r="3" fill={drawing.style?.color||"#2979ff"}/>;
    if(drawing.type==='矩形')return <rect x={Math.min(a.x,b.x)} y={Math.min(a.y,b.y)} width={Math.abs(b.x-a.x)} height={Math.abs(b.y-a.y)} {...style} fill="#2979ff12"/>;
    if(drawing.type==='测量'){const result=measurement(drawing.points);return <g><line x1={a.x} y1={a.y} x2={b.x} y2={b.y} {...style}/><text x={(a.x+b.x)/2} y={(a.y+b.y)/2-6} fill={drawing.style?.color||"#2979ff"} fontSize="11">{result?`${result.percent>=0?'+':''}${result.percent.toFixed(2)}% · ${Math.round(result.seconds/60)}分`:''}</text></g>;}
    if(drawing.type==='斐波那契')return <g>{[0,.236,.382,.5,.618,.786,1].map(ratio=>{const price=drawing.points[0].price+(drawing.points[1].price-drawing.points[0].price)*ratio,y=series.priceToCoordinate(price);return <g key={ratio}><line x1={a.x} y1={y} x2={b.x} y2={y} {...style}/><text x={b.x+3} y={y-3} fontSize="10" fill={drawing.style?.color||"#2979ff"}>{ratio}</text></g>;})}</g>;
    if(drawing.type==='平行线')return <g><line x1={a.x} y1={a.y} x2={b.x} y2={b.y} {...style}/>{c&&<line x1={c.x} y1={c.y} x2={c.x+b.x-a.x} y2={c.y+b.y-a.y} {...style}/>}</g>;
    if(drawing.type==='画笔')return <polyline points={anchors.map(point=>`${point.x},${point.y}`).join(' ')} {...style}/>;
    return <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} {...style}/>;
  };
  const beginEdit=(event,drawing,index=null)=>{
    if(tool!=="光标"||locked||drawing.locked||event.button!==0)return;
    const start=convert(event);if(!start)return;
    event.preventDefault();event.stopPropagation();setSelected(drawing.id);setEditing(drawing);
    drag.current={drawing,start,index,candidate:drawing,x:event.clientX,y:event.clientY};svg.current.setPointerCapture(event.pointerId);
  };
  const dragCandidate=event=>{
    const session=drag.current,end=convert(event);if(!session||!end)return null;
    if(Math.hypot(event.clientX-session.x,event.clientY-session.y)<3)return session.drawing;
    if(session.index===null)return moveDrawing(session.drawing,session.start,end,candles);
    return validateAnchoredDrawing({...session.drawing,points:session.drawing.points.map((point,index)=>index===session.index?end:point)});
  };
  const saveText=()=>{if(text.trim()){save([textPoint],text.trim());setTextPoint(null);}};
  const active=tool!=='光标'&&!locked;
  return <><svg ref={svg} className={`tv-anchor-layer ${active?'active':''}`} width={width} height={height} aria-label={`${symbol}时间价格绘图层`} data-drawing-count={drawings.filter(drawing=>drawing.schema===2&&drawing.scope===scope).length} onContextMenu={event=>{if(active){event.preventDefault();setPoints([]);setHover(null);setTextPoint(null);}}} onPointerDown={event=>{if(!active||event.button!==0)return;event.preventDefault();const point=convert(event);if(!point)return;if(tool==='画笔'){brush.current=[point];setPoints([point]);event.currentTarget.setPointerCapture(event.pointerId);}}} onPointerMove={event=>{if(drag.current){const candidate=dragCandidate(event);if(candidate){drag.current.candidate=candidate;setEditing(candidate);}return;}if(!active)return;const point=convert(event);if(!point)return;if(brush.current){if(brush.current.length<1000){brush.current.push(point);setPoints([...brush.current]);}}else setHover(point);}} onPointerUp={event=>{if(drag.current){event.preventDefault();event.stopPropagation();const session=drag.current,candidate=dragCandidate(event);drag.current=null;setEditing(null);if(candidate&&JSON.stringify(candidate)!==JSON.stringify(session.drawing))onUpdate?.(candidate);return;}if(!active||event.button!==0)return;const point=convert(event);if(tool==='画笔'){const anchors=brush.current;brush.current=null;if(anchors?.length>1)save(anchors);else setPoints([]);return;}if(!point)return;if(tool==='文本'){setTextPoint(point);setText('');return;}const next=[...points,point];if(next.length===(DRAWING_POINT_COUNTS[tool]||2))save(next);else setPoints(next);}} onPointerCancel={()=>{brush.current=null;drag.current=null;setEditing(null);setPoints([]);}}>
    {drawings.filter(drawing=>drawing.schema===2&&drawing.scope===scope&&!drawing.hidden).map(drawing=>{
      const value=editing?.id===drawing.id?editing:drawing;
      return <g key={drawing.id} className={tool==="光标"&&!locked&&!drawing.locked?"tv-drawing-selectable":""} data-selected={selected===drawing.id?"true":"false"} data-drawing-id={drawing.id} data-drawing-type={drawing.type} onPointerDown={event=>beginEdit(event,drawing)}>{shape(value)}{selected===drawing.id&&!locked&&!drawing.locked&&value.points.map((point,index)=>{
        if(value.points.length>50&&index!==0&&index!==value.points.length-1)return null;
        const at=project(point);return at&&<circle className="tv-drawing-handle" key={index} data-anchor-index={index} cx={at.x} cy={at.y} r="5" fill="white" stroke="#2979ff" strokeWidth="2" onPointerDown={event=>beginEdit(event,drawing,index)}/>;
      })}</g>;
    })}

    {!!points.length&&shape({type:tool,points:tool==='画笔'?points:hover?[...points,hover]:points},true)}
  </svg>{selected&&!active&&!locked&&<div className="tv-anchor-hint">拖动对象或锚点 · Esc取消</div>}{active&&<div className="tv-anchor-hint">{tool} · {tool==='画笔'?'拖动画线':tool==='文本'?'点击位置后输入文字':`选择${DRAWING_POINT_COUNTS[tool]||2}个锚点 · 已选${points.length}`} · 右键取消</div>}{textPoint&&<form className="tv-anchor-text" onSubmit={event=>{event.preventDefault();saveText();}}><input aria-label="图表标注文字" autoFocus maxLength={200} value={text} onChange={event=>setText(event.target.value)}/><button type="button" onClick={saveText}>保存文字</button><button type="button" onClick={()=>setTextPoint(null)}>取消</button></form>}</>;
}
