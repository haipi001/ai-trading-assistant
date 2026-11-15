import {useStrategyDrafts} from './use-strategy-drafts.jsx';
import {getTerminalTradingContext} from './terminal-trading-policy.js';
import React, { useMemo, useRef, useState } from "react";
import * as I from "@phosphor-icons/react";
import {apiRequest} from './backend-api.js';
import {paperTradeHistory} from './paper-trade-history.js';
import {buildLinkIndex,noteConnections,linkSuggestions,noteTags,tradeMetrics,journalStats,openPositions,journalGaps,noteAnalysisPrompt,strategyDraftFromNote,newNote,newTrade,noteKind,TRADE_STATUS,parseWikiLinks} from './trade-journal.js';
import "./strategy-intelligence.css";

function useLocalState(key, seed) {
  const context=getTerminalTradingContext();
  return useStrategyDrafts(Boolean(context),context,key,context?[]:seed);
}

const money = value => (typeof value === 'number' && Number.isFinite(value)
  ? `${value < 0 ? '-' : ''}${Math.abs(value).toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2})}`
  : '未计算');
const pct = value => (typeof value === 'number' && Number.isFinite(value) ? `${value > 0 ? '+' : ''}${value.toFixed(2)}%` : '未计算');
const signed = value => (typeof value === 'number' && Number.isFinite(value) && value > 0 ? `+${money(value)}` : money(value));

const seedNotes = [
  { id: "btc-breakout", kind: "note", title: "BTC 4小时突破观察", body: "价格在 64,200 附近反复测试，成交量收缩。等待放量站稳再介入。\n\n关联：[[主力净流入]] [[风险清单]]\n#BTC #突破", tags: ["BTC", "突破"], links: [], updated: "示例", ai: "" },
  { id: "flow", kind: "note", title: "主力净流入", body: "BTC 大单净流入连续 3 个周期转正，现货买盘强于永续。\n\n关联：[[BTC 4小时突破观察]]", tags: ["BTC", "资金流"], links: [], updated: "示例", ai: "" },
  { id: "risk", kind: "note", title: "风险清单", body: "失效位 62,800；单次风险不超过账户 0.8%；重要宏观数据前不追单。\n\nback 链接 [[BTC 4小时突破观察]]", tags: ["BTC", "风控"], links: [], updated: "示例", ai: "" },
];

function Field({label,children,hint}){
  return <label className="trade-field"><span>{label}{hint&&<small>{hint}</small>}</span>{children}</label>;
}

