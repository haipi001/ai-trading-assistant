import React,{useState} from 'react';
import * as I from '@phosphor-icons/react';
import {SAMPLE_DISCLOSURE,samplesFor,copySample,curvePath,SAMPLE_BACKTESTS,SAMPLE_BASKETS} from './strategy-samples.js';
import './strategy-samples.css';

function Sparkline({equity}){
 const shape=curvePath(equity);
 if(!shape)return null;
 return <svg className={`sample-spark ${shape.positive?'is-up':'is-down'}`} viewBox="0 0 100 28" preserveAspectRatio="none" aria-hidden="true"><polyline points={shape.points}/></svg>;
}

export function SampleBadge(){return <em className="sample-badge" title={SAMPLE_DISCLOSURE}>模拟案例</em>;}

// A gallery of hand-written cases. Copying one turns it into an ordinary local
// record, so the example still disappears from the gallery afterwards.
export function SampleGallery({kind,existing=[],onCopy,say}){
 const [open,setOpen]=useState(true);
 const items=samplesFor(kind,existing);
 if(!items.length)return null;
 return <section className="sample-gallery">
  <header><button type="button" className="sample-gallery-toggle" aria-expanded={open} onClick={()=>setOpen(!open)}><I.CaretDown className={open?'':'closed'}/><b>模拟案例</b><span>{items.length} 个</span></button><small>{SAMPLE_DISCLOSURE}</small></header>
  {open&&<div className="sample-gallery-grid">{items.map(item=><article className={`sample-card ${item.equity&&curvePath(item.equity)?.positive?'is-up':'is-down'}`} key={item.id}>
   <header><span><b>{item.name}</b><small>{item.symbol} · {item.mode}</small></span><SampleBadge/></header>
   <p className="sample-detail">{item.detail}</p>
   <Sparkline equity={item.equity}/>
   <dl className="sample-metrics">
    <div><dt>累计收益</dt><dd className={String(item.pnl).startsWith('-')?'red':'green'}>{item.pnl} {item.currency}</dd></div>
    <div><dt>最大回撤</dt><dd>{item.drawdown}</dd></div>
    <div><dt>{item.winRate==='—'?'定投期数':'胜率'}</dt><dd>{item.winRate==='—'?item.pairs:item.winRate}</dd></div>
    <div><dt>成交笔数</dt><dd>{item.orders}</dd></div>
   </dl>
   <footer><span>{item.createdAt}</span><button type="button" onClick={()=>{if(!onCopy)return;onCopy(copySample(item));say?.(`已复制「${item.name}」为本地配置，参数可继续修改`);}}>复制为我的配置</button></footer>
  </article>)}</div>}
 </section>;
}

export function SampleBacktestGallery({onApply,say}){
 const [selected,setSelected]=useState(null);
 return <section className="sample-gallery">
  <header><span><b>模拟回测案例</b><span>{SAMPLE_BACKTESTS.length} 个</span></span><small>{SAMPLE_DISCLOSURE}其中一个刻意是亏损案例。</small></header>
  <div className="sample-gallery-grid">{SAMPLE_BACKTESTS.map(item=><article className={`sample-card ${curvePath(item.equity)?.positive?'is-up':'is-down'}`} key={item.id}>
   <header><span><b>{item.name}</b><small>{item.symbol} · {item.period} · {item.range}</small></span><SampleBadge/></header>
   <Sparkline equity={item.equity}/>
   <dl className="sample-metrics">
    <div><dt>策略收益</dt><dd className={item.return.startsWith('-')?'red':'green'}>{item.return}</dd></div>
    <div><dt>基准收益</dt><dd>{item.benchmark}</dd></div>
    <div><dt>最大回撤</dt><dd>{item.drawdown}</dd></div>
    <div><dt>胜率</dt><dd>{item.winRate}</dd></div>
    <div><dt>交易次数</dt><dd>{item.trades}</dd></div>
    <div><dt>盈亏比</dt><dd>{item.ratio}</dd></div>
   </dl>
   <p className="sample-note">{item.note}</p>
   {selected===item.id?<footer><span>参数已填入左侧表单；回测引擎仍未接入，不会运行。</span><button type="button" onClick={()=>setSelected(null)}>收起</button></footer>:<footer><button type="button" onClick={()=>{setSelected(item.id);onApply?.(item);say?.(`已套用「${item.name}」的模拟参数；示例收益不会写入你的记录`);}}>套用参数</button></footer>}
  </article>)}</div>
 </section>;
}

