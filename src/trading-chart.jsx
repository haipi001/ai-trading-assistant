import React, { useEffect, useMemo, useRef, useState } from "react";
import { CandlestickSeries, CrosshairMode, HistogramSeries, LineSeries, createChart } from "lightweight-charts";
import * as I from "@phosphor-icons/react";
import "./trading-chart.css";

const PERIOD_SECONDS = { "1分":60,"5分":300,"15分":900,"30分":1800,"45分":2700,"分时":300,"1时":3600,"4时":14400,"8时":28800,"1日":86400,"1周":604800,"1月":2592000 };

function seededCandles(base, period, variant = 0) {
  const step = PERIOD_SECONDS[period] || 300;
  const count = variant ? 84 : 132;
  const end = Math.floor(Date.now() / step) * step;
  let close = base * (variant ? .965 : .982);
  return Array.from({ length: count }, (_, index) => {
    const wave = Math.sin((index + variant * 11) / 7) * base * .0017;
    const drift = base * .00024 + Math.cos(index / 13) * base * .00035;
    const open = close;
    close = Math.max(base * .82, open + wave * .42 + drift);
    const high = Math.max(open, close) + base * (.0012 + ((index * 7) % 9) * .00012);
    const low = Math.min(open, close) - base * (.0011 + ((index * 5) % 8) * .00011);
    return { time: end - (count - index) * step, open, high, low, close, volume: 90 + ((index * 37 + variant * 41) % 420) };
  });
}

function movingAverage(candles, length) {
  return candles.slice(length - 1).map((item, index) => ({
    time: item.time,
    value: candles.slice(index, index + length).reduce((sum, candle) => sum + candle.close, 0) / length,
  }));
}

function emaValues(candles, length) {
  const factor = 2 / (length + 1);
  let value = candles[0]?.close || 0;
  return candles.map((candle) => {
    value = candle.close * factor + value * (1 - factor);
    return value;
  });
}

function indicatorSnapshot(candles) {
  if (candles.length < 15) return { rsi: 50, macd: 0, signal: 0, kdj: 50 };
  let gains = 0, losses = 0;
  candles.slice(-15).forEach((candle, index, rows) => {
    if (!index) return;
    const diff = candle.close - rows[index - 1].close;
    if (diff >= 0) gains += diff; else losses -= diff;
  });
  const rsi = losses === 0 ? 100 : 100 - 100 / (1 + gains / losses);
  const ema12 = emaValues(candles, 12), ema26 = emaValues(candles, 26);
  const macdRows = ema12.map((value, index) => value - ema26[index]);
  let signal = macdRows[0] || 0;
  macdRows.forEach((value) => { signal = value * (2 / 10) + signal * (8 / 10); });
  const range = candles.slice(-9), high = Math.max(...range.map((item)=>item.high)), low = Math.min(...range.map((item)=>item.low));
  const kdj = high === low ? 50 : ((candles.at(-1).close - low) / (high - low)) * 100;
  return { rsi, macd: macdRows.at(-1) || 0, signal, kdj };
}

function renderDrawing(drawing) {
  const x1=Math.max(1,drawing.x-10),x2=Math.min(99,drawing.x+12),y1=Math.min(98,drawing.y+8),y2=Math.max(2,drawing.y-8);
  if(drawing.type==="水平线") return <line key={drawing.id} x1="0" y1={drawing.y} x2="100" y2={drawing.y}/>;
  if(drawing.type==="矩形") return <rect key={drawing.id} x={drawing.x-8} y={drawing.y-6} width="16" height="12"/>;
  if(drawing.type==="平行线") return <g key={drawing.id}><line x1={x1} y1={y1} x2={x2} y2={y2}/><line x1={x1} y1={y1+7} x2={x2} y2={y2+7}/></g>;
  if(drawing.type==="测量") return <g key={drawing.id}><line x1={x1} y1={drawing.y} x2={x2} y2={drawing.y}/><text x={drawing.x-4} y={drawing.y-3}>+4.82%</text></g>;
  if(drawing.type==="文本") return <text key={drawing.id} x={drawing.x-5} y={drawing.y}>交易注释</text>;
  if(drawing.type==="斐波那契") return <g key={drawing.id}>{[0,4,8,12,16].map((offset,index)=><g key={offset}><line x1={x1} y1={drawing.y-8+offset} x2={x2} y2={drawing.y-8+offset}/><text x={x2+1} y={drawing.y-7+offset}>{["0",".236",".5",".618","1"][index]}</text></g>)}</g>;
  if(drawing.type==="画笔") return <path key={drawing.id} d={`M ${x1} ${drawing.y+5} Q ${drawing.x-5} ${drawing.y-10}, ${drawing.x} ${drawing.y} T ${x2} ${drawing.y-5}`}/>;
  return <line key={drawing.id} x1={x1} y1={y1} x2={x2} y2={y2}/>;
}