function TradeForm({trade,onChange,records=[],onPick,onAnalyze,analysisBusy=false,fills=null,fillsState={},onLoadFills,onPickFill}){
  const metrics=tradeMetrics(trade);
  const [picker,setPicker]=useState('');
  const set=(key)=>(event)=>onChange({[key]:event.target.value});
  const others=records.filter(row=>row.id!==trade.id);
  const chosen=others.find(row=>row.id===picker);
  const realFills=Array.isArray(fills?.entries)?fills.entries:[];
  return <section className="trade-form">
    <div className="trade-source">
      <label>
        <I.Receipt/>
        <select aria-label="从真实成交回填" value="" onChange={(event)=>{const id=event.target.value;if(id)onPickFill?.(id);}}>
          <option value="">从真实成交记录回填…（{realFills.length} 笔）</option>
          {realFills.map(row=><option key={row.execution_id} value={row.execution_id}>{`${row.symbol} · ${row.side==='sell'?'卖出':'买入'} · ${row.quantity}@${row.price??'未记录'} · ${String(row.recorded_at).slice(0,10)}`}</option>)}
        </select>
      </label>
      <button type="button" className="trade-fill" disabled={fillsState.busy} onClick={()=>onLoadFills?.()}>{fillsState.busy?'读取中…':realFills.length?'刷新成交':'读取账户成交'}</button>
      <button type="button" className="trade-analyze" disabled={analysisBusy} onClick={()=>onAnalyze?.()}><I.Sparkle/>{analysisBusy?'分析中…':'分析这笔'}</button>
    </div>
    <div className="trade-source is-local">
      <label>
        <I.ClipboardText/>
        <select aria-label="选取已有本地记录填充" value={picker} onChange={(event)=>{const id=event.target.value;setPicker(id);if(id)onPick?.(id);}}>
          <option value="">从本地手工记录回填…（{others.length} 条）</option>
          {others.map(row=><option key={row.id} value={row.id}>{`${row.symbol||'未填标的'} · ${row.side||'买入'} · ${row.status||'未记录'}${row.openedAt?` · ${row.openedAt}`:''}`}</option>)}
        </select>
      </label>
      {chosen&&<button type="button" className="trade-fill" onClick={()=>onPick?.(chosen.id)}><I.DownloadSimple/>再次填充</button>}
    </div>
    {fillsState.error&&<p className="trade-hint">{fillsState.error}</p>}
    {fillsState.ready&&!realFills.length&&<p className="trade-hint">当前账户在该市场没有 Paper 成交记录；这里不会用本地笔记或示例数字顶替。</p>}
    {!fillsState.ready&&!fillsState.error&&<p className="trade-hint">「真实成交」来自后端 Paper 账本，需要在顶部选定已校验账户后读取；本地手工记录是另一组，两者不会混在一起。</p>}
    <div className="trade-form-grid">
      <Field label="标的"><input aria-label="交易标的" value={trade.symbol||''} onChange={set('symbol')} placeholder="BTC/USDT"/></Field>
      <Field label="方向"><select aria-label="交易方向" value={trade.side||'买入'} onChange={set('side')}><option>买入</option><option>卖出</option></select></Field>
      <Field label="状态"><select aria-label="交易状态" value={trade.status||TRADE_STATUS.open} onChange={set('status')}><option>{TRADE_STATUS.open}</option><option>{TRADE_STATUS.closed}</option></select></Field>
      <Field label="进场价"><input aria-label="进场价" inputMode="decimal" value={trade.entryPrice??''} onChange={set('entryPrice')}/></Field>
      <Field label="数量"><input aria-label="持仓数量" inputMode="decimal" value={trade.quantity??''} onChange={set('quantity')}/></Field>
      <Field label="止损价" hint="填了才能算风险"><input aria-label="止损价" inputMode="decimal" value={trade.stopLoss??''} onChange={set('stopLoss')}/></Field>
      <Field label="止盈价" hint="填了才能算盈亏比"><input aria-label="止盈价" inputMode="decimal" value={trade.takeProfit??''} onChange={set('takeProfit')}/></Field>
      <Field label="平仓价" hint={trade.status===TRADE_STATUS.closed?'平仓后填写':'持有中可留空'}><input aria-label="平仓价" inputMode="decimal" value={trade.exitPrice??''} onChange={set('exitPrice')} disabled={trade.status!==TRADE_STATUS.closed}/></Field>
      <Field label="手续费"><input aria-label="手续费" inputMode="decimal" value={trade.fees??''} onChange={set('fees')}/></Field>
      <Field label="开仓日"><input aria-label="开仓日期" type="date" value={trade.openedAt||''} onChange={set('openedAt')}/></Field>
    </div>
    <dl className="trade-metrics">
      <div><dt>名义金额</dt><dd>{money(metrics.cost)}</dd></div>
      <div><dt>单笔风险</dt><dd>{money(metrics.risk)}{metrics.riskRatio!==null&&<small>{(metrics.riskRatio*100).toFixed(2)}%</small>}</dd></div>
      <div><dt>潜在盈利</dt><dd>{money(metrics.reward)}</dd></div>
      <div><dt>盈亏比</dt><dd>{metrics.riskReward!==null?`${metrics.riskReward.toFixed(2)} : 1`:'未计算'}</dd></div>
      <div><dt>已实现盈亏</dt><dd className={metrics.realized>0?'gain':metrics.realized<0?'loss':''}>{metrics.closed?signed(metrics.realized):'未平仓'}</dd></div>
      <div><dt>R 倍数</dt><dd>{metrics.rMultiple!==null?`${metrics.rMultiple.toFixed(2)}R`:'未计算'}</dd></div>
    </dl>
    {!metrics.valid&&<p className="trade-hint">填写进场价与正数数量后，才会计算名义金额与风险；不会用示例数字补齐。</p>}
    {metrics.closed&&metrics.realized===null&&<p className="trade-hint">已标记平仓但缺少有效平仓价，已实现盈亏留空而不是按现价推测。</p>}
  </section>;
}

