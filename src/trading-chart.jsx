import {canUpdateCurrentCandle,candleStructureKey} from './chart-live-update.js';
import { CHART_TYPES } from "./chart-pane-appearance.js";
import { heikinAshiBars, hlcPlotBars, chartPriceLineRising, chartReadoutRising, candleChangeMetrics, cursorPriceDifference } from "./chart-candle-style.js";
import { ChartGridDividers } from "./chart-grid-dividers.jsx";
import { gridTemplate, gridRows } from "./chart-grid-geometry.js";
import { downloadChartData } from "./chart-data-export.js";
import { MarketCsvControl } from "./market-csv-control.jsx";
import { exportChartPng } from "./chart-image-export.js";
import { replayVisibleBars } from "./chart-replay.js";
import { ChartPriceRangeControl } from "./chart-axis-control.jsx";
import { DEFAULT_CHART_AXIS, chartAxisOptions, storedPriceRange, applyExactPriceRange } from "./chart-axis.js";
import { ChartDrawingManager } from "./chart-drawing-manager.jsx";
import { ChartDrawingLayer } from "./chart-drawing-layer.jsx";
import { chartContextAt } from "./chart-context.js";
import { validLogicalRange, viewportRange, zoomLogicalRange } from "./chart-viewport.js";
import { calculateOscillators, ema } from "./market-indicators.js";
import React, { useEffect, useMemo, useRef, useState } from "react";
import { AreaSeries, BarSeries, CandlestickSeries, CrosshairMode, HistogramSeries, LineSeries, createChart } from "lightweight-charts";
import * as I from "@phosphor-icons/react";
import "./trading-chart.css";

import { createChartSync, demoMarketBars, periodCountdown, periodDefinition } from "./market-chart-model.js";
import { observeCandleFeed } from "./live-market-candles.js";

function CandleCountdown({ period }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => { const timer = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(timer); }, []);
  return <>UTC周期剩余 {periodCountdown(period, now)}</>;
}