function TradingChartSurface({ symbol, instrument, marketMode = "web3", externalCandles = [], period, quote, studies, variant = 0, venue = "币安", replayMode = false, chartType = "蜡烛图", onPeriodChange, redUp = false }) {
  const container = useRef(null);
  const candles = useMemo(() => {
    const all = externalCandles.length >= 8 && variant === 0 ? externalCandles : seededCandles(Number(quote.price), period, variant);
    return replayMode ? all.slice(0, Math.max(28, Math.floor(all.length * .62))) : all;
  }, [quote.price, period, variant, replayMode, externalCandles]);
  const indicators = useMemo(() => indicatorSnapshot(candles), [candles]);
  const upColor = redUp ? "#ed5362" : "#20b486";
  const downColor = redUp ? "#20b486" : "#ed5362";
  useEffect(() => {
    if (!container.current) return undefined;
    const chart = createChart(container.current, {
      autoSize: true,
      layout: { background: { color: "#ffffff" }, textColor: "#7a8490", fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace", fontSize: 10, attributionLogo: true },
      grid: { vertLines: { color: studies.includes("网格线") ? "#eef1f3" : "#ffffff" }, horzLines: { color: studies.includes("网格线") ? "#eef1f3" : "#ffffff" } },
      crosshair: { mode: CrosshairMode.Normal, vertLine: { color: "#77838f", style: 3, labelBackgroundColor: "#39434d" }, horzLine: { color: "#77838f", style: 3, labelBackgroundColor: "#39434d" } },
      rightPriceScale: { borderColor: "#dfe4e7", scaleMargins: { top: .08, bottom: studies.includes("Volume") ? .22 : .08 } },
      timeScale: { borderColor: "#dfe4e7", timeVisible: true, secondsVisible: false, rightOffset: 4, barSpacing: variant ? 7 : 6, minBarSpacing: 2 },
      handleScroll: { mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: false },
      handleScale: { axisPressedMouseMove: true, mouseWheel: true, pinch: true },
    });
    const lineMode = chartType === "折线图" || chartType === "面积图";
    const candleSeries = lineMode
      ? chart.addSeries(LineSeries, { color: upColor, lineWidth: chartType === "面积图" ? 3 : 2, priceLineVisible: studies.includes("价格线"), lastValueVisible: studies.includes("价格线") })
      : chart.addSeries(CandlestickSeries, { upColor: chartType === "空心蜡烛" ? "#ffffff" : upColor, downColor, borderVisible: chartType === "空心蜡烛", borderUpColor: upColor, borderDownColor: downColor, wickUpColor: upColor, wickDownColor: downColor, priceLineVisible: studies.includes("价格线"), lastValueVisible: studies.includes("价格线"), priceLineColor: Number(quote.change.replace("%","")) >= 0 ? upColor : downColor });
    candleSeries.setData(lineMode ? candles.map((candle)=>({time:candle.time,value:candle.close})) : candles.map(({ volume, ...candle }) => candle));
    if (studies.includes("MA") || studies.includes("EMA")) {
      const ma7 = chart.addSeries(LineSeries, { color: "#e6a23c", lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
      const ma25 = chart.addSeries(LineSeries, { color: "#4d8df7", lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
      ma7.setData(movingAverage(candles, 7));
      ma25.setData(movingAverage(candles, 25));
    }
    if (studies.includes("EMA")) {
      const ema = chart.addSeries(LineSeries, { color: "#8b5cf6", lineWidth: 2, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
      ema.setData(candles.map((item,index)=>({time:item.time,value:emaValues(candles,12)[index]})));
    }
    if (studies.includes("BOLL")) {
      const middle=movingAverage(candles,20);
      const upper=middle.map((item,index)=>{const rows=candles.slice(index,index+20);const deviation=Math.sqrt(rows.reduce((sum,row)=>sum+(row.close-item.value)**2,0)/rows.length);return {...item,value:item.value+deviation*2}});
      const lower=middle.map((item,index)=>{const rows=candles.slice(index,index+20);const deviation=Math.sqrt(rows.reduce((sum,row)=>sum+(row.close-item.value)**2,0)/rows.length);return {...item,value:item.value-deviation*2}});
      [[upper,"#7c6ee6"],[middle,"#b08d36"],[lower,"#7c6ee6"]].forEach(([data,color])=>{const series=chart.addSeries(LineSeries,{color,lineWidth:1,priceLineVisible:false,lastValueVisible:false,crosshairMarkerVisible:false});series.setData(data)});
    }
    if (studies.includes("VWAP")) {
      let cumulativePV=0,cumulativeVolume=0;
      const vwap=chart.addSeries(LineSeries,{color:"#9a63d7",lineWidth:2,priceLineVisible:false,lastValueVisible:true,crosshairMarkerVisible:false});
      vwap.setData(candles.map((item)=>{cumulativePV+=((item.high+item.low+item.close)/3)*item.volume;cumulativeVolume+=item.volume;return {time:item.time,value:cumulativeVolume?cumulativePV/cumulativeVolume:item.close}}));
    }
    if (studies.includes("委托线")) candleSeries.createPriceLine({ price:Number(quote.price)*.994, color:"#ed5362", lineWidth:1, lineStyle:2, axisLabelVisible:true, title:"模拟委托" });
    if (studies.includes("持仓成本线")) candleSeries.createPriceLine({ price:Number(quote.price)*.982, color:"#e0a42d", lineWidth:1, lineStyle:2, axisLabelVisible:true, title:"持仓成本" });
    if (studies.includes("Volume")) {
      const volume = chart.addSeries(HistogramSeries, { priceFormat: { type: "volume" }, priceScaleId: "volume", priceLineVisible: false, lastValueVisible: false });
      volume.priceScale().applyOptions({ scaleMargins: { top: .82, bottom: 0 } });
      volume.setData(candles.map((item) => ({ time: item.time, value: item.volume, color: item.close >= item.open ? `${upColor}66` : `${downColor}66` })));
    }
    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [candles, quote.change, studies, chartType, redUp, upColor, downColor]);
  const indicatorValue=(name)=>name==="RSI"?indicators.rsi.toFixed(2):name==="MACD"?`${indicators.macd.toFixed(2)} / ${indicators.signal.toFixed(2)}`:name==="KDJ"?indicators.kdj.toFixed(2):name==="资金费率"?"0.0081%":name==="持仓量(OI)"?"$18.42B":"—";
  const periods=marketMode==="stocks"?["分时","5分","15分","30分","1时","1日","1周","1月"]:["1分","5分","15分","45分","分时","1时","4时","8时","1日","1周"];
  return <div className="tv-chart-pane"><header><b>{instrument || `${symbol}/USDT`} · {venue}</b><label><select aria-label={`第${variant+1}个K线窗口周期`} value={period} onChange={(event)=>onPeriodChange?.(event.target.value)}>{periods.map((value)=><option key={value}>{value}</option>)}</select></label><span>{chartType} · {marketMode==="stocks"?"美东交易时段":"7×24小时"} · {replayMode?"复盘未来K线已截断":studies.includes("倒计时")?"距收线 00:38":"实时演示"}</span></header><div ref={container} className="tv-chart-canvas" />{studies.includes("买卖信号")&&<div className="tv-signal-layer"><i className="buy">B</i><i className="sell">S</i><i className="buy">B</i></div>}{["RSI","MACD","KDJ","资金费率","持仓量(OI)"].some((name)=>studies.includes(name))&&<div className="tv-study-readout">{["RSI","MACD","KDJ","资金费率","持仓量(OI)"].filter((name)=>studies.includes(name)).map((name)=><span key={name}><b>{name}</b>{indicatorValue(name)}</span>)}</div>}{studies.includes("筹码分布")&&<div className="tv-chip-profile">{Array.from({length:16},(_,index)=><i key={index} style={{width:`${30+((index*17)%65)}%`}}/> )}</div>}</div>;
}

function DrawingOverlay({ drawings, drawingTool, drawingLocked, magnetEnabled, onDraw, trackedTraders, openOverlay, onOpenContext }) {
  return <div className={`tv-drawing-overlay ${drawingTool !== "光标" ? "active" : ""}`} aria-label="TradingView K线绘图区" onContextMenu={(event)=>{event.preventDefault();event.stopPropagation();const rect=event.currentTarget.getBoundingClientRect();onOpenContext?.({x:event.clientX-rect.left,y:event.clientY-rect.top,ratioY:(event.clientY-rect.top)/rect.height})}} onClick={(event)=>{const rect=event.currentTarget.getBoundingClientRect();onDraw({x:((event.clientX-rect.left)/rect.width)*100,y:((event.clientY-rect.top)/rect.height)*100})}}>
    <svg viewBox="0 0 100 100" preserveAspectRatio="none">{drawings.map(renderDrawing)}</svg>
    {trackedTraders.map((trader,index)=><button className={`tv-trader-marker ${trader.side==="卖出"?"sell":"buy"}`} style={{left:`${20+(index*27)%65}%`,top:`${18+(index*19)%58}%`}} key={`${trader.market}-${trader.name}`} onClick={(event)=>{event.stopPropagation();openOverlay("trader",trader.name,{description:`${trader.market} · ${trader.side} ${trader.symbol}/USDT · ${trader.price}`})}}>{trader.side}<small>{trader.name}</small></button>)}
    {drawingTool!=="光标"&&<span><I.PencilLine/>{drawingLocked?"画线已锁定":`${drawingTool}${magnetEnabled?" · 磁吸":""}`}</span>}
  </div>;
}

export function TradingChartGrid({ layout, symbol, instrument, marketMode, externalCandles = [], period, quote, venue, chartType, studies, drawings, drawingTool, drawingLocked, magnetEnabled, onDraw, trackedTraders = [], openOverlay = () => {}, replayMode = false, panePeriods = [], onPanePeriodChange, onCreateAlert, onPrefillOrder, onToggleWatch, onClearDrawings, onStartReplay, onResetChart, resetSignal = 0, redUp = false }) {
  const [context,setContext]=useState(null);
  const panes = Number(layout) || (layout === "九窗" ? 9 : layout === "六窗" ? 6 : layout === "四窗" ? 4 : layout === "双窗" ? 2 : 1);
  const contextAction=(action)=>{action();setContext(null)};
  const columns = panes <= 1 ? 1 : panes <= 4 ? 2 : panes <= 9 ? 3 : panes <= 16 ? 4 : 6;
  return <div className={`tv-chart-grid panes-${panes} ${panes > 4 ? "dense-panes" : ""} ${redUp?"red-up":"green-up"}`} style={{gridTemplateColumns:`repeat(${columns},minmax(0,1fr))`}}>
    {Array.from({length:panes},(_,index)=><TradingChartSurface key={`${symbol}-${index}-${resetSignal}`} symbol={symbol} instrument={instrument} marketMode={marketMode} externalCandles={index===0?externalCandles:[]} period={index===0?period:panePeriods[index] || "15分"} quote={quote} venue={venue} chartType={chartType} studies={studies} variant={index} replayMode={replayMode} redUp={redUp} onPeriodChange={(value)=>onPanePeriodChange?.(index,value)}/>) }
    <div className="tv-advanced-markers">{(studies.includes("大额成交")||studies.includes("主力大单"))&&<><button className="large buy" onClick={()=>openOverlay("flash","大额买入详情",{description:`${symbol}/USDT · $2.18M 主动买入`})}>大额买入 $2.18M</button><button className="large sell" onClick={()=>openOverlay("flash","大额卖出详情",{description:`${symbol}/USDT · $0.86M 主动卖出`})}>大额卖出 $0.86M</button></>}{studies.includes("主力挂单统计")&&<span className="main-order">主力挂买 +$12.4M</span>}{studies.includes("指标胜率")&&<span className="winrate">当前信号胜率 68.4%</span>}</div>
    <DrawingOverlay drawings={drawings} drawingTool={drawingTool} drawingLocked={drawingLocked} magnetEnabled={magnetEnabled} onDraw={onDraw} trackedTraders={trackedTraders} openOverlay={openOverlay} onOpenContext={({x,y,ratioY})=>setContext({x,y,price:Number(quote.price)*(1+(0.5-ratioY)*.08)})}/>
    {context&&<aside className="tv-context-menu" style={{left:Math.min(context.x,520),top:Math.min(context.y,260)}} onClick={(event)=>event.stopPropagation()}><header><span>{symbol}/USDT</span><b>{context.price.toFixed(quote.decimals)}</b></header><button onClick={()=>contextAction(()=>onCreateAlert?.(context.price))}><I.BellRinging/>在此价格添加预警</button><button onClick={()=>contextAction(()=>onPrefillOrder?.(context.price,"买入"))}><I.ArrowCircleDown/>限价买入</button><button onClick={()=>contextAction(()=>onPrefillOrder?.(context.price,"卖出"))}><I.ArrowCircleUp/>限价卖出</button><button onClick={()=>contextAction(()=>onToggleWatch?.())}><I.Star/>切换自选</button><button onClick={()=>contextAction(()=>onStartReplay?.())}><I.Play/>从此开始K线复盘</button><button onClick={()=>contextAction(()=>onResetChart?.())}><I.ArrowCounterClockwise/>重置图表视图</button><button disabled={!drawings.length} onClick={()=>contextAction(()=>onClearDrawings?.())}><I.Trash/>清除全部绘图</button><button className="close" onClick={()=>setContext(null)}><I.X/>关闭菜单</button></aside>}
  </div>;
}
