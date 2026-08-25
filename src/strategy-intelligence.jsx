import React, { useMemo, useState } from "react";
import * as I from "@phosphor-icons/react";
import "./strategy-intelligence.css";

function useLocalState(key, seed) {
  const [value, setValue] = useState(() => {
    try { return JSON.parse(localStorage.getItem(key)) || seed; } catch { return seed; }
  });
  const save = (next) => { setValue(next); localStorage.setItem(key, JSON.stringify(next)); };
  return [value, save];
}

const seedNotes = [
  { id: "btc-breakout", title: "BTC 4小时突破观察", body: "价格在 64,200 附近反复测试，成交量收缩。等待放量站稳再介入。\n\n关联：[[主力净流入]] [[风险清单]]\n#BTC #突破", tags: ["BTC", "突破"], links: ["flow", "risk"], updated: "今天 14:32", ai: "偏多但尚未确认。触发条件：4H 收盘站上 64,200 且成交量高于 20 日均量 1.4 倍。" },
  { id: "flow", title: "主力净流入", body: "BTC 大单净流入连续 3 个周期转正，现货买盘强于永续。\n\n关联：[[BTC 4小时突破观察]]", tags: ["BTC", "资金流"], links: ["btc-breakout"], updated: "今天 13:18", ai: "资金行为与突破假设一致，但要排除短时拉盘。" },
  { id: "risk", title: "风险清单", body: "失效位 62,800；单次风险不超过账户 0.8%；重要宏观数据前不追单。", tags: ["BTC", "风控"], links: ["btc-breakout"], updated: "昨天 21:06", ai: "已识别 3 条硬性风控约束。" },
];

