import React, { useMemo, useState } from "react";
import * as I from "@phosphor-icons/react";
import "./chart-command-centers.css";

const INDICATORS = [
  ["清算热力图", "追踪潜在清算密集区域", "NEW", "市场指数"],
  ["主力大单跟踪", "识别大额主动成交与方向", "PRO", "特色指标"],
  ["聪明钱追踪", "将链上交易与持仓轨迹标到 K 线", "PRO", "特色指标"],
  ["巨鲸追踪", "跟踪巨鲸在链上与交易所的转账行为", "PRO", "特色指标"],
  ["BOLL", "布林线", "", "技术指标"], ["EMA", "指数平滑移动平均线", "", "技术指标"],
  ["MA", "移动平均线", "", "技术指标"], ["MACD", "指数平滑异同移动平均线", "", "技术指标"],
  ["筹码分布", "质量价分布图", "PRO", "市场指数"], ["VWAP", "成交量加权平均价", "", "技术指标"],
];

export function IndicatorCenter({ studies, setStudies, close, say, openOverlay }) {
  const [tab,setTab]=useState("指标库"),[section,setSection]=useState("全部"),[query,setQuery]=useState("");
  const [favorites,setFavorites]=useState([]);
  const rows=useMemo(()=>INDICATORS.filter(x=>(section==="全部"||x[3]===section)&&`${x[0]}${x[1]}`.toLowerCase().includes(query.toLowerCase())),[section,query]);
  return <div className="chart-center-backdrop" onClick={close}><section className="indicator-center" onClick={e=>e.stopPropagation()}>
    <header><nav>{["指标库","指标广场","指标胜率","信号预警","布局广场"].map(x=><button className={tab===x?"on":""} key={x} onClick={()=>setTab(x)}>{x}</button>)}</nav><button onClick={()=>say("已切换为经典指标管理视图")}>切换经典版</button><button aria-label="关闭指标中心" onClick={close}><I.X/></button></header>
    <div className="indicator-center-body"><aside>{[["全部",I.ChartLine],["收藏",I.Star],["我的",I.UserCircle],["快捷",I.CursorClick],["编写指标",I.Code]].map(([x,Icon])=><button className={section===x?"on":""} key={x} onClick={()=>setSection(x)}><Icon/>{x}</button>)}</aside><main>
      <label className="indicator-search"><I.MagnifyingGlass/><input aria-label="搜索指标" value={query} onChange={e=>setQuery(e.target.value)} placeholder="试试搜索主力大单吧"/></label>
      <nav>{["全部","技术指标","特色指标","市场指数"].map(x=><button className={section===x?"on":""} key={x} onClick={()=>setSection(x)}>{x}</button>)}</nav>
      {tab==="指标库"?<div className="indicator-catalog">{rows.map(row=>{const active=studies.includes(row[0]);return <article key={row[0]}><button aria-label={`收藏${row[0]}`} className={favorites.includes(row[0])?"fav":""} onClick={()=>setFavorites(favorites.includes(row[0])?favorites.filter(x=>x!==row[0]):[...favorites,row[0]])}><I.Star weight={favorites.includes(row[0])?"fill":"regular"}/></button><span><b>{row[0]}</b><small>{row[1]}</small></span>{row[2]&&<em>{row[2]}</em>}<button className={active?"added":""} onClick={()=>{setStudies(active?studies.filter(x=>x!==row[0]):[...studies,row[0]]);say(active?`${row[0]} 已移除`:`${row[0]} 已添加到图表`);}}>{active?"已添加":"添加"}</button></article>})}</div>:<IndicatorSubpage tab={tab} openOverlay={openOverlay} say={say}/>} 
    </main></div>
  </section></div>;
}