function movingAverage(candles, length) {
  return candles.slice(length - 1).map((item, index) => ({
    time: item.time,
    value: candles.slice(index, index + length).reduce((sum, candle) => sum + candle.close, 0) / length,
  }));
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

function TradingChartSurface({ background="#ffffff", onAppearanceChange, symbol, instrument, marketMode = "web3", externalCandles = [], period, quote, studies, variant = 0, venue = "币安", replayMode = false, replayTime = null, chartType = "蜡烛图", onPeriodChange, onSymbolChange, symbolOptions = [], onStudiesChange, redUp = false, sync, viewportStore, onViewportChange, onOpenContext, drawings = [], drawingTool = "光标", drawingLocked = false, magnetEnabled = false, onDraw, onUpdateDrawing, onDeleteDrawing, axis = DEFAULT_CHART_AXIS, onAxisChange, timeRequest, csvIdentity, csvLoaded, onCsvApply, onCsvClear, replayActive, dataKind = "backend", volumeAvailable = true, dataIsDemo = false, dataSource = "后端未连接", dataStatus = "offline" }) {
  const demoData = dataIsDemo || !externalCandles.length;
  const waitingForMarket = dataStatus === "loading" && !externalCandles.length && !replayMode;
  const container = useRef(null);
  const chartApi = useRef(null);
  const priceSeriesApi = useRef(null);
  const rememberViewport=useRef(null);
  const previousReplayBar=useRef(null);
  const [rangeRestoreError,setRangeRestoreError]=useState("");
  const [exportState,setExportState]=useState("");
  const downloadChart=async()=>{if(exportState==="导出中")return;setExportState("导出中");try{await exportChartPng({chart:chartApi.current,container:container.current,filename:`${symbol}-${period}-chart.png`,caption:`${marketMode==="stocks"?symbol:`${symbol}/USDT`} · ${venue} · ${period} · ${dataKind==="csv"?"本地CSV":demoData?"演示数据":"行情快照"}${replayMode?" · 复盘":""} · ${dataSource} · Lightweight Charts · 导出时间 ${new Date().toISOString()}`});setExportState("PNG已生成");}catch(error){setExportState(error.message);}};
  const changeAxis=next=>{if(!next.autoScale&&next.mode===axis.mode){chartApi.current?.priceScale("right").applyOptions({autoScale:false});rememberViewport.current?.();}onAxisChange?.(next);};
  const [projectionRevision,setProjectionRevision] = useState(0);
  const projectionFrame=useRef(null);
  const redraw=()=>{if(projectionFrame.current===null)projectionFrame.current=requestAnimationFrame(()=>{projectionFrame.current=null;setProjectionRevision(value=>value+1);});};
  useEffect(()=>()=>{if(projectionFrame.current!==null)cancelAnimationFrame(projectionFrame.current);},[]);
  const viewKey = `${symbol}:${venue}:${period}:${replayMode?"replay":"full"}`;
  const candles = useMemo(() => {
    const all = externalCandles.length ? externalCandles : demoMarketBars(Number(quote.price), period, `${symbol}:${venue}`);
    const available=replayMode ? replayVisibleBars(all,replayTime,period) : all;
    return chartType==="平均K线"?heikinAshiBars(available):available;
  }, [quote.price, period, symbol, venue, replayMode, replayTime, externalCandles, chartType]);
  const currentUpdate=useRef(null),latestCandles=useRef(candles);latestCandles.current=candles;
  const currentOnly=canUpdateCurrentCandle(studies,replayMode);
  const structureKey=candleStructureKey(candles,currentOnly);
  // Stable while only the current bar changes; all historical corrections rebuild.
  const structureCandles=useMemo(()=>candles,[structureKey]);
  const [hoverTime,setHoverTime]=useState(null);
  const [cursorPrice,setCursorPrice]=useState(null);
  const readout=candles.find(bar=>bar.time===hoverTime)||candles.at(-1);
  const cursorDifference=hoverTime!==null?cursorPriceDifference(cursorPrice,candles.at(-1)?.close):null;
  const changeMetrics=candleChangeMetrics(candles,candles.indexOf(readout));
  const formatReadout=value=>Number(value).toLocaleString("en-US",{minimumFractionDigits:quote.decimals??2,maximumFractionDigits:quote.decimals??2});
  const indicators = useMemo(() => calculateOscillators(candles), [candles]);
  const upColor = redUp ? "#ed5362" : "#20b486";
  const downColor = redUp ? "#20b486" : "#ed5362";
  useEffect(() => {
    if (!container.current) return undefined;
    setCursorPrice(null);setHoverTime(null);
    const chart = createChart(container.current, {
      autoSize: true,
      layout: { background: { color: background }, textColor: "#7a8490", fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace", fontSize: 10, attributionLogo: true },
      grid: { vertLines: { color: studies.includes("网格线") ? "#eef1f3" : background }, horzLines: { color: studies.includes("网格线") ? "#eef1f3" : background } },
      crosshair: { mode: CrosshairMode.Normal, vertLine: { color: "#77838f", style: 3, labelBackgroundColor: "#39434d" }, horzLine: { color: "#77838f", style: 3, labelBackgroundColor: "#39434d" } },
      rightPriceScale: { borderColor: "#dfe4e7", scaleMargins: { top: .08, bottom: studies.includes("Volume") ? .22 : .08 } },
      timeScale: { borderColor: "#dfe4e7", timeVisible: true, secondsVisible: (periodDefinition(period).seconds || 60) < 60, rightOffset: 4, barSpacing: variant ? 7 : 6, minBarSpacing: 2 },
      handleScroll: { mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: false },
      handleScale: { axisPressedMouseMove: true, mouseWheel: true, pinch: true },
    });
    const refreshSeries=[];
    const lineMode = chartType === "折线图" || chartType === "面积图";
    const candleSeries = lineMode
      ? chart.addSeries(chartType === "面积图" ? AreaSeries : LineSeries, { color: upColor, lineColor: upColor, topColor: `${upColor}66`, bottomColor: `${upColor}05`, lineWidth: 2, priceLineVisible: studies.includes("价格线"), lastValueVisible: studies.includes("价格线") })
      : chartType === "美国线" ? chart.addSeries(BarSeries,{upColor,downColor,openVisible:true,thinBars:true,priceLineVisible:studies.includes("价格线"),lastValueVisible:studies.includes("价格线")}) : chart.addSeries(CandlestickSeries, { upColor: chartType === "空心蜡烛" ? "#ffffff" : upColor, downColor, borderVisible: chartType === "空心蜡烛", borderUpColor: upColor, borderDownColor: downColor, wickUpColor: upColor, wickDownColor: downColor, priceLineVisible: studies.includes("价格线"), lastValueVisible: studies.includes("价格线"), priceLineColor: chartPriceLineRising(candles,chartType) ? upColor : downColor });
    candleSeries.applyOptions({visible:!studies.includes("隐藏主图"),priceLineColor:chartPriceLineRising(candles,chartType)?upColor:downColor,priceFormat:{type:"price",precision:Math.min(8,Math.max(0,quote.decimals??2)),minMove:10**-Math.min(8,Math.max(0,quote.decimals??2))}});
    priceSeriesApi.current=candleSeries;
    container.current.dataset.candleCount=String(candles.length);
    container.current.dataset.chartType=chartType;
    container.current.dataset.mainChartVisible=String(!studies.includes("隐藏主图"));
    container.current.dataset.lastCandle=String(candles.at(-1)?.time||"");
    const plotCandles=chartType==="K线图(HLC)"?hlcPlotBars(candles):candles;
    candleSeries.setData(lineMode ? candles.map((candle)=>({time:candle.time,value:candle.close})) : plotCandles.map(({ volume, ...candle }) => candle));
    if (studies.includes("MA")) {
      const ma7 = chart.addSeries(LineSeries, { color: "#e6a23c", lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
      const ma25 = chart.addSeries(LineSeries, { color: "#4d8df7", lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
      ma7.setData(movingAverage(candles, 7));
      ma25.setData(movingAverage(candles, 25));
      refreshSeries.push(next=>{ma7.setData(movingAverage(next,7));ma25.setData(movingAverage(next,25));});
    }
    if (studies.includes("EMA")) {
      const emaSeries = chart.addSeries(LineSeries, { color: "#8b5cf6", lineWidth: 2, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
      const values = ema(candles.map(row=>row.close),12);
      emaSeries.setData(candles.map((item,index)=>({time:item.time,value:values[index]})));
      refreshSeries.push(next=>{const values=ema(next.map(row=>row.close),12);emaSeries.setData(next.map((item,index)=>({time:item.time,value:values[index]})));});
    }
    const bollRows=next=>{
      const middle=movingAverage(next,20);
      const band=sign=>middle.map((item,index)=>{const rows=next.slice(index,index+20);const deviation=Math.sqrt(rows.reduce((sum,row)=>sum+(row.close-item.value)**2,0)/rows.length);return {...item,value:item.value+sign*deviation*2};});
      return [band(1),middle,band(-1)];
    };
    if (studies.includes("BOLL")) {
      const series=["#7c6ee6","#b08d36","#7c6ee6"].map(color=>chart.addSeries(LineSeries,{color,lineWidth:1,priceLineVisible:false,lastValueVisible:false,crosshairMarkerVisible:false}));
      const refresh=next=>bollRows(next).forEach((rows,index)=>series[index].setData(rows));refresh(candles);refreshSeries.push(refresh);
    }
    if (studies.includes("VWAP") && volumeAvailable) {
      const vwap=chart.addSeries(LineSeries,{color:"#9a63d7",lineWidth:2,priceLineVisible:false,lastValueVisible:true,crosshairMarkerVisible:false});
      const refresh=next=>{let pv=0,volume=0;vwap.setData(next.map(item=>{pv+=((item.high+item.low+item.close)/3)*item.volume;volume+=item.volume;return {time:item.time,value:volume?pv/volume:item.close};}));};refresh(candles);refreshSeries.push(refresh);
    }
    if (studies.includes("委托线")) candleSeries.createPriceLine({ price:Number(quote.price)*.994, color:"#ed5362", lineWidth:1, lineStyle:2, axisLabelVisible:true, title:"模拟委托" });
    if (studies.includes("持仓成本线")) candleSeries.createPriceLine({ price:Number(quote.price)*.982, color:"#e0a42d", lineWidth:1, lineStyle:2, axisLabelVisible:true, title:"持仓成本" });
    if (studies.includes("Volume") && volumeAvailable) {
      const volume = chart.addSeries(HistogramSeries, { priceFormat: { type: "volume" }, priceScaleId: "volume", priceLineVisible: false, lastValueVisible: false });
      volume.priceScale().applyOptions({ scaleMargins: { top: .82, bottom: 0 } });
      volume.setData(candles.map((item) => ({ time: item.time, value: item.volume, color: item.close >= item.open ? `${upColor}66` : `${downColor}66` })));
      refreshSeries.push(next=>volume.setData(next.map(item=>({time:item.time,value:item.volume,color:item.close>=item.open?`${upColor}66`:`${downColor}66`}))));
    }
    let paneIndex=1;
    const addOscillatorLine=(rows,key,color,pane,title,kind)=>{
      const series=chart.addSeries(LineSeries,{color,lineWidth:1,title,priceLineVisible:false,lastValueVisible:true},pane);
      series.setData(rows.map(row=>({time:row.time,value:row[key]})));
      refreshSeries.push((next,osc)=>series.setData(osc[kind].map(row=>({time:row.time,value:row[key]}))));
      return series;
    };
    if(studies.includes("RSI")) {
      const series=addOscillatorLine(indicators.rsi,"value","#8b5cf6",paneIndex++,"RSI14","rsi");
      for(const price of [30,70]) series.createPriceLine({price,color:"#aab2bc",lineWidth:1,lineStyle:2,axisLabelVisible:false});
    }
    if(studies.includes("MACD")) {
      const pane=paneIndex++;
      addOscillatorLine(indicators.macd,"dif","#e6a23c",pane,"DIF12/26","macd");
      addOscillatorLine(indicators.macd,"dea","#4d8df7",pane,"DEA9","macd");
      const histogram=chart.addSeries(HistogramSeries,{priceLineVisible:false,lastValueVisible:false,title:"MACD×2"},pane);
      histogram.setData(indicators.macd.map(row=>({time:row.time,value:row.histogram,color:row.histogram>=0?upColor:downColor})));
      refreshSeries.push((next,osc)=>histogram.setData(osc.macd.map(row=>({time:row.time,value:row.histogram,color:row.histogram>=0?upColor:downColor}))));
    }
    if(studies.includes("KDJ")) {
      const pane=paneIndex++;
      for(const [key,color] of [["k","#e6a23c"],["d","#4d8df7"],["j","#8b5cf6"]]) addOscillatorLine(indicators.kdj,key,color,pane,`${key.toUpperCase()}9/3/3`,"kdj");
    }
    currentUpdate.current=next=>{
      const last=next.at(-1);if(!last)return;
      const plot=chartType==="K线图(HLC)"?hlcPlotBars(next).at(-1):last;
      const {volume,...bar}=plot;
      candleSeries.update(lineMode?{time:last.time,value:last.close}:bar);
      candleSeries.applyOptions({priceLineColor:chartPriceLineRising(next,chartType)?upColor:downColor});
      const osc=calculateOscillators(next);refreshSeries.forEach(refresh=>refresh(next,osc));redraw();
    };
    container.current.dataset.chartInstance=crypto.randomUUID();
    chart.panes().forEach((pane,index)=>{ if(index) pane.setHeight(90); });
    const scale = chart.timeScale();
    const viewportGeneration=viewportStore?.current;
    const restored=viewportRange(viewportStore?.current[variant],viewKey,candles);
    if(restored?.logical) scale.setVisibleLogicalRange(restored.logical);
    else if(restored?.time) scale.setVisibleRange(restored.time);
    else scale.fitContent();
    const lastReplay=candles.at(-1)?.time;
    if(replayMode&&lastReplay&&(previousReplayBar.current?.last!==lastReplay||previousReplayBar.current?.key!==viewKey)){
      const old=viewportStore?.current[variant],span=old?.key===viewKey&&validLogicalRange(old.logical)?old.logical.to-old.logical.from:Math.min(60,candles.length)+3;
      scale.setVisibleLogicalRange({from:Math.max(0,candles.length+3-span),to:candles.length+3});
    }
    previousReplayBar.current={key:viewKey,last:lastReplay};
    chart.priceScale("right").applyOptions(chartAxisOptions(axis));
    const savedPrice=storedPriceRange(viewportGeneration?.[variant],viewKey,axis);if(savedPrice){try{applyExactPriceRange(chart.priceScale("right"),savedPrice);}catch(error){setRangeRestoreError(`价格范围未恢复：${error.message}，已改用自动范围`);onAxisChange?.({...axis,autoScale:true});}}
    container.current.dataset.priceAxis=JSON.stringify({mode:chart.priceScale("right").options().mode,invertScale:chart.priceScale("right").options().invertScale,autoScale:chart.priceScale("right").options().autoScale});
    chartApi.current=chart;redraw();
    const drawingResize=new ResizeObserver(redraw);drawingResize.observe(container.current);
    const unregister = sync?.register(variant, {
      timeline:candles.map(row=>row.time).join(","),
      logicalRange(range){scale.setVisibleLogicalRange(range);},
      crosshair(time) { const row = latestCandles.current.find(item => item.time === time);setHoverTime(row?.time??null);setCursorPrice(row?.close??null); if (row) chart.setCrosshairPosition(row.close, row.time, candleSeries); else chart.clearCrosshairPosition(); },
      timeRange(range) { scale.setVisibleRange(range); },
      zoom(span) { const range = scale.getVisibleLogicalRange(); if (range) scale.setVisibleLogicalRange({ from: range.to - span, to: range.to }); },
    });
    const crosshair = event => {setHoverTime(typeof event.time==="number"?event.time:null);if(event.sourceEvent){const price=event.point&&(event.paneIndex??0)===0?candleSeries.coordinateToPrice(event.point.y):null;setCursorPrice(price);sync?.crosshair(variant,event.time);}};
    const remember = logical => {
      if(!validLogicalRange(logical)||!candles.length || (viewportStore && viewportStore.current!==viewportGeneration))return;
      const timeRange=scale.getVisibleRange();
      const view={key:viewKey,logical:{from:logical.from,to:logical.to},first:candles[0].time,last:candles.at(-1).time,barCount:candles.length,timeRange:timeRange && typeof timeRange.from==="number" && typeof timeRange.to==="number" && timeRange.to>timeRange.from ? timeRange:null};
      const priceScale=chart.priceScale("right"),priceRange=priceScale.getVisibleRange(),options=priceScale.options();
      if(!options.autoScale&&options.mode!==2&&priceRange&&Number.isFinite(priceRange.from)&&Number.isFinite(priceRange.to)&&priceRange.from>0&&priceRange.to>priceRange.from){view.priceRange=priceRange;view.priceMode=options.mode===1?"logarithmic":"linear";}
      if(container.current){container.current.dataset.visiblePriceRange=JSON.stringify(priceRange);container.current.dataset.visibleLogicalRange=JSON.stringify(view.logical);container.current.dataset.candleBounds=JSON.stringify({first:view.first,last:view.last,count:candles.length});}
      if(viewportStore){const previous=viewportStore.current[variant];viewportStore.current[variant]=view;if(JSON.stringify(previous)!==JSON.stringify(view))onViewportChange?.();}
      if(container.current){container.current.dataset.visibleRange=JSON.stringify(view.logical);container.current.dataset.visibleTimeRange=JSON.stringify(view.timeRange);}
    };
    // Initial layout/data notifications are restoration, not user navigation.
    let rangeSyncReady=false,settleFrame=null;
    const initialFrame=requestAnimationFrame(()=>{settleFrame=requestAnimationFrame(()=>{rangeSyncReady=true;});});
    const range = logical => { redraw();remember(logical);if(rangeSyncReady)sync?.range(variant, logical, scale.getVisibleRange()); };
    rememberViewport.current=()=>remember(scale.getVisibleLogicalRange());
    rememberViewport.current();
    chart.subscribeCrosshairMove(crosshair);
    scale.subscribeVisibleLogicalRangeChange(range);
    return () => {cancelAnimationFrame(initialFrame);if(settleFrame!==null)cancelAnimationFrame(settleFrame);drawingResize.disconnect();currentUpdate.current=null;rememberViewport.current=null;unregister?.(); chart.unsubscribeCrosshairMove(crosshair); scale.unsubscribeVisibleLogicalRangeChange(range); chartApi.current=null;priceSeriesApi.current=null;chart.remove(); };
  }, [structureCandles, quote.decimals, studies, chartType, redUp, upColor, downColor, sync, variant, viewKey, viewportStore, axis, volumeAvailable, background]);
  useEffect(()=>{if(currentOnly)currentUpdate.current?.(candles);},[candles,currentOnly]);
  useEffect(()=>{
    if(variant!==0||!timeRequest||!chartApi.current)return;
    const scale=chartApi.current.timeScale();scale.setVisibleLogicalRange(timeRequest.logical);
    sync?.range(variant,timeRequest.logical,scale.getVisibleRange(),true);
    rememberViewport.current?.();redraw();
  },[timeRequest,variant]);
  const indicatorValue=(name)=>{
    if(name==="RSI") return indicators.rsi.at(-1)?.value.toFixed(2) ?? "不足15根";
    if(name==="MACD") {const row=indicators.macd.at(-1);return row?`${row.dif.toFixed(2)} / ${row.dea.toFixed(2)}`:"无数据";}
    if(name==="KDJ") {const row=indicators.kdj.at(-1);return row?`${row.k.toFixed(2)} / ${row.d.toFixed(2)} / ${row.j.toFixed(2)}`:"不足9根";}
    return "数据未接入";
  };
  const periods=marketMode==="stocks"?["分时","5分","15分","30分","1时","1日","1周","1月"]:["1分","5分","15分","45分","分时","1时","4时","8时","1日","1周"];
  return <div className="tv-chart-pane"><header title={dataSource}><label><select aria-label={`第${variant+1}个K线窗口交易对`} value={symbol} onChange={event=>onSymbolChange?.(event.target.value)}>{[...new Set([symbol,...symbolOptions])].map(value=><option key={value} value={value}>{marketMode==="stocks"?value:`${value}/USDT`}</option>)}</select></label><b> · {venue}</b><details className="tv-pane-studies"><summary aria-label={`第${variant+1}窗样式设置`}>样式</summary><section><label>图表<select aria-label={`第${variant+1}窗图表类型`} value={chartType} onChange={event=>onAppearanceChange?.({chartType:event.target.value,background})}>{CHART_TYPES.map(type=><option key={type}>{type}</option>)}</select></label><label>背景<input aria-label={`第${variant+1}窗背景颜色`} type="color" value={background} onChange={event=>onAppearanceChange?.({chartType,background:event.target.value})}/></label></section></details><MarketCsvControl index={variant} identity={csvIdentity} label={`${symbol} · ${period} · ${marketMode==="stocks"?"USD":"USDT"}`} active={replayActive} loaded={csvLoaded} onApply={onCsvApply} onClear={onCsvClear}/><ChartDrawingManager symbol={symbol} venue={venue} marketMode={marketMode} drawings={drawings} locked={drawingLocked} onUpdate={onUpdateDrawing} onDelete={onDeleteDrawing}/><details className="tv-pane-studies"><summary aria-label={`第${variant+1}个K线窗口指标`}>指标 {studies.filter(value=>["MA","EMA","BOLL","VWAP","Volume","RSI","MACD","KDJ"].includes(value)).length}</summary><section>{["MA","EMA","BOLL","VWAP","Volume","RSI","MACD","KDJ","价格线","网格线","倒计时","隐藏主图"].map(name=><label key={name}><input type="checkbox" aria-label={`第${variant+1}窗 ${name}`} checked={studies.includes(name)} disabled={!volumeAvailable&&["VWAP","Volume"].includes(name)} title={!volumeAvailable&&["VWAP","Volume"].includes(name)?"文件未提供成交量，无法计算该指标":undefined} onChange={()=>onStudiesChange?.(studies.includes(name)?studies.filter(value=>value!==name):[...studies,name])}/>{name}</label>)}{!volumeAvailable&&<p>文件未提供成交量，VWAP和成交量图暂停计算。</p>}</section></details><label><select aria-label={`第${variant+1}个K线窗口周期`} value={period} onChange={(event)=>onPeriodChange?.(event.target.value)}>{[...new Set([...periods,period])].map((value)=><option key={value}>{value}</option>)}</select></label><details className="tv-axis-options"><summary aria-label={`第${variant+1}窗坐标轴设置`}>坐标</summary><section><label>价格坐标<select aria-label={`第${variant+1}窗价格坐标模式`} value={axis.mode} onChange={event=>changeAxis({...axis,mode:event.target.value,...(event.target.value==="percentage"?{autoScale:true}:{})})}><option value="linear">线性</option><option value="logarithmic">对数</option><option value="percentage">百分比</option></select></label><label><input type="checkbox" aria-label={`第${variant+1}窗翻转坐标`} checked={axis.inverted} onChange={event=>changeAxis({...axis,inverted:event.target.checked})}/>翻转坐标</label><label><input type="checkbox" aria-label={`第${variant+1}窗自动价格范围`} checked={axis.autoScale} disabled={axis.mode==="percentage"} onChange={event=>changeAxis({...axis,autoScale:event.target.checked})}/>自动价格范围</label><ChartPriceRangeControl index={variant} disabled={axis.mode==="percentage"} readRange={()=>chartApi.current?.priceScale("right").getVisibleRange()} onApply={range=>{const priceScale=chartApi.current?.priceScale("right");if(!priceScale)return;priceScale.applyOptions({autoScale:false});try{applyExactPriceRange(priceScale,range);}catch(error){onAxisChange?.({...axis,autoScale:true});throw error;}setRangeRestoreError("");rememberViewport.current?.();changeAxis({...axis,autoScale:false});redraw();}}/>{axis.mode==="percentage"&&<p>可见区间首值为0%，拖动时间范围会改变基准。</p>}</section></details><button aria-label={`第${variant+1}窗放大`} onClick={()=>{const scale=chartApi.current?.timeScale();const next=zoomLogicalRange(scale?.getVisibleLogicalRange(),.7);if(next)scale.setVisibleLogicalRange(next);}}>＋</button><button aria-label={`第${variant+1}窗缩小`} onClick={()=>{const scale=chartApi.current?.timeScale();const next=zoomLogicalRange(scale?.getVisibleLogicalRange(),1.4);if(next)scale.setVisibleLogicalRange(next);}}>−</button><button aria-label={`导出第${variant+1}窗K线CSV`} disabled={waitingForMarket||!candles.length} onClick={()=>{try{downloadChartData({candles,volumeAvailable,symbol,venue,period,source:chartType==="平均K线"?`${dataSource} · 平均K线合成OHLC`:dataSource,kind:dataKind==="csv"?"local_csv":demoData?"demo":"backend",replay:replayMode});setExportState(`CSV已生成 · ${candles.length}根`);}catch(error){setExportState(error.message);}}}>数据</button><button aria-label={`导出第${variant+1}窗PNG`} disabled={waitingForMarket||exportState==="导出中"} onClick={downloadChart}>PNG</button>{exportState&&<small role="status">{exportState}</small>}<button aria-label={`第${variant+1}窗显示全部`} onClick={()=>chartApi.current?.timeScale().fitContent()}>全</button><span>{dataKind==="csv"?"本地CSV":!demoData ? "行情快照" : dataStatus === "loading" ? "正在读取对应标的和周期行情" : "演示数据"} · {chartType} · {marketMode==="stocks"?"美东交易时段":"7×24小时"} · {replayMode?"复盘未来K线已截断":studies.includes("倒计时")?<CandleCountdown period={period}/>:"周期快照"}</span>{!demoData&&["买卖信号","筹码分布"].filter(name=>studies.includes(name)).map(name=><small key={name}>{name}未接入真实统计</small>)}</header><div ref={container} style={waitingForMarket?{visibility:"hidden"}:undefined} className="tv-chart-canvas" aria-label={`第${variant+1}窗价格图`} tabIndex={0} onPointerLeave={()=>{setHoverTime(null);setCursorPrice(null);sync?.crosshair(variant,null);}} onKeyDown={event=>{
    if(!event.altKey||["INPUT","TEXTAREA","SELECT"].includes(event.target.tagName))return;
    if(event.code==="KeyI"){event.preventDefault();changeAxis({...axis,inverted:!axis.inverted});}
    if(event.code==="KeyL"&&axis.mode!=="percentage"){event.preventDefault();changeAxis({...axis,autoScale:!axis.autoScale});}
  }} onPointerMove={event=>{if(event.buttons===1)redraw();}} onPointerUp={()=>{redraw();rememberViewport.current?.();}} onContextMenu={event=>{
    event.preventDefault();event.stopPropagation();
    const chart=chartApi.current,series=priceSeriesApi.current;if(!chart||!series)return;
    const rect=event.currentTarget.getBoundingClientRect(),grid=event.currentTarget.closest(".tv-chart-grid").getBoundingClientRect();
    const hit=chartContextAt({x:event.clientX-rect.left,y:event.clientY-rect.top,width:chart.timeScale().width(),height:chart.panes()[0]?.getHeight()||0,symbol,marketMode,decimals:quote.decimals,demo:demoData},y=>series.coordinateToPrice(y));
    if(hit)onOpenContext?.({...hit,x:event.clientX-grid.left,y:event.clientY-grid.top});
  }}>{studies.includes("隐藏主图")&&<div className="tv-ohlcv-readout">主图已隐藏 · 指标和画线保留</div>}{readout&&!studies.includes("隐藏主图")&&<div className="tv-ohlcv-readout" style={{color:chartReadoutRising(candles,candles.indexOf(readout),chartType)?upColor:downColor}} aria-label={`第${variant+1}窗K线读数`} data-readout-time={readout.time}>{chartType==="平均K线"&&<b>合成OHLC · 非成交价</b>}{chartType==="K线图(HLC)"&&<b>原始OHLC · 实体以前收绘制</b>}<time>{new Date(readout.time*1000).toISOString().slice(0,19).replace("T"," ")} UTC</time><span>开 {formatReadout(readout.open)}</span><span>高 {formatReadout(readout.high)}</span><span>低 {formatReadout(readout.low)}</span><span>收 {formatReadout(readout.close)}</span><span>量 {volumeAvailable?readout.volume.toLocaleString("en-US",{maximumFractionDigits:6}):"未提供"}</span><span>涨跌 {changeMetrics?`${changeMetrics.percent>=0?"+":""}${changeMetrics.percent.toFixed(2)}% (${changeMetrics.change>=0?"+":""}${formatReadout(changeMetrics.change)})`:"—"}</span><span>振幅 {changeMetrics?`${changeMetrics.amplitude.toFixed(2)}%`:"—"}</span>{cursorDifference&&<span style={{color:cursorDifference.change>=0?upColor:downColor}}>光标 {formatReadout(cursorDifference.price)} · 价差（对末收）{cursorDifference.percent>=0?"+":""}{cursorDifference.percent.toFixed(2)}% ({cursorDifference.change>=0?"+":""}{formatReadout(cursorDifference.change)})</span>}</div>}{rangeRestoreError&&<div className="tv-anchor-hint" role="alert">{rangeRestoreError}</div>}<ChartDrawingLayer chart={chartApi.current} series={priceSeriesApi.current} candles={candles} symbol={symbol} venue={venue} marketMode={marketMode} drawings={drawings} tool={drawingTool} locked={drawingLocked} magnet={magnetEnabled} onDraw={onDraw} onUpdate={onUpdateDrawing} revision={projectionRevision}/></div>{demoData&&!waitingForMarket&&!replayMode&&!studies.includes("隐藏主图")&&studies.includes("买卖信号")&&<div className="tv-signal-layer"><i className="buy">B</i><i className="sell">S</i><i className="buy">B</i></div>}{["RSI","MACD","KDJ","资金费率","持仓量(OI)"].some((name)=>studies.includes(name))&&<div className="tv-study-readout">{["RSI","MACD","KDJ","资金费率","持仓量(OI)"].filter((name)=>studies.includes(name)).map((name)=><span key={name}><b>{name}</b>{indicatorValue(name)}</span>)}</div>}{demoData&&!waitingForMarket&&!replayMode&&!studies.includes("隐藏主图")&&studies.includes("筹码分布")&&<div className="tv-chip-profile">{Array.from({length:16},(_,index)=><i key={index} style={{width:`${30+((index*17)%65)}%`}}/> )}</div>}</div>;
}

function MarketChartPane(props) {
  const { sharedPeriod, sharedSymbol, period, externalCandles, symbol, venue, marketMode } = props;
  const shared = period === sharedPeriod && symbol === sharedSymbol;
  const local=props.localData?.key===props.csvIdentity?props.localData:null;
  const feedKey = `${marketMode}:${symbol}:${venue}:${period}`;
  const [feed, setFeed] = useState({ candles: [], status: "loading" });
  useEffect(() => {
    if (shared||local) return;
    setFeed({ candles: [], status: "loading" });
    return observeCandleFeed(
      symbol, periodDefinition(period).timeframe, { publicMarket: true, venue, quoteCurrency:marketMode==="stocks"?"USD":"USDT" },
      result => setFeed({...result, key: feedKey})
    );
  }, [shared, symbol, venue, period, marketMode,local]);
  if(local)return <TradingChartSurface {...props} externalCandles={local.candles} quote={{...props.quote,price:local.candles.at(-1).close}} dataSource={local.source} dataStatus="local" dataKind="csv" dataIsDemo={false} volumeAvailable={local.volumeAvailable}/>;
  return <TradingChartSurface {...props} dataKind={shared?props.dataKind:"backend"} volumeAvailable={shared?props.volumeAvailable:true} externalCandles={shared ? externalCandles : feed.key === feedKey ? feed.candles : []} quote={!shared && feed.key === feedKey && feed.candles.length ? {...props.quote, price:feed.candles.at(-1).close} : props.quote} dataStatus={shared ? props.dataStatus : feed.key === feedKey ? feed.status : "loading"} dataSource={shared?props.dataSource:feed.key===feedKey?feed.source:"连接后端…"} dataIsDemo={shared?props.dataIsDemo:!feed.candles.length}/>;
}

function DrawingOverlay({ drawings, drawingTool, drawingLocked, magnetEnabled, onDraw, onUpdateDrawing, onDeleteDrawing, trackedTraders, openOverlay, }) {
  return <div className={`tv-drawing-overlay legacy-drawings`} aria-label="TradingView K线绘图区" onClick={(event)=>{const rect=event.currentTarget.getBoundingClientRect();onDraw({x:((event.clientX-rect.left)/rect.width)*100,y:((event.clientY-rect.top)/rect.height)*100})}}>
    <svg viewBox="0 0 100 100" preserveAspectRatio="none">{drawings.filter(drawing=>drawing.schema!==2).map(renderDrawing)}</svg>
    {trackedTraders.map((trader,index)=><button className={`tv-trader-marker ${trader.side==="卖出"?"sell":"buy"}`} style={{left:`${20+(index*27)%65}%`,top:`${18+(index*19)%58}%`}} key={`${trader.market}-${trader.name}`} onClick={(event)=>{event.stopPropagation();openOverlay("trader",trader.name,{description:`${trader.market} · ${trader.side} ${trader.symbol}/USDT · ${trader.price}`})}}>{trader.side}<small>{trader.name}</small></button>)}
    {drawings.some(drawing=>drawing.schema!==2)&&<span>旧版屏幕标注 · 未转换为行情锚点</span>}
  </div>;
}

export function TradingChartGrid({ paneAppearance=[], onPaneAppearanceChange, paneGeometry, onPaneGeometryChange, layout, symbol, instrument, marketMode, externalCandles = [], period, quote, venue, chartType, studies, onStudiesChange, paneStudies = [], onPaneStudiesChange, paneAxes = [], onPaneAxisChange, viewportStore, onViewportChange, drawings, drawingTool, drawingLocked, magnetEnabled, onDraw, onUpdateDrawing, onDeleteDrawing, trackedTraders = [], openOverlay = () => {}, replayMode = false, replayTime = null, timeRequest, panePeriods = [], paneSymbols = [], symbolOptions = [], getSymbolQuote, onPaneSymbolChange, paneSync = [], paneLocalData = [], onPaneLocalData, replayActive, dataKind, volumeAvailable, dataStatus, dataSource, dataIsDemo, onPanePeriodChange, onCreateAlert, onPrefillOrder, onToggleWatch, onClearDrawings, onStartReplay, onResetChart, resetSignal = 0, redUp = false }) {
  const [context,setContext]=useState(null);
  const changeStudies = (index, next) => {
    if(index===0 || paneSync.includes("指标")) onStudiesChange?.(next);
    else onPaneStudiesChange?.(index,next);
  };
  const syncOptions = useRef(paneSync); syncOptions.current = paneSync;
  const sync = useMemo(() => createChartSync(() => syncOptions.current), []);
  const panes = Number(layout) || (layout === "九窗" ? 9 : layout === "六窗" ? 6 : layout === "四窗" ? 4 : layout === "双窗" ? 2 : 1);
  const contextAction=(action)=>{action();setContext(null)};
  const columns = panes <= 1 ? 1 : panes <= 4 ? 2 : panes <= 9 ? 3 : panes <= 16 ? 4 : 6;
  return <div className={`tv-chart-grid panes-${panes} ${panes > 4 ? "dense-panes" : ""} ${redUp?"red-up":"green-up"}`} style={{gridTemplateColumns:gridTemplate(panes,paneGeometry),gridTemplateRows:gridRows(panes,paneGeometry)}}>
    <ChartGridDividers count={panes} geometry={paneGeometry} onChange={onPaneGeometryChange}/>
    {Array.from({length:panes},(_,index)=>{
      const paneSymbol = index === 0 || paneSync.includes("交易对") ? symbol : paneSymbols[index] || symbol;
      const panePeriod=index===0||paneSync.includes("周期")?period:panePeriods[index]||"15分";
      const csvIdentity=`${marketMode}:${paneSymbol}:${venue}:${panePeriod}`;
      const paneQuote = paneSymbol === symbol ? quote : getSymbolQuote?.(paneSymbol) || { price:0, change:"0%", decimals:2 };
      return <MarketChartPane localData={paneLocalData[index]} csvIdentity={csvIdentity} csvLoaded={paneLocalData[index]?.key===csvIdentity} onCsvApply={value=>onPaneLocalData?.(index,value)} onCsvClear={()=>onPaneLocalData?.(index,null)} replayActive={replayActive} dataKind={dataKind} volumeAvailable={volumeAvailable} timeRequest={timeRequest} axis={paneAxes[index]||DEFAULT_CHART_AXIS} onAxisChange={next=>onPaneAxisChange?.(index,next)} onUpdateDrawing={onUpdateDrawing} onDeleteDrawing={onDeleteDrawing} drawings={drawings} drawingTool={drawingTool} drawingLocked={drawingLocked} magnetEnabled={magnetEnabled} onDraw={onDraw} onOpenContext={setContext} onViewportChange={onViewportChange} viewportStore={viewportStore} sync={sync} sharedPeriod={period} sharedSymbol={symbol} dataStatus={dataStatus} dataSource={dataSource} dataIsDemo={dataIsDemo} key={`${index}-${resetSignal}`} symbol={paneSymbol} instrument={paneSymbol===symbol?instrument:undefined} symbolOptions={symbolOptions} onSymbolChange={value=>onPaneSymbolChange?.(index,value)} marketMode={marketMode} externalCandles={externalCandles} period={index===0 || paneSync.includes("周期")?period:panePeriods[index] || "15分"} quote={paneQuote} venue={venue} background={paneAppearance[index]?.background||"#ffffff"} onAppearanceChange={next=>onPaneAppearanceChange?.(index,next)} chartType={index===0||paneSync.includes("其他")?chartType:paneAppearance[index]?.chartType||chartType} studies={index===0 || paneSync.includes("指标") ? studies : paneStudies[index] || studies} onStudiesChange={next=>changeStudies(index,next)} variant={index} replayMode={replayMode} replayTime={replayTime} redUp={redUp} onPeriodChange={(value)=>onPanePeriodChange?.(index,value)}/>;
    })}

    <div className="tv-advanced-markers" hidden={replayMode||!dataIsDemo||dataStatus==="loading"}>{(studies.includes("大额成交")||studies.includes("主力大单"))&&<><button className="large buy" onClick={()=>openOverlay("flash","大额买入详情",{description:`${symbol}/USDT · $2.18M 主动买入`})}>大额买入 $2.18M</button><button className="large sell" onClick={()=>openOverlay("flash","大额卖出详情",{description:`${symbol}/USDT · $0.86M 主动卖出`})}>大额卖出 $0.86M</button></>}{studies.includes("主力挂单统计")&&<span className="main-order">主力挂买 +$12.4M</span>}{studies.includes("指标胜率")&&<span className="winrate">当前信号胜率 68.4%</span>}</div>
    <DrawingOverlay drawings={drawings} drawingTool={drawingTool} drawingLocked={drawingLocked} magnetEnabled={magnetEnabled} onDraw={onDraw} trackedTraders={replayMode?[]:trackedTraders} openOverlay={openOverlay}/>
    {context&&<aside className="tv-context-menu" style={{left:Math.min(context.x,520),top:Math.min(context.y,260)}} onClick={(event)=>event.stopPropagation()}><header><span>{context.instrument}{context.demo?" · 演示":""}</span><b>{context.price.toFixed(context.decimals)}</b></header><button onClick={()=>contextAction(()=>onCreateAlert?.(context.price,context.symbol))}><I.BellRinging/>在此价格添加预警</button><button onClick={()=>contextAction(()=>onPrefillOrder?.(context.price,"买入",context.symbol))}><I.ArrowCircleDown/>限价买入</button><button onClick={()=>contextAction(()=>onPrefillOrder?.(context.price,"卖出",context.symbol))}><I.ArrowCircleUp/>限价卖出</button><button onClick={()=>contextAction(()=>onToggleWatch?.(context.symbol))}><I.Star/>切换自选</button><button onClick={()=>contextAction(()=>onStartReplay?.())}><I.Play/>打开K线复盘</button><button onClick={()=>contextAction(()=>onResetChart?.())}><I.ArrowCounterClockwise/>重置全部图表视图</button><button disabled={drawingLocked||!drawings.some(item=>!item.locked)} onClick={()=>contextAction(()=>onClearDrawings?.())}><I.Trash/>清除未锁定绘图</button><button className="close" onClick={()=>setContext(null)}><I.X/>关闭菜单</button></aside>}
  </div>;
}