const noteTags = (note) => note.tags?.length ? note.tags : (note.body.match(/#[\w\u4e00-\u9fa5]+/g) || []).map((tag) => tag.slice(1));

export function StrategyNotebook({ say, setSavedStrategies }) {
  const [notes, setNotes] = useLocalState("ai-trading-assistant-strategy-notes", seedNotes);
  const [selectedId, setSelectedId] = useState(notes[0]?.id);
  const [query, setQuery] = useState("");
  const [graphOpen, setGraphOpen] = useState(false);
  const [tagDraft, setTagDraft] = useState("");
  const [nodeOffsets, setNodeOffsets] = useState({});
  const selected = notes.find((note) => note.id === selectedId) || notes[0];
  const update = (patch) => setNotes(notes.map((note) => note.id === selected.id ? { ...note, ...patch, updated: "刚刚" } : note));
  const filtered = notes.filter((note) => `${note.title}${note.body}${noteTags(note).join(" ")}`.toLowerCase().includes(query.toLowerCase()));
  const positions = useMemo(() => notes.map((note, index) => ({ ...note, x: 52 + (index % 3) * 168 + (nodeOffsets[note.id]?.x || 0), y: 48 + Math.floor(index / 3) * 112 + (nodeOffsets[note.id]?.y || 0) })), [notes, nodeOffsets]);
  const relatedIds = useMemo(() => {
    const map = new Map();
    notes.forEach((note) => map.set(note.id, new Set(note.links || [])));
    notes.forEach((note) => notes.forEach((other) => {
      if (note.id === other.id) return;
      const shared = noteTags(note).filter((tag) => noteTags(other).includes(tag));
      if (shared.length || (other.links || []).includes(note.id)) map.get(note.id).add(other.id);
    }));
    return map;
  }, [notes]);
  const createNote = () => {
    const note = { id: `${Date.now()}`, title: "未命名交易笔记", body: "记录行情事实、交易假设与失效条件…", tags: ["待整理"], links: [], updated: "刚刚", ai: "" };
    setNotes([note, ...notes]); setSelectedId(note.id); say("已创建本地策略笔记");
  };
  const analyze = () => {
    const tags = (selected.body.match(/#[\w\u4e00-\u9fa5]+/g) || []).join("、") || "未标注";
    update({ ai: `AI 结论：当前笔记更接近“条件触发型”策略。主题 ${tags}；建议补全入场确认、失效位和仓位上限，再进入模拟验证。` });
    say("AI 已完成笔记结构化分析");
  };
  const generate = () => {
    setSavedStrategies((items) => [{ id: Date.now(), name: selected.title, coin: selected.body.match(/BTC|ETH|SOL|XRP/)?.[0] || "BTC", type: "AI笔记策略", amount: "100", status: "草稿" }, ...items]);
    say("已生成策略草稿，可在“我的套利”继续编辑");
  };
  const addTag = () => {
    const tag = tagDraft.trim().replace(/^#/, "");
    if (!tag || noteTags(selected).includes(tag)) return setTagDraft("");
    update({ tags: [...noteTags(selected), tag] }); setTagDraft(""); say(`已添加标签 #${tag}`);
  };
  if (!selected) return <div className="strategy-empty"><I.Notebook/><h3>暂无策略笔记</h3><button onClick={createNote}>新建第一篇笔记</button></div>;
  return <section className={`strategy-notebook ${graphOpen ? "graph-open" : "graph-closed"}`}>
    <aside className="note-library">
      <header><span><small>本地知识库</small><b>{notes.length} 篇笔记</b></span><button aria-label="新建策略笔记" onClick={createNote}><I.Plus/></button></header>
      <label><I.MagnifyingGlass/><input aria-label="搜索策略笔记" value={query} onChange={(e)=>setQuery(e.target.value)} placeholder="搜索笔记、标签或币种"/></label>
      <nav>{filtered.map((note)=><button key={note.id} className={selected.id===note.id?"on":""} onClick={()=>setSelectedId(note.id)}><b>{note.title}</b><small>{note.body.replace(/\n/g," ").slice(0,46)}</small><span className="note-list-tags">{noteTags(note).slice(0,3).map((tag)=><i key={tag}>#{tag}</i>)}</span><em>{note.updated}</em></button>)}</nav>
    </aside>
    <article className="note-editor">
      <header><div><small>交易笔记 / 自动保存</small><input aria-label="策略笔记标题" value={selected.title} onChange={(e)=>update({title:e.target.value})}/></div><button className={graphOpen ? "on" : ""} aria-label="展开双向关联" title="双向关联" onClick={()=>setGraphOpen(!graphOpen)}><I.Graph/></button><button aria-label="删除当前策略笔记" onClick={()=>{ const next=notes.filter(n=>n.id!==selected.id); setNotes(next); setSelectedId(next[0]?.id); say("笔记已删除"); }}><I.Trash/></button></header>
      <div className="note-tag-editor"><span>{noteTags(selected).map((tag)=><button key={tag} title={`移除 #${tag}`} onClick={()=>update({tags:noteTags(selected).filter((item)=>item!==tag)})}>#{tag}<I.X/></button>)}</span><label><I.Tag/><input aria-label="添加笔记标签" value={tagDraft} onChange={(e)=>setTagDraft(e.target.value)} onKeyDown={(e)=>{if(e.key==="Enter"){e.preventDefault();addTag();}}} placeholder="添加标签，回车确认"/></label></div>
      <textarea aria-label="策略笔记正文" value={selected.body} onChange={(e)=>update({body:e.target.value})}/>
      <div className="note-actions"><button onClick={analyze}><I.Sparkle/>AI 分析笔记</button><button className="primary" onClick={generate}><I.Robot/>生成策略草稿</button></div>
      <section className="note-ai-result"><header><I.Sparkle/><b>AI 策略分析</b><span>基于当前笔记</span></header><p>{selected.ai || "点击“AI 分析笔记”，提取交易假设、触发条件与风险缺口。"}</p></section>
    </article>
    {graphOpen && <aside className="knowledge-graph">
      <header><div><small>标签驱动 · 可拖动</small><b>双向关联</b></div><span>{Array.from(relatedIds.values()).reduce((n,set)=>n+set.size,0)} 条连接</span><button aria-label="收起双向关联" onClick={()=>setGraphOpen(false)}><I.X/></button></header>
      <svg viewBox="0 0 580 360" role="img" aria-label="策略笔记双向关联图谱">
        {positions.flatMap((node)=>Array.from(relatedIds.get(node.id) || []).map((id)=>{const target=positions.find(n=>n.id===id);return target?<line key={`${node.id}-${id}`} x1={node.x+40} y1={node.y+40} x2={target.x+40} y2={target.y+40}/>:null}))}
        {positions.map((node)=><g key={node.id} className={node.id===selected.id?"on":""} transform={`translate(${node.x} ${node.y})`} onClick={()=>setSelectedId(node.id)} onPointerMove={(e)=>{if(e.buttons===1)setNodeOffsets((current)=>({...current,[node.id]:{x:(current[node.id]?.x||0)+e.movementX,y:(current[node.id]?.y||0)+e.movementY}}));}} role="button" tabIndex="0"><circle cx="40" cy="40" r="38"/><text x="40" y="36" textAnchor="middle">{node.title.slice(0,7)}</text><text className="bubble-tag" x="40" y="53" textAnchor="middle">#{noteTags(node)[0] || "未分类"}</text></g>)}
      </svg>
      <footer><span><i/>当前笔记</span><span><i/>标签关联</span><small>拖动气泡调整视图</small></footer>
    </aside>}
  </section>;
}

const TRACKING = {
  main: { title:"主力追踪", kicker:"机构与巨鲸资金行为", stats:[["24h 主力净流入","+$86.4M"],["活跃大单","127"],["多空强度","1.38"]], rows:[["BTC/USDT","现货持续吸筹","+$42.8M","强"],["ETH/USDT","大单买入加速","+$18.3M","强"],["SOL/USDT","永续减仓整理","-$6.7M","中"],["XRP/USDT","盘口挂单承接","+$4.2M","中"]] },
  hot: { title:"游资追踪", kicker:"短周期活跃资金与题材轮动", stats:[["1h 活跃资金","$31.7M"],["高热标的","18"],["轮动速度","7.2x"]], rows:[["PEPE/USDT","社交热度突破","+$8.6M","强"],["WIF/USDT","成交量急升","+$6.1M","强"],["HYPE/USDT","高换手震荡","+$3.8M","中"],["ENA/USDT","题材资金回流","+$2.4M","中"]] }
};

export function CapitalTracker({ mode, say, setSavedStrategies }) {
  const data=TRACKING[mode]; const [period,setPeriod]=useState("24小时"); const [market,setMarket]=useState("全部市场");
  const [watch,setWatch]=useLocalState(`ai-trading-assistant-${mode}-tracking-watch`,[]); const [selected,setSelected]=useState(data.rows[0]);
  const create=(row)=>{setSavedStrategies((items)=>[{id:Date.now(),name:`${row[0]} ${data.title}策略`,coin:row[0].split("/")[0],type:data.title,amount:"100",status:"草稿"},...items]);say("信号已生成本地策略草稿");};
  return <section className="capital-tracker"><header><div><small>{data.kicker}</small><h3>{data.title}</h3><p>信号为本地模拟分析，仅用于研究，不会自动提交订单。</p></div><div><select aria-label={`${data.title}周期`} value={period} onChange={(e)=>setPeriod(e.target.value)}><option>1小时</option><option>4小时</option><option>24小时</option><option>7天</option></select><select aria-label={`${data.title}市场`} value={market} onChange={(e)=>setMarket(e.target.value)}><option>全部市场</option><option>币安</option><option>欧易OKX</option><option>Hyperliquid</option></select></div></header>
    <div className="tracker-stats">{data.stats.map((x)=><article key={x[0]}><small>{x[0]}</small><strong>{x[1]}</strong><span>{period} · {market}</span></article>)}</div>
    <div className="tracker-grid"><section><header><b>资金信号流</b><span>按强度排序</span></header>{data.rows.map((row)=><button key={row[0]} className={selected[0]===row[0]?"on":""} onClick={()=>setSelected(row)}><i>{row[0].slice(0,2)}</i><span><b>{row[0]}</b><small>{row[1]}</small></span><strong className={row[2].startsWith("-")?"loss":""}>{row[2]}</strong><em>{row[3]}</em></button>)}</section>
      <aside><header><span><small>信号详情</small><h4>{selected[0]}</h4></span><button aria-label={`关注${selected[0]}`} className={watch.includes(selected[0])?"on":""} onClick={()=>{setWatch(watch.includes(selected[0])?watch.filter(x=>x!==selected[0]):[...watch,selected[0]]);say(watch.includes(selected[0])?"已取消关注":"已加入重点关注");}}><I.Star weight={watch.includes(selected[0])?"fill":"regular"}/></button></header><div className="signal-meter"><span style={{width:selected[3]==="强"?"82%":"61%"}}/></div><dl><div><dt>资金方向</dt><dd>{selected[2]}</dd></div><div><dt>行为识别</dt><dd>{selected[1]}</dd></div><div><dt>可信等级</dt><dd>{selected[3]} · 多源确认</dd></div><div><dt>失效提醒</dt><dd>净流向反转或量价背离</dd></div></dl><p><I.Sparkle/>AI 建议：等待价格确认，不追逐单一大额成交；用分批入场和明确失效位控制风险。</p><button className="primary" onClick={()=>create(selected)}>生成策略草稿</button></aside></div>
  </section>;
}

export function FloatingAIChat({ open, onClose, page, symbol, say }) {
  const [messages,setMessages]=useLocalState("ai-trading-assistant-ai-dialog",[{id:1,role:"ai",text:"我是交易工作台 AI。可以整理当前行情、分析策略笔记，或把想法转成模拟策略。"}]);
  const [input,setInput]=useState(""); const ask=(text=input)=>{if(!text.trim())return;const answer=`已结合 ${symbol}/USDT 与当前${page==="strategy"?"策略":"行情"}工作区分析：建议先定义触发条件、失效位和最大风险，再做本地模拟验证。`;setMessages([...messages,{id:Date.now(),role:"user",text},{id:Date.now()+1,role:"ai",text:answer}]);setInput("");};
  if(!open)return null;
  return <aside className="floating-ai"><header><div className="ai-avatar"><I.Sparkle/></div><span><b>AI 交易助手</b><small><i/>正在读取当前工作区</small></span><button aria-label="关闭AI对话" onClick={onClose}><I.X/></button></header><div className="ai-context"><span>{symbol}/USDT</span><span>{page==="strategy"?"策略工作区":"全局工作区"}</span><em>本地模拟</em></div><div className="ai-messages">{messages.slice(-6).map(m=><p key={m.id} className={m.role}>{m.text}</p>)}</div><div className="ai-prompts">{["总结当前机会","检查策略风险","整理成交易笔记"].map(x=><button key={x} onClick={()=>ask(x)}>{x}</button>)}</div><footer><textarea aria-label="向AI交易助手提问" value={input} onChange={e=>setInput(e.target.value)} onKeyDown={e=>{if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();ask();}}} placeholder="输入问题，Enter 发送…"/><button aria-label="发送AI消息" onClick={()=>{ask();say("AI 已回复");}}><I.ArrowUp/></button></footer></aside>;
}