export function SampleBasketGallery({onApply,say}){
 return <section className="sample-gallery">
  <header><span><b>模拟组合案例</b><span>{SAMPLE_BASKETS.length} 个</span></span><small>{SAMPLE_DISCLOSURE}</small></header>
  <div className="sample-gallery-grid">{SAMPLE_BASKETS.map(item=><article className="sample-card" key={item.id}>
   <header><span><b>{item.name}</b><small>{item.rows.length} 笔委托</small></span><SampleBadge/></header>
   <p className="sample-detail">{item.note}</p>
   <table className="sample-basket-table"><thead><tr>{['交易对','方向','类型','价格','数量'].map(name=><th key={name}>{name}</th>)}</tr></thead><tbody>{item.rows.map((row,index)=><tr key={index}><td>{row.pair}</td><td className={row.side==='买入'?'green':'red'}>{row.side}</td><td>{row.type}</td><td>{row.price||'市价'}</td><td>{row.amount}</td></tr>)}</tbody></table>
   <footer><button type="button" onClick={()=>{onApply?.(item.rows.map(row=>({...row,id:Date.now()+Math.random()})));say?.(`已载入「${item.name}」的 ${item.rows.length} 笔委托，提交前请核对价格与数量`);}}>载入到组合下单</button></footer>
  </article>)}</div>
 </section>;
}

// A worked example of what the AI panel produces, so the page does not open on
// an empty placeholder. Clearly marked, and it is analysis of given numbers only.
export function SampleAnalysisReport({symbol,tab}){
 const reports={
  综合解读:{ verdict:'震荡偏强，未突破', points:[
    ['价格结构','近 30 根 K 线在 63,800–66,400 之间来回，未创出新高也未跌破前低，属于区间震荡。'],
    ['量能','上涨段的成交量没有显著高于下跌段，突破缺少量能配合。'],
    ['需要补充','盘口深度与资金流未接入，无法判断区间边缘是否有真实承接。'],
  ]},
  趋势分析:{ verdict:'中期上行，短期回调', points:[
    ['均线','MA5 上穿 MA10，但两者仍在 MA20 附近纠缠，趋势强度一般。'],
    ['回撤','当前回撤幅度约 2.1%，小于样本内单根平均波动的两倍，尚属正常回调。'],
    ['失效条件','若收盘跌破区间下沿 63,800 且放量，本段上行判断失效。'],
  ]},
  主力订单:{ verdict:'资料不足，无法判断', points:[
    ['缺失','主力订单需要逐笔大单与挂单增量数据，当前范围没有接入。'],
    ['不推测','不根据价格形态反推主力意图，那样得出的结论无法核验。'],
    ['建议','接入盘口增量后再评估，或先在「订单与成交」来源中查看真实盘口快照。'],
  ]},
  风险事件:{ verdict:'未见已核验事件', points:[
    ['资讯','资讯来源为缓存快照，未做事件抽取，不能当作风险清单。'],
    ['日历','经济日历尚未接入，无法核对未来 24 小时的宏观事件。'],
    ['建议','把风险事件当作待核验项，不要因为这里显示"无"就认为没有风险。'],
  ]},
 };
 const report=reports[tab]||reports.综合解读;
 return <section className="sample-analysis">
  <header><span><b>{symbol} · {tab}</b><small>示例结构</small></span><SampleBadge/></header>
  <p className="sample-verdict">{report.verdict}</p>
  <ul>{report.points.map(([name,text],index)=><li key={index}><b>{name}</b><span>{text}</span></li>)}</ul>
  <footer>以上是本地示例文本，用来展示回复结构。真实回复依赖已配置的 AI 服务与附带的材料，且不会替你下单。</footer>
 </section>;
}
