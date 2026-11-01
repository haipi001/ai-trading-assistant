import React,{useEffect,useMemo,useState} from 'react';
import * as I from '@phosphor-icons/react';
import {applyReplayTrade,emptyReplayLedger,replayCloseTime,replayProfit,replayStartIndex} from './chart-replay.js';
export function KlineReplayPanel({symbol,period,bars=[],source,marketMode,onCursorChange,onChooseStart,onClose,say,initialSpeed=1,hideFuture=true,startLabel='数据起点'}){
 const [index,setIndex]=useState(()=>Math.min(14,Math.max(0,bars.length-1))),[playing,setPlaying]=useState(false),[speed,setSpeed]=useState(initialSpeed),[ledger,setLedger]=useState(emptyReplayLedger),[summary,setSummary]=useState(false),[mode,setMode]=useState('简洁模式'),[error,setError]=useState('');
 useEffect(()=>{try{setIndex(replayStartIndex(bars,startLabel));setPlaying(false);setLedger(emptyReplayLedger());setError('');}catch(error){setError(error.message);}},[startLabel,bars]);
 useEffect(()=>{setSpeed(initialSpeed);},[initialSpeed]);
 const current=bars[index],finished=index>=bars.length-1;
 useEffect(()=>{if(current)onCursorChange(replayCloseTime(current,period));},[current,period]);
 useEffect(()=>{if(!playing||finished||summary)return;const timer=setInterval(()=>setIndex(value=>Math.min(bars.length-1,value+1)),1000/speed);return()=>clearInterval(timer);},[playing,finished,summary,speed,bars.length]);
 useEffect(()=>{if(finished)setPlaying(false);},[finished]);
 const pnl=useMemo(()=>replayProfit(ledger,current?.close||0),[ledger,current]);
 const progress=bars.length?100*(index+1)/bars.length:0,unit=marketMode==='stocks'?'USD':'USDT';
 const reset=()=>{setIndex(Math.min(14,Math.max(0,bars.length-1)));setPlaying(false);setLedger(emptyReplayLedger());setError('');};
 const trade=side=>{if(!current)return;try{setLedger(applyReplayTrade(ledger,{side,price:current.close,time:current.time}));setError('');say(`复盘${side}0.01 ${symbol} · 本地模拟`);}catch(error){setError(error.message);}};
 return <div className="kline-replay" role="region" aria-label="K线复盘训练"><header><div><I.ClockCounterClockwise/><span><b>K线复盘 · {source}</b><small>{symbol} · {period} · {current?new Date(current.time*1000).toISOString().replace('T',' ').slice(0,19):'无数据'} UTC · {hideFuture?'未来K线已隐藏':'未来K线可见'}</small></span></div><button onClick={()=>{setSummary(true);setPlaying(false);}}>结束训练</button><button aria-label="关闭K线复盘" onClick={onClose}><I.X/></button></header>
 <section className="replay-stats"><span><small>复盘进度</small><b>{index+1}/{bars.length}根 · {progress.toFixed(1)}%</b></span><span><small>模拟持仓</small><b>{ledger.quantity.toFixed(2)} {symbol}</b></span><span><small>已实现 / 浮动盈亏</small><b>{pnl.realized.toFixed(4)} / {pnl.unrealized.toFixed(4)} {unit}</b></span><span><small>当前收盘 / 交易次数</small><b>{current?.close.toFixed(4)||'—'} / {ledger.trades.length}</b></span></section>
 <div className="replay-progress"><i style={{width:`${progress}%`}}/></div>{error&&<p role="alert">{error}</p>}
 <footer><button onClick={onChooseStart}><I.CalendarBlank/>选择起始时间</button><button onClick={reset}><I.ArrowCounterClockwise/>重新选择起点</button><button disabled={!current||finished} onClick={()=>setIndex(value=>Math.min(bars.length-1,value+1))}><I.SkipForward/>单步</button><button className="replay-play" disabled={!current||finished} onClick={()=>setPlaying(!playing)}>{playing?<I.Pause/>:<I.Play/>}{playing?'暂停':'播放'}</button>{[1,2,4].map(value=><button key={value} className={speed===value?'on':''} onClick={()=>setSpeed(value)}>{value}x</button>)}<span/>{['简洁模式','持仓模式'].map(value=><button key={value} className={mode===value?'on':''} onClick={()=>setMode(value)}>{value}</button>)}<button className="replay-buy" disabled={!current} onClick={()=>trade('买入')}>模拟买入</button><button className="replay-sell" disabled={!current||ledger.quantity<.01} onClick={()=>trade('卖出')}>模拟卖出</button></footer>
 {mode==='持仓模式'&&<div className="replay-trade-records">{ledger.trades.length?ledger.trades.map((trade,index)=><p key={index}>{new Date(trade.time*1000).toISOString()} · {trade.side} {trade.quantity} · {trade.price.toFixed(4)} {unit}</p>):<p>暂无模拟交易</p>}</div>}
 <small className="replay-data-note">固定载入快照逐根推进，图外盘口及资讯不参与复盘；无手续费、滑点或成交撮合，不提交实盘委托。选择新起点会清空本次模拟记录。</small>
 {summary&&<div className="replay-summary"><article><header><I.ChartLineUp/><div><b>复盘训练结果</b><small>{symbol} · {period}</small></div></header><strong>{pnl.total.toFixed(4)} {unit}</strong><p><span>已实现盈亏</span><b>{pnl.realized.toFixed(4)}</b></p><p><span>浮动盈亏</span><b>{pnl.unrealized.toFixed(4)}</b></p><p><span>交易次数</span><b>{ledger.trades.length}</b></p><footer><button onClick={()=>setSummary(false)}>继续复盘</button><button onClick={onClose}>结束并退出</button></footer><small>仅为当前快照的本地模拟，未运行交易策略。</small></article></div>}
 </div>;
}
