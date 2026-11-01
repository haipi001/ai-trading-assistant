import { defaultGridColumns } from "./chart-grid-geometry.js";
import { periodDefinition } from "./market-chart-model.js";
import React, { useMemo, useState } from "react";
import * as I from "@phosphor-icons/react";
import "./chart-command-centers.css";

export { IndicatorCenter } from "./indicator-library.jsx";

const LAYOUTS=[1,2,3,4,5,6,7,8,9,10,12,15,16,18];
export function MultiWindowCenter({ current, currentSync = ["十字光标","周期"], currentGeometry=null, onApply, close, say }) {
  const [selected,setSelected]=useState(current),[sync,setSync]=useState(currentSync);
  const [geometry,setGeometry]=useState(currentGeometry);
  const toggle=x=>setSync(sync.includes(x)?sync.filter(y=>y!==x && !(x==="周期" && y==="日期范围")):[...new Set([...sync,x,...(x==="日期范围"?["周期"]:[])])]);
  return <aside className="multi-center"><header><b>多窗排列</b><small>1–18 窗全部免费</small><button aria-label="关闭多窗排列" onClick={close}><I.X/></button></header><div className="layout-grid">{LAYOUTS.map(count=><button className={selected===count?"on":""} key={count} onClick={()=>{setSelected(count);setGeometry(null);}} title={`${count}窗`}>{Array.from({length:Math.min(count,9)},(_,i)=><i key={i}/>) }<span>{count}</span></button>)}</div><button className="custom-layout" onClick={()=>setGeometry(geometry?null:{columns:defaultGridColumns(selected),weights:Array(defaultGridColumns(selected)).fill(1)})}>{geometry?"恢复等宽默认排列":"自定义列宽"}</button>{geometry&&<section><label>列数<select aria-label="自定义图窗列数" value={geometry.columns} onChange={event=>{const columns=Number(event.target.value);setGeometry({columns,weights:Array(columns).fill(1)});}}>{Array.from({length:Math.min(selected,6)},(_,i)=><option key={i+1} value={i+1}>{i+1}</option>)}</select></label>{geometry.weights.map((weight,index)=><label key={index}>第{index+1}列比例 {weight.toFixed(1)}<input aria-label={`第${index+1}列宽比例`} type="range" min="0.25" max="4" step="0.05" value={weight} onChange={event=>setGeometry({...geometry,weights:geometry.weights.map((x,i)=>i===index?Number(event.target.value):x)})}/></label>)}<p>所有行共用列宽；不足一行保留空位。</p></section>}<section><header><b>图表间同步</b><button onClick={()=>setSync(["十字光标","交易对","指标","周期","日期范围","缩放比例","坐标轴","其他"])}>全选</button></header>{["十字光标","交易对","指标","周期","日期范围","对比K线","缩放比例","坐标轴","其他"].map(x=><label key={x}><input type="checkbox" disabled={!["十字光标","交易对","指标","周期","日期范围","缩放比例","坐标轴","其他"].includes(x)} checked={sync.includes(x)} onChange={()=>toggle(x)}/>{x}{!["十字光标","交易对","指标","周期","日期范围","缩放比例","坐标轴","其他"].includes(x)?"（待接入）":""}</label>)}</section><footer><button onClick={close}>取消</button><button onClick={()=>{onApply(selected,sync,geometry);close();}}>应用 {selected} 窗</button></footer></aside>;
}

export function CustomPeriodCenter({ current, onSelect, close, say }) {
  const [amount,setAmount]=useState("1"),[unit,setUnit]=useState("分钟");
  const groups=[["秒",["1秒","30秒"]],["分",["1分","3分","5分","10分","15分","30分","45分","分时"]],["时",["1时","2时","3时","4时","6时","8时","12时"]],["日",["1日","2日","3日","5日"]],["长周期",["1周","15日","1月","季K","年K"]]];
  return <aside className="period-center"><header><b>自定义周期</b><button aria-label="关闭自定义周期" onClick={close}><I.X/></button></header><div className="period-custom"><input aria-label="自定义周期数值" inputMode="numeric" value={amount} onChange={e=>setAmount(e.target.value)}/><select aria-label="自定义周期单位" value={unit} onChange={e=>setUnit(e.target.value)}><option>秒</option><option>分钟</option><option>小时</option><option>天</option><option>周</option><option>月</option></select><button onClick={()=>{if(!/^[1-9]\d{0,3}$/.test(amount))return say("请输入1至9999的整数周期");const label=`${amount}${{秒:"秒",分钟:"分",小时:"时",天:"日",周:"周",月:"月"}[unit]}`;periodDefinition(label);onSelect(label);say(`${label} 已加入周期栏`);}}>添加</button></div>{groups.map(([name,values])=><section key={name}><b>{name}</b><div>{values.map(x=><button className={current===x?"on":""} key={x} onClick={()=>onSelect(x)}>{x}</button>)}</div></section>)}<footer><label><input type="checkbox" defaultChecked/>底部栏显示</label><button onClick={()=>{onSelect("15分");say("周期已恢复默认")}}>恢复默认</button></footer></aside>;
}
