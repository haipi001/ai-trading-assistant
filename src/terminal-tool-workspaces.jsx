import {observePublicDepth} from './live-market-depth.js';
import {observePublicTrades} from './live-market-trades.js';
import {observeCandleFeed} from './live-market-candles.js';
import {useNewsFeed} from './news-feed-workspace.jsx';
import React,{useState,useEffect,useMemo} from 'react';
import * as I from '@phosphor-icons/react';
import {AceAgentDock} from './ace-status.jsx';
import {useStrategyDrafts} from './use-strategy-drafts.jsx';
import {getTerminalTradingContext} from './terminal-trading-policy.js';
import './terminal-tool-workspaces.css';
import {analyzeSource,analysisQuestion} from './source-ai-analysis.js';
import {buildLinkIndex,noteConnections,journalStats,openPositions,journalGaps,noteAnalysisPrompt,noteKind} from './trade-journal.js';
const sources=[['depth','订单与成交'],['news','最新资讯'],['funds','资金流向'],['analysis','技术分析'],['feature','特色数据'],['etf','ETF 数据']];
function prepare(question){const detail={includeMarket:false,question};window.dispatchEvent(new CustomEvent('ai-trading-assistant-research-intent',{detail}));return detail.accepted;}
function SourceMaterialPreview({material}){
 const rows=material.asks?[[...material.asks].map(row=>['卖盘',row.price,row.quantity]),[...material.bids].map(row=>['买盘',row.price,row.quantity])].flat():material.recent_public_trades?material.recent_public_trades.map(row=>[row.side,row.price,row.quantity]):null;
 return <section className="source-material-preview"><p>{material.source}</p><small>获取：{material.captured_at||'来源未提供'}{material.stale?' · 已陈旧':''}</small>{rows&&<table><thead><tr><th>类型</th><th>价格</th><th>数量</th></tr></thead><tbody>{rows.map((row,index)=><tr key={index}>{row.map((cell,i)=><td key={i}>{String(cell??'未提供')}</td>)}</tr>)}</tbody></table>}{material.candles&&<table><thead><tr>{['开','高','低','收','量'].map(label=><th key={label}>{label}</th>)}</tr></thead><tbody>{material.candles.map((row,index)=><tr key={index}>{['open','high','low','close','volume'].map(field=><td key={field}>{String(row[field]??'未提供')}</td>)}</tr>)}</tbody></table>}{material.articles?.map((row,index)=><article key={index}><b>{row.title}</b><small>{row.publishedAt||'发布时间未提供'}</small><p>{row.description}</p><a href={row.url} target="_blank" rel="noopener noreferrer">查看原文</a></article>)}{material.limitations&&<p>{material.limitations}</p>}<details><summary>核对原始资料</summary><pre style={{whiteSpace:'pre-wrap',maxHeight:240,overflow:'auto'}}>{JSON.stringify(material,null,2)}</pre></details></section>;
}
function AnalysisReadout({analysis,label}){
 if(!analysis.ready)return <section className="source-analysis is-empty" aria-label={`${label}资料状态`}><p role="status">{analysis.summary}</p>{analysis.risks.length>0&&<ul className="source-risk-list">{analysis.risks.map((row,index)=><li key={index}>{row}</li>)}</ul>}{analysis.gaps.length>0&&<ul className="source-gap-list">{analysis.gaps.map((row,index)=><li key={index}>{row}</li>)}</ul>}</section>;
 return <section className="source-analysis" aria-label={`${label}本地计算摘要`}>
  <p className="source-analysis-summary">{analysis.summary}</p>
  {analysis.metrics.length>0&&<dl className="source-metric-grid">{analysis.metrics.map(row=><div key={row.label}><dt>{row.label}</dt><dd>{row.value}{row.hint&&<small>{row.hint}</small>}</dd></div>)}</dl>}
  {analysis.findings.length>0&&<div className="source-block"><h4>本地计算</h4><ul>{analysis.findings.map((row,index)=><li key={index}>{row}</li>)}</ul></div>}
  {analysis.risks.length>0&&<div className="source-block is-risk"><h4>已识别风险</h4><ul>{analysis.risks.map((row,index)=><li key={index}>{row}</li>)}</ul></div>}
  {analysis.gaps.length>0&&<div className="source-block is-gap"><h4>资料缺口</h4><ul>{analysis.gaps.map((row,index)=><li key={index}>{row}</li>)}</ul></div>}
  {analysis.basis&&<small className="source-basis">{analysis.basis}；数字由本地规则计算，不是模型输出，也不代表独立核验。</small>}
 </section>;
}
export function SourceAIWorkspace({renderSource}){
 const context=getTerminalTradingContext(),news=useNewsFeed();
 const [feed,setFeed]=useState(null),[profile,setProfile]=useState(null);
 const [selected,setSelected]=useState('depth'),[notice,setNotice]=useState('');const label=sources.find(([id])=>id===selected)[1];
 const feedKey=JSON.stringify([selected,context?.market,context?.instrumentId,context?.venue,context?.timeframe,context?.contextVersion]);
 useEffect(()=>{
  setFeed(null);setProfile(null);const symbol=context?.instrumentId?.split('/')[0],quote=context?.instrumentId?.split('/')[1],venue=context?.venue==='欧易'?'欧易OKX':context?.venue;
  if(context?.market!=='cex'||quote!=='USDT'||!symbol)return;
  const receive=value=>setFeed({...value,key:feedKey,captured_at:new Date().toISOString()});
  if(selected==='depth')return observePublicDepth(symbol,venue,receive);
  if(selected==='funds')return observePublicTrades(symbol,venue,receive);
  if(selected==='analysis')return observeCandleFeed(symbol,String(context.timeframe||'1D').toLowerCase(),{publicMarket:true,venue,quoteCurrency:quote},receive);
  if(selected==='feature'){
   // 特色数据 combines both microstructure and price history; each keeps its own status.
   const stops=[];
   const collect=(kind)=>value=>setProfile(previous=>{const next={...(previous&&previous.key===feedKey?previous:{key:feedKey}),[kind]:value,captured_at:new Date().toISOString()};return next;});
   stops.push(observePublicTrades(symbol,venue,collect('trades')));
   stops.push(observeCandleFeed(symbol,String(context.timeframe||'1D').toLowerCase(),{publicMarket:true,venue,quoteCurrency:quote},collect('candles')));
   return()=>{for(const stop of stops)if(typeof stop==='function')stop();};
  }
 },[feedKey]);
 const active=feed?.key===feedKey?feed:null;
 const liveProfile=profile?.key===feedKey?profile:null;
 const material=selected==='news'&&news.data?.articles?.length?{source:news.data.provider,captured_at:news.data.fetchedAt,stale:news.stale,articles:news.data.articles.slice(0,20).map(row=>({title:row.title,url:row.url,publishedAt:row.publishedAt,publisher:row.publisher,description:row.description?.slice(0,180)}))}:selected==='feature'?(liveProfile?.trades?.status==='connected'||liveProfile?.candles?.status==='connected'?{source:[liveProfile?.trades?.source,liveProfile?.candles?.source].filter(Boolean).join(' · '),captured_at:liveProfile.captured_at,instrument:context.instrumentId,venue:context.venue,trades:liveProfile?.trades?.status==='connected'?liveProfile.trades.trades:undefined,candles:liveProfile?.candles?.status==='connected'?liveProfile.candles.candles:undefined}:null):active?.status==='connected'?{source:active.source,captured_at:active.captured_at,instrument:context.instrumentId,venue:context.venue,...(selected==='depth'?{asks:active.asks?.slice(0,20),bids:active.bids?.slice(0,20)}:selected==='funds'?{recent_public_trades:active.trades?.slice(0,20)}:{candles:active.candles})}:null;
 const analysis=analyzeSource(selected,material);
 function analyze(){const question=analysis.ready?analysisQuestion(analysis,label,material):`请列出“${label}”所需数据与核验步骤。当前没有该来源的已验证资料：${analysis.gaps.join('；')}。不得推测数字或给出确定性资产结论。`;
  setNotice(question.length>4000?'材料超过输入上限，未截断或发送。':prepare(question)?'已准备此来源的研究问题，请在AI对话核对材料后手动发送。':'AI对话未接收，请重试。');
 }
 const statusText=material?'已读取资料，发送前请核对来源与时间':selected==='etf'?'ETF 来源尚未接入':liveProfile?.trades?.source||liveProfile?.candles?.source||active?.source||news.error||'当前范围暂无已校验来源；不会用示例补齐';
 return <section className="tool-workspace source-ai-workspace"><header><small>ACE · 六源研究</small><h2 data-terminal-label>市场 AI 分析</h2><p>分别查看六类资料。每一项先给出本地计算结果，再决定是否交给模型；切换来源保留其独立范围，不把缺失资料拼成完整结论。</p></header><nav aria-label="AI分析资料来源">{sources.map(([id,name])=><button key={id} aria-pressed={id===selected} onClick={()=>{setSelected(id);setNotice('');}}>{name}</button>)}</nav><section><h3 data-terminal-label>{label}</h3><p className="source-status-line">{statusText}</p><AnalysisReadout analysis={analysis} label={label}/><div className="source-actions"><button onClick={analyze} disabled={!analysis.ready&&selected!=='etf'}>准备此来源 AI 分析</button>{material&&<small>本地计算不调用模型，不产生费用。</small>}</div>{notice&&<p role="status">{notice}</p>}<section className="tool-source-content">{material&&<details className="source-raw"><summary>查看原始资料（{label}）</summary><SourceMaterialPreview material={material}/></details>}<details><summary>原版界面样例（非当前实时证据）</summary>{renderSource(selected)}</details></section></section></section>;
}
export function AIActivityCenter({onReviewOrder,go}){
 const context=getTerminalTradingContext(),embedded=Boolean(context);
 const [strategies]=useStrategyDrafts(embedded,context),[notes]=useStrategyDrafts(embedded,context,'ai-trading-assistant-strategy-notes');
 const [grid]=useStrategyDrafts(embedded,context,'ai-trading-assistant-grid-strategies'),[dca]=useStrategyDrafts(embedded,context,'ai-trading-assistant-spot-dca-strategies'),[futures]=useStrategyDrafts(embedded,context,'ai-trading-assistant-futures-dca-strategies'),[indicators]=useStrategyDrafts(embedded,context,'ai-trading-assistant-indicator-live-strategies'),[copy]=useStrategyDrafts(embedded,context,'ai-trading-assistant-copy-subscriptions'),[dex]=useStrategyDrafts(embedded,context,'ai-trading-assistant-dex-copy-subscriptions');
 const [tab,setTab]=useState('journal'),[notice,setNotice]=useState('');const records=[...strategies,...grid,...dca,...futures,...indicators,...copy,...dex];
 const index=useMemo(()=>buildLinkIndex(notes),[notes]);
 const stats=useMemo(()=>journalStats(notes),[notes]);
 const gaps=useMemo(()=>journalGaps(notes),[notes]);
 const positions=useMemo(()=>openPositions(notes),[notes]);
 const linked=useMemo(()=>notes.map(row=>({row,connections:noteConnections(index,row.id)})).filter(item=>item.connections.outgoing.length+item.connections.incoming.length>0),[index,notes]);
 const analyzeNote=(note,kind)=>{const question=noteAnalysisPrompt(note,index);const detail={includeMarket:false,question:question.slice(0,4000)};window.dispatchEvent(new CustomEvent('ai-trading-assistant-research-intent',{detail}));setNotice(detail.accepted?`已准备「${note.title}」的${kind}，请在对话中核对后手动发送。`:'AI面板未接收。');};
 return <section className="tool-workspace ai-activity-center"><header><small>AI · 工作中心</small><h2 data-terminal-label>复盘、任务与策略</h2><p>这里抽取本地记录中可供 AI 审阅的部分：交易统计、资料缺口与链接关系。本地配置不等于正在执行，记录未经独立核验。</p></header>
 <nav>{[['journal','复盘摘要'],['notes','笔记与链接'],['strategies','全部策略'],['tasks','任务与通知']].map(([id,label])=><button key={id} aria-pressed={tab===id} onClick={()=>{setTab(id);setNotice('');}}>{label}</button>)}</nav>
 {tab==='journal'&&<section className="ai-journal-summary">
  <dl className="ai-stat-grid">
   <div><dt>已实现盈亏</dt><dd className={stats.realized>0?'gain':stats.realized<0?'loss':''}>{stats.realized>0?'+':''}{stats.realized.toFixed(2)}</dd></div>
   <div><dt>胜率</dt><dd>{stats.winRate===null?'未计算':`${stats.winRate.toFixed(1)}%`}</dd></div>
   <div><dt>盈亏比</dt><dd>{stats.profitFactor===null?'未计算':stats.profitFactor.toFixed(2)}</dd></div>
   <div><dt>持仓中</dt><dd>{stats.open}</dd></div>
  </dl>
  {positions.length>0&&<section><h3 data-terminal-label>当前持仓敞口</h3>{positions.map(row=><article key={row.symbol}><b>{row.symbol}</b><p>数量 {row.quantity} · 均价 {row.averageEntry===null?'未记录':row.averageEntry.toFixed(4)} · 风险 {row.risked.toFixed(2)}</p></article>)}</section>}
  <section><h3 data-terminal-label>让 AI 先看的缺口</h3>{gaps.length===0?<p>记录字段齐全，可以开始复盘。</p>:<ul className="ai-gap-list">{gaps.map((gap,index)=><li key={index}>{gap}</li>)}</ul>}<button onClick={()=>{const question=[`请审阅我的交易复盘摘要，指出统计口径的局限与下一步应补齐的记录。`,`当前已实现盈亏 ${stats.realized.toFixed(2)}，${stats.decided} 笔已判定，胜率 ${stats.winRate===null?'未计算':stats.winRate.toFixed(1)+'%'}，盈亏比 ${stats.profitFactor===null?'未计算':stats.profitFactor.toFixed(2)}。`,`持仓 ${stats.open} 笔，未实现盈亏未计入。`,`已知缺口：${gaps.join(' ')}`,`要求：区分事实与推断，不虚构行情，不给出确定性买卖建议，不声称已核验。`].join('\n');const detail={includeMarket:false,question:question.slice(0,4000)};window.dispatchEvent(new CustomEvent('ai-trading-assistant-research-intent',{detail}));setNotice(detail.accepted?'已准备复盘摘要分析，请在对话中核对后手动发送。':'AI面板未接收。');}}><I.Sparkle/>AI 分析我的复盘</button></section>
  {notice&&<p role="status">{notice}</p>}
 </section>}
 {tab==='notes'&&<section className="ai-note-index">
  <h3 data-terminal-label>{notes.length} 条记录 · {index.edgeCount} 条双向链接 · {index.orphans.length} 条孤立</h3>
  {notes.slice(0,12).map((note,index2)=>{const connections=noteConnections(index,note.id);return <article key={note.id||index2}><b>{noteKind(note)==='trade'&&<i className="kind-badge">记录</i>}{note.title||'未命名'}</b>
   <p>{String(note.body||'').replace(/\[\[|\]\]/g,'').slice(0,160)||'正文为空'}</p>
   {(connections.outgoing.length>0||connections.incoming.length>0)&&<small>链接：{[...connections.outgoing.map(r=>`→${r.note.title}`),...connections.incoming.map(r=>`←${r.note.title}`)].join(' · ')}</small>}
   <button onClick={()=>analyzeNote(note,noteKind(note)==='trade'?'交易复盘':'笔记分析')}>准备 AI 分析</button></article>;})}
  {!notes.length&&<p>当前范围没有笔记；不会显示其他账户的记录。</p>}
  {index.broken.length>0&&<section><h3 data-terminal-label>悬空链接</h3>{index.broken.slice(0,5).map((row,i)=><p key={i}><b>{row.noteTitle}</b> → [[{row.title}]] 尚无对应笔记</p>)}</section>}
  {linked.length===0&&notes.length>0&&<p>还没有任何双向链接；在笔记正文里写 [[标题]] 即可建立。</p>}
  <button onClick={()=>go('strategy')}>打开策略工作台</button>
  {notice&&<p role="status">{notice}</p>}
 </section>}
 {tab==='strategies'&&<section><h3 data-terminal-label>{records.length} 份本地策略配置</h3>{records.map((row,index2)=><article key={String(row.id||index2)+index2}><b>{row.name||row.kind||'未命名配置'}</b><p>{row.symbol||row.coin||'未记录标的'} · {row.status||'状态未记录'}（本地记录，未证实运行）</p></article>)}<button onClick={()=>go('strategy')}>打开策略工作台</button></section>}
 {tab==='tasks'&&<AceAgentDock initialView="Tasks" onReviewOrder={onReviewOrder}/>}
 </section>;
}
export function LiveOrderTicket({openConnections}){
 const c=getTerminalTradingContext();const [form,setForm]=useState({side:'buy',type:'limit',quantity:'',price:''}),[review,setReview]=useState('');
 return <section className="live-ticket"><header><small>LIVE · 实盘票据</small><h2 data-terminal-label>真实账户下单</h2><span>执行通道未开放</span></header><p>账户：{c?.accountId||'未选择'} · 标的：{c?.instrumentId||'未选择'} · 场所：{c?.venue||'未选择'}</p><label>方向<select value={form.side} onChange={e=>{setForm({...form,side:e.target.value});setReview('');}}><option value="buy">买入</option><option value="sell">卖出</option></select></label><label>订单类型<select value={form.type} onChange={e=>{setForm({...form,type:e.target.value});setReview('');}}><option value="limit">限价</option><option value="market">市价</option></select></label>{form.type==='limit'&&<label>委托价格<input inputMode="decimal" value={form.price} onChange={e=>{setForm({...form,price:e.target.value});setReview('');}}/></label>}<label>数量<input inputMode="decimal" value={form.quantity} onChange={e=>{setForm({...form,quantity:e.target.value});setReview('');}}/></label><p>可用余额、最小委托、价格精度及手续费：未取得可交易账户回执，不使用演示报价补齐。</p><button onClick={()=>setReview(!c?.instrumentId||!c?.accountId?'请先选择标的与账户。':!Number.isFinite(Number(form.quantity))||Number(form.quantity)<=0||form.type==='limit'&&(!Number.isFinite(Number(form.price))||Number(form.price)<=0)?'请填写有效的正数价格与数量。':'票据输入有效；实盘权限、风控、人工审批和执行通道尚未完成，未发送任何订单。')}>检查票据</button><button disabled>提交真实订单（未开放）</button>{review&&<p role="status">{review}</p>}<button onClick={openConnections}>连接设置与权限</button><p>只读连接不授予交易权限；真实交易不由AI自动执行。</p></section>;
}