function JournalOverview({entries,index}){
  const stats=useMemo(()=>journalStats(entries),[entries]);
  const positions=useMemo(()=>openPositions(entries),[entries]);
  const gaps=useMemo(()=>journalGaps(entries),[entries]);
  return <section className="journal-overview">
    <div className="journal-stats">
      <article><small>已实现盈亏</small><strong className={stats.realized>0?'gain':stats.realized<0?'loss':''}>{signed(stats.realized)}</strong><span>{stats.closed} 笔已平仓</span></article>
      <article><small>胜率</small><strong>{stats.winRate===null?'未计算':`${stats.winRate.toFixed(1)}%`}</strong><span>{stats.wins} 胜 / {stats.losses} 负{stats.unknown?` · ${stats.unknown} 笔缺平仓价`:''}</span></article>
      <article><small>盈亏比</small><strong>{stats.profitFactor===null?'未计算':`${stats.profitFactor.toFixed(2)} : 1`}</strong><span>平均盈 {money(stats.averageWin)} / 平均亏 {money(stats.averageLoss)}</span></article>
      <article><small>持仓中</small><strong>{stats.open} 笔</strong><span>风险敞口 {money(stats.riskedOpen)} · 占用 {money(stats.capitalOpen)}</span></article>
    </div>
    <div className="journal-panels">
      <section>
        <header><b>持仓汇总</b><span>{positions.length} 个标的</span></header>
        {positions.length===0?<p className="journal-empty">没有未平仓记录。新建「交易记录」并保持状态为持有中即可累计。</p>:
          <table><thead><tr><th>标的</th><th>数量</th><th>均价</th><th>成本</th><th>风险</th></tr></thead><tbody>
          {positions.map(row=><tr key={row.symbol}><td>{row.symbol}{row.mixedSides&&<small>买卖并存</small>}</td><td>{row.quantity}</td><td>{money(row.averageEntry)}</td><td>{money(row.cost)}</td><td>{money(row.risked)}</td></tr>)}
          </tbody></table>}
      </section>
      <section>
        <header><b>数据积累缺口</b><span>用于判断统计是否可信</span></header>
        {gaps.length===0?<p className="journal-empty">记录字段齐全，可以开始复盘。</p>:<ul className="journal-gaps">{gaps.map((gap,index)=><li key={index}>{gap}</li>)}</ul>}
      </section>
      <section>
        <header><b>按标的已实现</b><span>{stats.bySymbol.length} 个</span></header>
        {stats.bySymbol.length===0?<p className="journal-empty">还没有已平仓记录。</p>:
          <ul className="symbol-rows">{stats.bySymbol.map(row=><li key={row.symbol}><b>{row.symbol}</b><span>{row.count} 笔 · {row.wins}胜{row.losses}负</span><em className={row.realized>0?'gain':row.realized<0?'loss':''}>{signed(row.realized)}</em></li>)}</ul>}
      </section>
      <section>
        <header><b>知识库索引</b><span>{index.edgeCount} 条链接</span></header>
        <dl className="index-stats">
          <div><dt>标签</dt><dd>{index.tagIndex.size}</dd></div>
          <div><dt>孤立笔记</dt><dd>{index.orphans.length}</dd></div>
          <div><dt>悬空链接</dt><dd>{index.broken.length}</dd></div>
        </dl>
        {index.broken.length>0&&<ul className="broken-links">{index.broken.slice(0,6).map((row,index)=><li key={index}><b>{row.noteTitle}</b> → [[{row.title}]] 尚无对应笔记</li>)}</ul>}
      </section>
    </div>
  </section>;
}