function IndicatorSubpage({tab,openOverlay,say}) { const copy={指标广场:["社区指标与策略脚本","浏览公开脚本、查看说明并加入自己的指标库。"],指标胜率:["指标历史胜率","按标的和周期检验信号表现，避免只看一次命中。"],信号预警:["指标信号预警","组合指标条件并创建本地预警，不自动触发交易。"],布局广场:["图表布局模板","保存指标、周期与多窗组合，快速恢复研究现场。"]}[tab];return <div className="indicator-subpage"><I.Sparkle/><h3>{copy[0]}</h3><p>{copy[1]}</p><button onClick={()=>tab==="信号预警"?openOverlay("alertCenter","指标信号预警",{alertType:"指标预警"}):say(`${tab}已切换为本地演示数据`)}>打开{tab}</button></div> }

const LAYOUTS=[1,2,3,4,5,6,7,8,9,10,12,15,16,18];
export function MultiWindowCenter({ current, onApply, close, say }) {
  const [selected,setSelected]=useState(current),[sync,setSync]=useState(["十字光标","周期"]);
  const toggle=x=>setSync(sync.includes(x)?sync.filter(y=>y!==x):[...sync,x]);
  return <aside className="multi-center"><header><b>多窗排列</b><small>1–18 窗全部免费</small><button aria-label="关闭多窗排列" onClick={close}><I.X/></button></header><div className="layout-grid">{LAYOUTS.map(count=><button className={selected===count?"on":""} key={count} onClick={()=>setSelected(count)} title={`${count}窗`}>{Array.from({length:Math.min(count,9)},(_,i)=><i key={i}/>) }<span>{count}</span></button>)}</div><button className="custom-layout" onClick={()=>say("已进入自定义多窗编辑，可拖动分隔线调整")}>自定义多窗</button><section><header><b>图表间同步</b><button onClick={()=>setSync(["十字光标","交易对","指标","周期","日期范围","对比K线","缩放比例","坐标轴","其他"])}>全选</button></header>{["十字光标","交易对","指标","周期","日期范围","对比K线","缩放比例","坐标轴","其他"].map(x=><label key={x}><input type="checkbox" checked={sync.includes(x)} onChange={()=>toggle(x)}/>{x}</label>)}</section><footer><button onClick={close}>取消</button><button onClick={()=>{onApply(selected,sync);close();}}>应用 {selected} 窗</button></footer></aside>;
}

export function CustomPeriodCenter({ current, onSelect, close, say }) {
  const [amount,setAmount]=useState("1"),[unit,setUnit]=useState("分钟");
  const groups=[["秒",["1秒","30秒"]],["分",["1分","3分","5分","10分","15分","30分","45分","分时"]],["时",["1时","2时","3时","4时","6时","8时","12时"]],["日",["1日","2日","3日","5日"]],["长周期",["1周","15日","1月","季K","年K"]]];
  return <aside className="period-center"><header><b>自定义周期</b><button aria-label="关闭自定义周期" onClick={close}><I.X/></button></header><div className="period-custom"><input aria-label="自定义周期数值" inputMode="numeric" value={amount} onChange={e=>setAmount(e.target.value)}/><select aria-label="自定义周期单位" value={unit} onChange={e=>setUnit(e.target.value)}><option>秒</option><option>分钟</option><option>小时</option><option>天</option><option>周</option><option>月</option></select><button onClick={()=>{if(!Number(amount))return say("请输入有效周期");const label=`${amount}${{秒:"秒",分钟:"分",小时:"时",天:"日",周:"周",月:"月"}[unit]}`;onSelect(label);say(`${label} 已加入周期栏`);}}>添加</button></div>{groups.map(([name,values])=><section key={name}><b>{name}</b><div>{values.map(x=><button className={current===x?"on":""} key={x} onClick={()=>onSelect(x)}>{x}</button>)}</div></section>)}<footer><label><input type="checkbox" defaultChecked/>底部栏显示</label><button onClick={()=>{onSelect("15分");say("周期已恢复默认")}}>恢复默认</button></footer></aside>;
}