export function StrategyNotebook({ say, setSavedStrategies,openOverlay,initialNoteId,onReviewConstitution }) {
  const [notes, setNotes] = useLocalState("ai-trading-assistant-strategy-notes", seedNotes);
  const [selectedId, setSelectedId] = useState(initialNoteId||notes[0]?.id);
  const [query, setQuery] = useState("");
  const [graphOpen, setGraphOpen] = useState(false);
  const [tagDraft, setTagDraft] = useState("");
  const [linkDraft, setLinkDraft] = useState("");
  const [nodeOffsets, setNodeOffsets] = useState({});
  const [view, setView] = useState('editor');
  const [fills,setFills]=useState(null),[fillsState,setFillsState]=useState({});
  const fillsJob=useRef(null);

  const index=useMemo(()=>buildLinkIndex(notes),[notes]);
  const selected = notes.find((note) => note.id === selectedId) || notes[0];
  const connections=useMemo(()=>selected?noteConnections(index,selected.id):{outgoing:[],incoming:[],related:[]},[index,selected?.id]);
  const suggestions=useMemo(()=>selected?linkSuggestions(index,selected.id,linkDraft):[],[index,selected?.id,linkDraft]);
  const positions = useMemo(() => notes.map((note, nodeIndex) => ({ ...note, x: 60 + (nodeIndex % 3) * 172 + (nodeOffsets[note.id]?.x || 0), y: 52 + Math.floor(nodeIndex / 3) * 116 + (nodeOffsets[note.id]?.y || 0) })), [notes, nodeOffsets]);
  const filtered = notes.filter((note) => `${note.title}${note.body}${note.symbol||''}${noteTags(note).join(" ")}`.toLowerCase().includes(query.toLowerCase()));
  const update = (patch) => setNotes(notes.map((note) => note.id === selected.id ? { ...note, ...patch, updated: "刚刚" } : note));
  const kind=selected?noteKind(selected):'note';

  const createNote = () => {
    const note = newNote(`${Date.now()}`);
    setNotes([note, ...notes]); setSelectedId(note.id); setView('editor'); say("已新建本地交易心得");
  };
  const createTrade = () => {
    const trade = newTrade(`${Date.now()}`);
    setNotes([trade, ...notes]); setSelectedId(trade.id); setView('editor'); say("已新建本地交易记录");
  };
  const analyze = () => {
    const question=noteAnalysisPrompt(selected,index);
    const detail={includeMarket:false,question:question.slice(0,4000)};
    window.dispatchEvent(new CustomEvent('ai-trading-assistant-research-intent',{detail}));
    say(detail.accepted?'已准备笔记分析，请在右侧 AI 面板核对后手动发送':'AI面板未接收，请重新打开后重试');
  };
  // Copy an existing record's trading parameters into the record being edited.
  // Title, body and tags stay put so the user's own reasoning is never overwritten.
  const pickTrade = (sourceId) => {
    const source=notes.find(row=>row.id===sourceId);
    if(!source||!selected||source.id===selected.id)return;
    update({
      symbol:source.symbol??'', side:source.side??'买入', status:source.status??TRADE_STATUS.open,
      entryPrice:source.entryPrice??'', quantity:source.quantity??'', exitPrice:source.exitPrice??'',
      stopLoss:source.stopLoss??'', takeProfit:source.takeProfit??'', fees:source.fees??'',
      openedAt:source.openedAt??'',
    });
    say(`已按「${source.title}」回填交易参数；标题、正文与标签保持不变`);
  };
  const generate = () => {
    const context=getTerminalTradingContext();
    openOverlay('strategyCreate','编辑笔记研究草稿',{strategy:strategyDraftFromNote(selected,context)});
    say('请核对标的并填写预算；尚未保存或启动策略');
  };
  // Real Paper fills come from the backend ledger and need a verified account.
  const loadFills = async () => {
    const context=getTerminalTradingContext();
    if(!context?.accountVerified||!context.accountId||!['stocks','cex'].includes(context.market)){
      setFillsState({ready:false,error:'请先在顶部选择一个已校验的股票或 CEX 账户，再读取真实成交。'});
      return;
    }
    fillsJob.current?.abort();
    const controller=new AbortController();fillsJob.current=controller;
    setFillsState(previous=>({...previous,busy:true,error:''}));
    try{
      const params=new URLSearchParams({account_id:context.accountId,market:context.market});
      const packet=paperTradeHistory(await apiRequest('/api/v2/workspaces/research/paper-trades?'+params,{signal:controller.signal}),context);
      if(controller.signal.aborted)return;
      setFills(packet);setFillsState({busy:false,ready:true,error:''});
      say(`已读取 ${packet.entries.length} 笔 Paper 成交`);
    }catch(error){
      if(controller.signal.aborted)return;
      setFillsState({busy:false,ready:false,error:'无法读取当前账户的 Paper 成交，请检查登录、账户权限与后端连接。'});
    }
  };
  // Fill from a real fill: quantity and average price are authoritative.
  // Exit price, stop and target are NOT invented — they stay as the user left them.
  const pickFill = (executionId) => {
    const row=(fills?.entries||[]).find(item=>item.execution_id===executionId);
    if(!row||!selected)return;
    update({
      symbol:`${row.symbol}/${row.asset_currency}`, side:row.side==='sell'?'卖出':'买入',
      status:row.status==='filled'?TRADE_STATUS.closed:TRADE_STATUS.open,
      entryPrice:row.price??'', quantity:row.quantity??'', fees:row.fee??'',
      openedAt:String(row.recorded_at).slice(0,10),
      fillExecutionId:row.execution_id, fillVenue:row.venue,
    });
    say(`已按真实成交 ${row.execution_id.slice(0,8)} 回填标的、方向、数量、均价与费用；止盈止损与平仓价需你自行填写`);
  };
  const addTag = () => {
    const tag = tagDraft.trim().replace(/^#/, "");
    if (!tag || noteTags(selected).includes(tag)) return setTagDraft("");
    update({ tags: [...noteTags(selected), tag] }); setTagDraft(""); say(`已添加标签 #${tag}`);
  };
  const insertLink = (title) => {
    const body=String(selected.body||'');
    const next=body.includes('[[ ]]')?body.replace('[[ ]]',`[[${title}]]`):`${body}${body.endsWith('\n')?'':'\n'}关联：[[${title}]]`;
    update({body:next}); setLinkDraft(''); say(`已插入链接 [[${title}]]`);
  };

  if (!selected) return <div className="strategy-empty"><I.Notebook/><h3>开始你的交易知识库</h3><p>记录交易记录与心得，用 [[双向链接]] 把它们连起来。</p><div className="strategy-empty-actions"><button onClick={createTrade}>新建交易记录</button><button onClick={createNote}>新建交易心得</button></div></div>;

  return <section className={`strategy-notebook ${graphOpen ? "graph-open" : "graph-closed"}`}>
    <aside className="note-library">
      <header><span><small>本地知识库</small><b>{notes.length} 条记录 · {index.edgeCount} 链接</b></span><div className="note-library-actions"><button aria-label="新建交易记录" title="新建交易记录" onClick={createTrade}><I.Notepad/></button><button aria-label="新建交易心得" title="新建交易心得" onClick={createNote}><I.Plus/></button></div></header>
      <div className="note-view-switch">{[['editor','编辑'],['journal','复盘总览']].map(([id,label])=><button key={id} className={view===id?'on':''} onClick={()=>setView(id)}>{label}</button>)}</div>
      <label><I.MagnifyingGlass/><input aria-label="搜索交易记录与笔记" value={query} onChange={(e)=>setQuery(e.target.value)} placeholder="搜索标题、标签、标的"/></label>
      <nav>{filtered.map((note)=><button key={note.id} className={selected.id===note.id?"on":""} onClick={()=>setSelectedId(note.id)}><b>{noteKind(note)==='trade'&&<i className="kind-badge">记录</i>}{note.title}</b><small>{noteKind(note)==='trade'?`${note.symbol||'未填标的'} · ${note.status||'未记录'}`:note.body.replace(/\[\[|\]\]/g,'').replace(/\n/g," ").slice(0,46)}</small><span className="note-list-tags">{noteTags(note).slice(0,3).map((tag)=><i key={tag}>#{tag}</i>)}</span><em>{note.updated}</em></button>)}</nav>
    </aside>

    {view==='journal'?<article className="journal-view"><JournalOverview entries={notes} index={index}/></article>:<article className="note-editor">
      <header><div><small>{kind==='trade'?'交易记录 / 自动保存':'交易心得 / 自动保存'}</small><input aria-label="笔记标题" value={selected.title} onChange={(e)=>update({title:e.target.value})}/></div><button className={graphOpen ? "on" : ""} aria-label="展开双向关联" title="双向关联" onClick={()=>setGraphOpen(!graphOpen)}><I.Graph/></button><button aria-label="删除当前记录" onClick={()=>{ const next=notes.filter(n=>n.id!==selected.id); setNotes(next); setSelectedId(next[0]?.id); say("已删除"); }}><I.Trash/></button></header>
      <div className="note-tag-editor"><span>{noteTags(selected).map((tag)=><button key={tag} title={`移除 #${tag}`} onClick={()=>update({tags:noteTags(selected).filter((item)=>item!==tag)})}>#{tag}<I.X/></button>)}</span><label><I.Tag/><input aria-label="添加笔记标签" value={tagDraft} onChange={(e)=>setTagDraft(e.target.value)} onKeyDown={(e)=>{if(e.key==="Enter"){e.preventDefault();addTag();}}} placeholder="添加标签，回车确认"/></label></div>
      {kind==='trade'&&<TradeForm trade={selected} onChange={update} records={notes.filter(row=>noteKind(row)==='trade')} onPick={pickTrade} onAnalyze={analyze} fills={fills} fillsState={fillsState} onLoadFills={loadFills} onPickFill={pickFill}/>}
      <textarea aria-label="笔记正文" value={selected.body} onChange={(e)=>update({body:e.target.value})} placeholder={kind==='trade'?'写下进场理由、当时的依据与失效条件…':'记录行情事实、交易假设与失效条件… 用 [[标题]] 建立双向链接'}/>
      <section className="link-panel">
        <header><b>双向链接</b><span>{connections.outgoing.length} 出 / {connections.incoming.length} 入 / {connections.related.length} 标签关联</span></header>
        <label className="link-input"><I.Link/><input aria-label="插入双向链接" value={linkDraft} onChange={(e)=>setLinkDraft(e.target.value)} onKeyDown={(e)=>{if(e.key==='Enter'&&linkDraft.trim()){e.preventDefault();insertLink(linkDraft.trim());}}} placeholder="输入标题后回车，插入 [[链接]]"/></label>
        {linkDraft.trim()&&<div className="link-suggestions">{suggestions.length===0?<button onClick={()=>insertLink(linkDraft.trim())}>新建链接 [[{linkDraft.trim()}]]</button>:suggestions.map(row=><button key={row.id} onClick={()=>insertLink(row.title)}>{row.title}</button>)}</div>}
        {parseWikiLinks(selected.body).length>0&&<ul className="link-targets">{parseWikiLinks(selected.body).map(title=>{const target=index.byTitle.get(String(title).trim().toLowerCase());return <li key={title}><button disabled={!target} onClick={()=>target&&setSelectedId(target)}>→ {title}{!target&&<small>尚无对应笔记</small>}</button></li>;})}</ul>}
        {(connections.incoming.length>0||connections.related.length>0)&&<ul className="link-back">{[...connections.incoming.map(row=>({...row,dir:'← 被引用'})),...connections.related.map(row=>({...row,dir:'# 标签关联'}))].map(row=><li key={row.dir+row.id}><button onClick={()=>setSelectedId(row.id)}><small>{row.dir}</small>{row.note.title}</button></li>)}</ul>}
      </section>
      <div className="note-actions">{onReviewConstitution&&<button onClick={()=>onReviewConstitution(selected.id)}><I.Notepad/>作为宪章迭代依据</button>}<button onClick={analyze}><I.Sparkle/>AI 分析{kind==='trade'?'这笔交易':'这篇笔记'}</button><button className="primary" onClick={generate}><I.Robot/>生成策略草稿</button></div>
      <section className="note-ai-result"><header><I.Sparkle/><b>已保存的分析</b><span>历史内容，来源未验证</span></header><p>{selected.ai || "点击「AI 分析」会把记录内容与链接关系准备到右侧 AI 面板，核对后手动发送。"}</p></section>
    </article>}

    {graphOpen && <aside className="knowledge-graph">
      <header><div><small>链接与标签驱动 · 可拖动</small><b>双向关联</b></div><span>{index.edgeCount} 条链接 · {index.tagIndex.size} 标签</span><button aria-label="收起双向关联" onClick={()=>setGraphOpen(false)}><I.X/></button></header>
      <svg viewBox="0 0 580 400" role="img" aria-label="交易知识库关联图谱">
        {positions.flatMap((node)=>{const edges=new Set([...(index.outgoing.get(node.id)||[]),...[...(index.backlinks.get(node.id)||[])].filter(id=>!index.outgoing.get(node.id)?.has(id))]);return [...edges].map((id)=>{const target=positions.find(n=>n.id===id);return target?<line key={`${node.id}-${id}`} x1={node.x+40} y1={node.y+40} x2={target.x+40} y2={target.y+40}/>:null;});})}
        {positions.map((node)=><g key={node.id} className={node.id===selected.id?"on":""} transform={`translate(${node.x} ${node.y})`} onClick={()=>setSelectedId(node.id)} onPointerMove={(e)=>{if(e.buttons===1)setNodeOffsets((current)=>({...current,[node.id]:{x:(current[node.id]?.x||0)+e.movementX,y:(current[node.id]?.y||0)+e.movementY}}));}} role="button" tabIndex="0"><circle cx="40" cy="40" r="38"/><text x="40" y="36" textAnchor="middle">{node.title.slice(0,7)}</text><text className="bubble-tag" x="40" y="53" textAnchor="middle">{noteKind(node)==='trade'?'交易记录':`#${noteTags(node)[0] || "未分类"}`}</text></g>)}
      </svg>
      <footer><span><i/>当前节点</span><span><i/>实线为双向链接</span><small>拖动气泡调整视图</small></footer>
    </aside>}
  </section>;
}

const TRACKING = {
  main: { title:"主力追踪", kicker:"机构与巨鲸资金行为", stats:[["24h 主力净流入","+$86.4M"],["活跃大单","127"],["多空强度","1.38"]], rows:[["BTC/USDT","现货持续吸筹","+$42.8M","强"],["ETH/USDT","大单买入加速","+$18.3M","强"],["SOL/USDT","永续减仓整理","-$6.7M","中"],["XRP/USDT","盘口挂单承接","+$4.2M","中"]] },
  hot: { title:"游资追踪", kicker:"短周期活跃资金与题材轮动", stats:[["1h 活跃资金","$31.7M"],["高热标的","18"],["轮动速度","7.2x"]], rows:[["PEPE/USDT","社交热度突破","+$8.6M","强"],["WIF/USDT","成交量急升","+$6.1M","强"],["HYPE/USDT","高换手震荡","+$3.8M","中"],["ENA/USDT","题材资金回流","+$2.4M","中"]] }
};

export function CapitalTracker({ mode, say, setSavedStrategies,openOverlay }) {
  const data=TRACKING[mode]; const [period,setPeriod]=useState("24小时"); const [market,setMarket]=useState("全部市场");
  const [watch,setWatch]=useLocalState(`ai-trading-assistant-${mode}-tracking-watch`,[]); const [selected,setSelected]=useState(data.rows[0]);
  const create=(row)=>{openOverlay("strategyCreate","编辑追踪研究草稿",{strategy:{name:`${row[0]} ${data.title}研究`,coin:row[0].split("/")[0],type:data.title,amount:"",status:"草稿",trigger:"",invalidation:"",constraints:"此入口来自固定界面示例，未取得真实资金流来源；请先核对市场、账户和证据。"}});};
  const review=()=>{
    const detail={includeMarket:false,question:'请为'+data.title+'制定可审阅的数据核验清单：说明资金分类、场所、样本时段、净流口径、异常成交和失效条件。所选标的仅为界面示例名称 '+selected[0]+'；没有附带真实资金流、报价或交易者身份数据。不要把示例当作市场事实，不推断真实交易者身份，不生成收益或执行结论。'};
    window.dispatchEvent(new CustomEvent('ai-trading-assistant-research-intent',{detail}));
    say(detail.accepted?'已准备数据核验问题，请在AI面板手动发送':'AI面板未接收，请重新打开后再试');
  };
  return <section className="capital-tracker"><header><div><small>{data.kicker}</small><h3>{data.title}</h3><p>固定界面示例，尚未接入真实资金流或交易者来源；筛选仅保存偏好，不会查询或重算数据。</p></div><div><select aria-label={`${data.title}周期`} value={period} onChange={(e)=>setPeriod(e.target.value)}><option>1小时</option><option>4小时</option><option>24小时</option><option>7天</option></select><select aria-label={`${data.title}市场`} value={market} onChange={(e)=>setMarket(e.target.value)}><option>全部市场</option><option>币安</option><option>欧易OKX</option><option>Hyperliquid</option></select></div></header>
    <div className="tracker-stats">{data.stats.map((x)=><article key={x[0]}><small>{x[0]}</small><strong>{x[1]}</strong><span>筛选偏好：{period} · {market}（未查询）</span></article>)}</div>
    <div className="tracker-grid"><section><header><b>资金信号流</b><span>固定示例顺序</span></header>{data.rows.map((row)=><button key={row[0]} className={selected[0]===row[0]?"on":""} onClick={()=>setSelected(row)}><i>{row[0].slice(0,2)}</i><span><b>{row[0]}</b><small>{row[1]}</small></span><strong className={row[2].startsWith("-")?"loss":""}>{row[2]}</strong><em>{row[3]}</em></button>)}</section>
      <aside><header><span><small>信号详情</small><h4>{selected[0]}</h4></span><button aria-label={`关注${selected[0]}`} className={watch.includes(selected[0])?"on":""} onClick={()=>{setWatch(watch.includes(selected[0])?watch.filter(x=>x!==selected[0]):[...watch,selected[0]]);say(watch.includes(selected[0])?"已取消关注":"已加入重点关注");}}><I.Star weight={watch.includes(selected[0])?"fill":"regular"}/></button></header><div className="signal-meter"><span style={{width:selected[3]==="强"?"82%":"61%"}}/></div><dl><div><dt>资金方向</dt><dd>{selected[2]}</dd></div><div><dt>行为识别</dt><dd>{selected[1]}</dd></div><div><dt>可信等级</dt><dd>示例：{selected[3]} · 来源未接入</dd></div><div><dt>失效提醒</dt><dd>净流向反转或量价背离</dd></div></dl><p><I.Sparkle/>示例提示（非模型输出）：等待价格确认，不追逐单一大额成交；用分批入场和明确失效位控制风险。</p><button onClick={review}>AI 核对数据需求</button><button className="primary" onClick={()=>create(selected)}>编辑研究草稿</button></aside></div>
  </section>;
}

export {FloatingAIChat} from './research-ai-chat.jsx';
