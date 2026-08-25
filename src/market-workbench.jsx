import React, { useEffect, useMemo, useState } from "react";
import * as I from "@phosphor-icons/react";
import "./market-workbench.css";

const ORDER_TABS = [
  "现货仓位(0)", "当前委托(0)", "策略(0)", "历史委托", "买卖记录",
  "账户资产", "预估清算图", "深度图", "技术分析", "主力",
];

const EMPTY_ROWS = {
  "现货仓位(0)": ["币种", "数量", "买入均价", "现价", "持仓盈亏", "操作"],
  "当前委托(0)": ["交易对", "方向", "委托价", "委托数量", "成交比例", "状态"],
  "策略(0)": ["策略", "交易对", "运行状态", "累计收益", "创建时间", "操作"],
  "历史委托": ["交易对", "方向", "委托类型", "成交均价", "成交数量", "时间"],
  "买卖记录": ["交易对", "方向", "成交价", "成交数量", "手续费", "成交时间"],
};

function useLocalState(key, initialValue) {
  const readStoredValue = () => {
    if (typeof window === "undefined") return initialValue;
    try {
      const stored = window.localStorage.getItem(key);
      return stored ? JSON.parse(stored) : initialValue;
    } catch {
      return initialValue;
    }
  };
  const [value, setValue] = useState(readStoredValue);
  useEffect(() => {
    setValue(readStoredValue());
  }, [key]);
  useEffect(() => {
    const sync = (event) => {
      if (event.detail?.key === key) setValue(event.detail.value);
    };
    window.addEventListener("ai-trading-assistant-local-state", sync);
    return () => window.removeEventListener("ai-trading-assistant-local-state", sync);
  }, [key]);
  const update = (nextValue) => {
    setValue((current) => {
      const resolved = typeof nextValue === "function" ? nextValue(current) : nextValue;
      try { window.localStorage.setItem(key, JSON.stringify(resolved)); } catch { /* local demo can continue without persistence */ }
      window.dispatchEvent(new CustomEvent("ai-trading-assistant-local-state", { detail: { key, value: resolved } }));
      return resolved;
    });
  };
  return [value, update];
}

function makeLocalStrategy({ kind, name, symbol, amount, mode, detail }) {
  return {
    id: Date.now(), kind, name, symbol, amount, mode, detail,
    status: "运行中", pnl: "+0.00", orders: 0,
    createdAt: new Date().toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }),
  };
}

function EmptyTable({ tab, authorized, openOverlay }) {
  const heads = EMPTY_ROWS[tab] || EMPTY_ROWS["当前委托(0)"];
  return (
    <div className="terminal-table empty-terminal-table">
      <header>{heads.map((x) => <b key={x}>{x}</b>)}</header>
      <div className="terminal-empty">
        <I.Tray />
        <b>{authorized ? `${tab.replace(/\(0\)/, "")}暂无记录` : "尚未连接交易账户"}</b>
        <small>{authorized ? "调整筛选条件或切换其他账户查看" : "授权后可同步委托、成交与持仓数据"}</small>
        {!authorized && <button onClick={() => openOverlay("apiAuth", "连接交易账户")}>连接账户</button>}
      </div>
    </div>
  );
}

function AccountAssets({ authorized, openOverlay }) {
  return (
    <div className="account-assets-panel">
      <header><b>账户资产</b><button onClick={() => openOverlay("apiAuth", "管理授权账户")}>管理账户</button></header>
      <div className="asset-summary-row">
        <article><small>总资产折合</small><strong>{authorized ? "12,846.32 USDT" : "--"}</strong><em>≈ ¥92,486</em></article>
        <article><small>可用资产</small><strong>{authorized ? "9,420.18 USDT" : "--"}</strong><em>73.33%</em></article>
        <article><small>冻结资产</small><strong>{authorized ? "3,426.14 USDT" : "--"}</strong><em>26.67%</em></article>
      </div>
      <div className="terminal-table asset-mini-table">
        <header>{["币种", "总额", "可用", "冻结", "折合(USDT)", "操作"].map(x => <b key={x}>{x}</b>)}</header>
        {(authorized ? [["USDT","8,420.18","5,000.00","3,420.18","8,420.18"],["BTC","0.0521","0.0520","0.0001","3,426.14"]] : []).map(r => <div key={r[0]}>{r.map(x => <span key={x}>{x}</span>)}<button onClick={() => openOverlay("transfer", `${r[0]} 账户划转`)}>划转</button></div>)}
      </div>
    </div>
  );
}

function EstimatedLiquidation({ symbol }) {
  const [range, setRange] = useState("12H");
  const bars = useMemo(() => Array.from({ length: 28 }, (_, i) => ({
    h: 16 + ((i * 23) % 78), danger: i < 7 || i > 22,
  })), []);
  return (
    <div className="analysis-panel liquidation-panel">
      <header><div><b>{symbol}/USDT 预估清算图</b><small>聚合 Binance、OKX、Bybit 永续合约</small></div><div>{["12H","24H","3日"].map(x => <button className={range === x ? "on" : ""} key={x} onClick={() => setRange(x)}>{x}</button>)}</div></header>
      <div className="liq-chart">
        {bars.map((b, i) => <i key={i} className={b.danger ? "danger" : "safe"} style={{height:`${b.h}%`}} />)}
        <span className="liq-price">当前价 65,731.77</span>
      </div>
      <footer><span>多单清算密集区 <b>64,820</b></span><span>空单清算密集区 <b>67,100</b></span><span>最大清算强度 <b>$3.28亿</b></span></footer>
    </div>
  );
}

function DepthPanel({ symbol }) {
  const [step, setStep] = useState("0.1%");
  return (
    <div className="analysis-panel depth-workbench">
      <header><div><b>{symbol}/USDT 深度图</b><small>买卖盘累计委托量</small></div><div>{["0.1%","0.5%","1%"].map(x => <button className={step === x ? "on" : ""} key={x} onClick={() => setStep(x)}>{x}</button>)}</div></header>
      <div className="depth-area"><i className="depth-buy"/><i className="depth-sell"/><span>65,731.77</span></div>
      <footer><span className="green">买盘 $82.4M · 56.75%</span><span className="red">卖盘 $62.8M · 43.25%</span><span>委比 +13.50%</span></footer>
    </div>
  );
}

function TechnicalPanel({ symbol }) {
  const [period, setPeriod] = useState("5分");
  const signals = [["移动平均线","强力卖出",22],["震荡指标","中性",50],["趋势指标","卖出",35],["成交量","中性偏弱",44]];
  return (
    <div className="technical-panel">
      <header><div><b>{symbol}/USDT 技术分析</b><small>{period} · 22:45 更新</small></div><div>{["5分","15分","1时","4时","1日"].map(x=><button className={period===x?"on":""} key={x} onClick={() => setPeriod(x)}>{x}</button>)}</div></header>
      <section><div className="tech-gauge"><i/><strong>卖出</strong><small>综合评分 36</small></div><div>{signals.map(x=><p key={x[0]}><span>{x[0]}</span><b>{x[1]}</b><i><em style={{width:`${x[2]}%`}}/></i></p>)}</div></section>
      <footer>支撑位 <b>65,553</b>　阻力位 <b>66,120</b>　波动率 <b>0.29%</b></footer>
    </div>
  );
}

function MainForcePanel({ symbol, openOverlay }) {
  return (
    <div className="mainforce-panel">
      <header><div><b>{symbol}/USDT 主力大单</b><small>当前平台 · 最近1小时</small></div><button onClick={() => openOverlay("aiChart", "AI解读主力订单")}>AI解读</button></header>
      <div className="force-metrics"><article><small>主力活跃度</small><strong>68</strong><em>活跃</em></article><article><small>挂单差</small><strong className="green">+$12.4M</strong><em>主力看涨</em></article><article><small>成交差</small><strong className="red">-$4.8M</strong><em>短线抛压</em></article><article><small>主力均价</small><strong>65,842</strong><em>-0.17%</em></article></div>
      <div className="terminal-table force-table"><header>{["时间","方向","委托价","初始金额","已成交","持续"].map(x=><b key={x}>{x}</b>)}</header>{[["22:43:18","买入","65,620","$2.48M","71%","2分14秒"],["22:41:03","卖出","65,980","$1.82M","38%","4分09秒"],["22:37:46","买入","65,553","$3.16M","86%","7分31秒"]].map(r=><div key={r[0]}>{r.map((x,i)=><span className={i===1?(x==="买入"?"green":"red"):""} key={x}>{x}</span>)}</div>)}</div>
    </div>
  );
}

function OrdersPanel({ symbol, authorized, openOverlay, say }) {
  const [sub, setSub] = useState("现货仓位(0)");
  const [onlyPair, setOnlyPair] = useState(false);
  const [orders, setOrders] = useLocalState("ai-trading-assistant-quick-orders", []);
  const scopedOrders = onlyPair ? orders.filter((order) => (order.symbol || "BTC") === symbol) : orders;
  const pendingOrders = scopedOrders.filter((order) => order.status === "等待成交");
  const historicalOrders = scopedOrders.filter((order) => order.status !== "等待成交");
  const filledOrders = scopedOrders.filter((order) => order.status === "模拟成交");
  const positions = Object.values(filledOrders.reduce((result, order) => {
    const coin = order.symbol || "BTC";
    const quantity = Number(order.quantity) || 0;
    const signed = order.side === "卖出" ? -quantity : quantity;
    const current = result[coin] || { coin, quantity: 0, buyQuantity: 0, buyValue: 0, lastPrice: Number(order.price) || 0 };
    current.quantity += signed;
    current.lastPrice = Number(order.price) || current.lastPrice;
    if (order.side === "买入") {
      current.buyQuantity += quantity;
      current.buyValue += quantity * (Number(order.price) || 0);
    }
    result[coin] = current;
    return result;
  }, {})).filter((position) => position.quantity > 0.00000001);
  const cancelOrder = (id) => {
    setOrders((current) => current.map((order) => order.id === id ? { ...order, status: "已撤销", canceledAt: new Date().toLocaleTimeString("zh-CN") } : order));
    say("限价模拟委托已撤销并归入历史");
  };
  const closePosition = (position) => {
    const record = { id: Date.now(), side: "卖出", type: "市价", symbol: position.coin, price: String(position.lastPrice), quantity: String(position.quantity), status: "模拟成交", createdAt: new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" }) };
    setOrders((current) => [record, ...current]);
    say(`${position.coin} 本地模拟仓位已平仓`);
  };
  const empty = (title) => <div className="terminal-empty"><I.Tray/><b>{title}</b><small>右侧下单面板创建的本地模拟委托会同步显示在这里</small></div>;
  const orderRows = (rows, current = false) => rows.length ? <div className="terminal-table local-order-table"><header>{["交易对","方向 / 类型","委托价","委托数量","时间","状态 / 操作"].map((name)=><b key={name}>{name}</b>)}</header>{rows.map((order)=><div key={order.id}><b>{order.symbol || "BTC"}/USDT</b><span className={order.side === "买入" ? "green" : "red"}>{order.side} · {order.type}</span><span>{order.price}</span><span>{order.quantity} {order.symbol || "BTC"}</span><span>{order.createdAt || "本地"}</span><span><em className={order.status === "模拟成交" ? "green" : order.status === "已撤销" ? "red" : ""}>{order.status}</em>{current && <button onClick={()=>cancelOrder(order.id)}>撤单</button>}</span></div>)}</div> : empty(current ? "暂无当前委托" : "暂无历史委托");
  let content;
  if (sub === "现货仓位(0)") content = positions.length ? <div className="terminal-table local-position-table"><header>{["币种","数量","买入均价","现价","持仓盈亏","操作"].map((name)=><b key={name}>{name}</b>)}</header>{positions.map((position)=>{const average=position.buyQuantity ? position.buyValue/position.buyQuantity : position.lastPrice; const pnl=(position.lastPrice-average)*position.quantity; return <div key={position.coin}><b>{position.coin}</b><span>{position.quantity.toFixed(6)}</span><span>{average.toFixed(4)}</span><span>{position.lastPrice.toFixed(4)}</span><span className={pnl>=0?"green":"red"}>{pnl>=0?"+":""}{pnl.toFixed(2)} USDT</span><button onClick={()=>closePosition(position)}>模拟平仓</button></div>})}</div> : empty("暂无本地模拟仓位");
  else if (sub === "当前委托(0)") content = orderRows(pendingOrders, true);
  else if (sub === "历史委托") content = orderRows(historicalOrders);
  else if (sub === "买卖记录") content = orderRows(filledOrders);
  else if (EMPTY_ROWS[sub]) content = <EmptyTable tab={sub} authorized={authorized} openOverlay={openOverlay}/>;
  else if (sub === "账户资产") content = <AccountAssets authorized={authorized} openOverlay={openOverlay}/>;
  else if (sub === "预估清算图") content = <EstimatedLiquidation symbol={symbol}/>;
  else if (sub === "深度图") content = <DepthPanel symbol={symbol}/>;
  else if (sub === "技术分析") content = <TechnicalPanel symbol={symbol}/>;
  else content = <MainForcePanel symbol={symbol} openOverlay={openOverlay}/>;
  const labelFor = (name) => name === "现货仓位(0)" ? `现货仓位(${positions.length})` : name === "当前委托(0)" ? `当前委托(${pendingOrders.length})` : name;
  return <div className="orders-terminal"><div className="work-subtabs scroll-tabs">{ORDER_TABS.map(x=><button className={sub===x?"on":""} key={x} onClick={()=>setSub(x)}>{labelFor(x)}</button>)}<label><input type="checkbox" checked={onlyPair} onChange={e=>setOnlyPair(e.target.checked)}/> 当前币对</label></div>{content}</div>;
}

function IndicatorPanel({ symbol, setSymbol, say }) {
  const [section, setSection] = useState("指标编辑");
  const [status, setStatus] = useState("编译通过");
  const [code, setCode] = useState("// @version=2\n\n[td]=td(close)\nplot(td, color.green)\nalertcondition(td > 8, '超买')");
  const [search, setSearch] = useState("");
  const [groupName, setGroupName] = useState("");
  const [groupOpen, setGroupOpen] = useState(false);
  const [savedGroups, setSavedGroups] = useState([]);
  const [backtestStatus, setBacktestStatus] = useState("ready");
  const [backtestHistory, setBacktestHistory] = useState(false);
  const [backtestPeriod, setBacktestPeriod] = useState("5分");
  const [capital, setCapital] = useState("10000");
  const [fee, setFee] = useState("0.10");
  const [aiPrompt, setAiPrompt] = useState("");
  const [aiStage, setAiStage] = useState("idle");
  const [aiMessages, setAiMessages] = useState([]);
  const [liveStrategies, setLiveStrategies] = useLocalState("ai-trading-assistant-indicator-live-strategies", []);
  const runningLiveCount = liveStrategies.filter((item) => item.status !== "已终止").length;
  const menus = [{ key: "AI指标助手", label: "AI指标助手" }, { key: "指标编辑", label: "指标编辑" }, { key: "指标选币", label: "指标选币" }, { key: "策略回测", label: "策略回测" }, { key: "实盘运行 (0/30)", label: `实盘运行 (${runningLiveCount}/30)` }, { key: "实盘历史", label: "实盘历史" }];
  const candidates = [["BTC/USDT","5分","超卖","22:41","-1.24%"],["ETH/USDT","15分","金叉","22:36","-0.82%"],["SOL/USDT","1时","趋势转强","22:15","+1.16%"]]
    .filter((row) => row.join(" ").toLowerCase().includes(search.toLowerCase()));
  let body;
  if(section === "AI指标助手") body = <div className="ai-indicator-assistant"><header><div><I.Sparkle/><span><b>AI指标助手</b><small>用自然语言生成、解释和修复指标</small></span></div><em>本地演示</em></header><section>{aiMessages.length?aiMessages.map((message)=><article className={message.role} key={message.id}><small>{message.role==="user"?"你":"AI指标助手"}</small><p>{message.text}</p>{message.code&&<pre>{message.code}</pre>}{message.code&&<footer><button onClick={()=>{setCode(message.code);setStatus("未保存");setSection("指标编辑");say("AI生成代码已写入指标编辑器")}}>写入编辑器</button><button onClick={()=>{setCode(message.code);setSection("策略回测");say("已载入AI指标并进入回测")}}>立即回测</button></footer>}</article>):<div className="assistant-starter"><I.MagicWand/><b>描述你想验证的信号</b><small>例如：生成一个结合 RSI 超卖和成交量放大的买入指标</small><div>{["RSI超卖反转","均线突破确认","修复当前代码"].map((name)=><button key={name} onClick={()=>setAiPrompt(name)}>{name}</button>)}</div></div>}{aiStage==="thinking"&&<div className="assistant-thinking"><i/><i/><i/><span>正在生成指标逻辑与风险说明</span></div>}</section><footer><textarea value={aiPrompt} onChange={(event)=>setAiPrompt(event.target.value)} placeholder="输入指标需求或粘贴报错信息"/><button disabled={aiStage==="thinking"} onClick={()=>{if(!aiPrompt.trim())return say("请输入指标需求");const prompt=aiPrompt.trim();setAiMessages((current)=>[...current,{id:Date.now(),role:"user",text:prompt}]);setAiPrompt("");setAiStage("thinking");window.setTimeout(()=>{const generated="// @version=2\n[rsiValue]=rsi(close, 14)\n[volumeAvg]=sma(volume, 20)\nbuySignal = rsiValue < 30 && volume > volumeAvg * 1.5\nplotshape(buySignal, 'BUY', color.green)\nalertcondition(buySignal, 'RSI放量反转')";setAiMessages((current)=>[...current,{id:Date.now()+1,role:"assistant",text:"已生成 RSI 超卖与成交量确认指标，并加入信号预警条件。建议先用 90 天数据回测，再调整阈值。",code:generated}]);setAiStage("done")},450)}}><I.PaperPlaneTilt/>{aiStage==="thinking"?"生成中":"发送"}</button></footer><p className="assistant-safety">AI 生成结果仅用于本地研究，不构成投资建议，不会直接启动实盘。</p></div>;
  else if(section === "指标编辑") body = <div className="indicator-editor"><header><b>自定义TD指标策略_副本</b><button onClick={()=>{setCode("// @version=2\n");setStatus("未保存")}}>新建⌄</button><button onClick={()=>setSection("AI指标助手")}><I.Sparkle/>AI写指标</button><button onClick={()=>{setStatus("已保存");say("指标已保存")}}>保存</button><button onClick={()=>{setStatus("编译通过");say("编译通过")}}>编译</button><button onClick={()=>setSection("策略回测")}>立即回测</button></header><textarea value={code} onChange={e=>{setCode(e.target.value);setStatus("未保存")}}/><footer><span className={status==="编译通过"?"ok":""}>● {status}</span><span>{code.split("\n").length} 行</span></footer></div>;
  else if(section === "指标选币") body = <div className="indicator-screener"><header><b>指标选币</b><input value={search} onChange={(e)=>setSearch(e.target.value)} placeholder="搜索指标或币种"/><button className={groupOpen?"on":""} onClick={()=>setGroupOpen(!groupOpen)}>创建动态分组</button></header>{groupOpen&&<div className="dynamic-group-form"><input value={groupName} onChange={(e)=>setGroupName(e.target.value)} placeholder="分组名称，例如 TD超卖"/><select defaultValue="超卖"><option>超卖</option><option>金叉</option><option>趋势转强</option></select><button onClick={()=>{if(!groupName.trim())return say("请输入分组名称");setSavedGroups([...savedGroups,groupName.trim()]);setGroupName("");setGroupOpen(false);say("动态分组已创建")}}>保存分组</button></div>}<p>通过自定义指标策略筛选目标交易对，动态管理自选分组。{savedGroups.length>0&&<span> 已保存：{savedGroups.join("、")}</span>}</p><div className="terminal-table"><header>{["交易对","周期","最新信号","触发时间","涨跌幅","操作"].map(x=><b key={x}>{x}</b>)}</header>{candidates.map(r=><div key={r[0]}>{r.map(x=><span key={x}>{x}</span>)}<button onClick={()=>{setSymbol(r[0].split("/")[0]);say(`K线已切换到 ${r[0]}`)}}>查看K线</button></div>)}</div></div>;
  else if(section === "策略回测") body = <div className="backtest-panel"><header><b>指标回测 · {symbol}/USDT</b><button className={backtestHistory?"on":""} onClick={()=>setBacktestHistory(!backtestHistory)}>{backtestHistory?"返回结果":"回测历史"}</button></header>{backtestHistory?<div className="backtest-history-table"><div><b>2026-07-22 22:46</b><span>{symbol}/USDT · {backtestPeriod}</span><em>+18.42%</em><button onClick={()=>setBacktestHistory(false)}>查看</button></div><div><b>2026-07-20 18:12</b><span>ETH/USDT · 15分</span><em>+9.76%</em><button onClick={()=>setBacktestHistory(false)}>查看</button></div></div>:<><div className="backtest-controls"><label>周期<select value={backtestPeriod} onChange={(e)=>setBacktestPeriod(e.target.value)}><option>5分</option><option>15分</option><option>1时</option></select></label><label>日期范围<input value="近90天" readOnly/></label><label>初始资金<input value={capital} onChange={(e)=>setCapital(e.target.value)} inputMode="decimal"/></label><label>手续费（%）<input value={fee} onChange={(e)=>setFee(e.target.value)} inputMode="decimal"/></label><button disabled={backtestStatus==="running"} onClick={()=>{if(Number(capital)<=0||Number(fee)<0)return say("请输入有效回测参数");setBacktestStatus("running");window.setTimeout(()=>setBacktestStatus("done"),500)}}>{backtestStatus==="running"?"计算中…":"开始回测"}</button></div>{backtestStatus==="ready"?<div className="backtest-ready"><I.ChartLine/><b>设置参数并开始回测</b><small>结果会保存到回测历史</small></div>:backtestStatus==="running"?<div className="backtest-ready"><I.Spinner className="spin"/><b>正在回放 90 天历史行情</b><small>计算信号、成交与手续费</small></div>:<><div className="backtest-metrics">{[["策略收益","+18.42%"],["最大回撤","-6.83%"],["胜率","62.5%"],["交易次数","48"],["盈亏比","1.84"]].map(x=><article key={x[0]}><small>{x[0]}</small><strong>{x[1]}</strong></article>)}</div><div className="equity-curve"><i/><span>策略净值</span><em>基准收益 +4.10%</em><button onClick={() => { if (runningLiveCount >= 30) return say("实盘模拟策略已达到30个上限"); const record = makeLocalStrategy({ kind: "指标实盘", name: "自定义TD指标策略_副本", symbol: `${symbol}/USDT`, amount: capital, mode: `${backtestPeriod} · TD信号`, detail: `近90天回测 +18.42% · 手续费 ${fee}%` }); setLiveStrategies((current) => [record, ...current]); setSection("实盘运行 (0/30)"); say("指标本地模拟实盘已创建"); }}>创建模拟实盘</button></div></>}</>}</div>;
  else body = <BotStrategyList title={section === "实盘运行 (0/30)" ? `实盘运行 (${runningLiveCount}/30)` : section} icon={I.Robot} onCreate={()=>setSection("指标编辑")} strategies={liveStrategies} setStrategies={setLiveStrategies} say={say}/>;
  return <div className="indicator-terminal"><aside>{menus.map((item)=><button className={section===item.key?"on":""} key={item.key} onClick={()=>setSection(item.key)}>{item.label}<I.CaretRight/></button>)}</aside><section>{body}</section></div>;
}

function GridPanel({ symbol, authorized, openOverlay, say }) {
  const [section, setSection] = useState("创建网格");
  const [mode, setMode] = useState("一键创建");
  const [amount, setAmount] = useState("");
  const [lower, setLower] = useState("63200");
  const [upper, setUpper] = useState("68400");
  const [gridCount, setGridCount] = useState("24");
  const [calculated, setCalculated] = useState(false);
  const [strategies, setStrategies] = useLocalState("ai-trading-assistant-grid-strategies", []);
  const createStrategy = () => {
    if (!calculated) return say("请先完成收益测算");
    const record = makeLocalStrategy({ kind: "AI网格", name: `${symbol} ${mode}`, symbol: `${symbol}/USDT`, amount, mode, detail: `${lower}–${upper} · ${gridCount}格${authorized ? " · 已关联演示授权" : " · 未连接真实账户"}` });
    setStrategies((current) => [record, ...current]);
    setSection("运行中");
    setAmount("");
    setCalculated(false);
    say("网格本地模拟策略已创建");
  };
  return <div className="bot-terminal"><aside>{["创建网格","运行中","历史策略"].map((name)=><button className={section===name?"on":""} key={name} onClick={()=>setSection(name)}>{name}<em>{name === "运行中" ? strategies.filter((item) => item.status !== "已终止").length : name === "历史策略" ? strategies.filter((item) => item.status === "已终止").length : ""}</em></button>)}</aside><section>{section==="创建网格"?<><div className="risk-banner">网格机器人需要软件一直保持正常运行。当前复刻只创建本地模拟策略，不向交易所提交委托。</div><div className="bot-modes"><button onClick={()=>openOverlay("help","在线客服与常见问题")}>联系客服</button><button onClick={()=>openOverlay("help","网格策略教程")}>网格教程</button>{["一键创建","手动创建","杠杆网格"].map((name)=><button className={mode===name?"on":""} key={name} onClick={()=>{setMode(name);setCalculated(false)}}>{name}</button>)}</div><div className="bot-form"><div><b>1. 价格区间</b><small>{mode==="一键创建"?"AI参数":"手动参数"}</small><label><input aria-label="网格最低价" value={lower} onChange={(event)=>{setLower(event.target.value);setCalculated(false)}} placeholder="最低价"/><span>~</span><input aria-label="网格最高价" value={upper} onChange={(event)=>{setUpper(event.target.value);setCalculated(false)}} placeholder="最高价"/></label></div><div><b>2. 网格数量</b><label><input aria-label="网格数量" value={gridCount} onChange={(event)=>{setGridCount(event.target.value);setCalculated(false)}}/><span>每格利润 0.31% - 0.42%</span></label></div><div><b>3. 投入金额</b><label><input aria-label="网格投入金额" value={amount} onChange={event=>{setAmount(event.target.value);setCalculated(false)}} placeholder="≥ 20"/><span>USDT</span></label></div><footer><button onClick={()=>{if(Number(amount)<20||Number(lower)<=0||Number(upper)<=Number(lower)||Number(gridCount)<2)return say("请填写有效区间、网格数和不少于20 USDT的投入");setCalculated(true)}}>测算收益</button><button className="primary" onClick={createStrategy}>创建模拟网格</button>{calculated&&<output>预估7日收益 <b>+{(Number(amount)*0.0168).toFixed(2)} USDT</b></output>}</footer></div></>:<BotStrategyList title={section} icon={I.GridFour} onCreate={()=>setSection("创建网格")} strategies={strategies} setStrategies={setStrategies} say={say}/>}</section></div>;
}

function DcaPanel({ symbol, openOverlay, say }) {
  const [section, setSection] = useState("创建DCA");
  const [mode, setMode] = useState("一键创建");
  const [amount, setAmount] = useState("");
  const [frequency, setFrequency] = useState("每天");
  const [firstRun, setFirstRun] = useState("");
  const [takeProfit, setTakeProfit] = useState("20");
  const [strategies, setStrategies] = useLocalState("ai-trading-assistant-spot-dca-strategies", []);
  const createStrategy = () => {
    if (Number(amount) <= 0) return say("请输入每期金额");
    if (mode === "手动创建" && Number(takeProfit) <= 0) return say("请输入有效止盈比例");
    const record = makeLocalStrategy({ kind: "现货DCA", name: `${symbol} 长期定投`, symbol: `${symbol}/USDT`, amount, mode: `${mode} · ${frequency}`, detail: `止盈 ${takeProfit}%${firstRun ? ` · 首次 ${firstRun.replace("T", " ")}` : " · 立即开始"}` });
    setStrategies((current) => [record, ...current]);
    setSection("运行中");
    setAmount("");
    say("现货DCA本地模拟策略已创建");
  };
  return <div className="bot-terminal"><aside>{["创建DCA","运行中","历史策略"].map((name)=><button className={section===name?"on":""} key={name} onClick={()=>setSection(name)}>{name}<em>{name === "运行中" ? strategies.filter((item) => item.status !== "已终止").length : name === "历史策略" ? strategies.filter((item) => item.status === "已终止").length : ""}</em></button>)}</aside><section>{section==="创建DCA"?<><div className="bot-modes centered">{["一键创建","手动创建"].map((name)=><button className={mode===name?"on":""} key={name} onClick={()=>setMode(name)}>{name}</button>)}<button onClick={()=>openOverlay("help","DCA 定投教程")}>DCA教程</button></div><div className="dca-form"><header><div><b>{symbol} 长期定投</b><small>分批投入，摊薄成本</small></div><em>现货DCA</em></header><label>定投币种<input value={`${symbol}/USDT`} readOnly/></label><label>每期金额<input aria-label="DCA每期金额" value={amount} onChange={event=>setAmount(event.target.value)} placeholder="100 USDT"/></label><label>执行频率<select value={frequency} onChange={event=>setFrequency(event.target.value)}><option>每天</option><option>每周</option><option>每月</option></select></label>{mode==="手动创建"&&<><label>首次执行<input value={firstRun} onChange={(event) => setFirstRun(event.target.value)} type="datetime-local"/><span>按本地时区执行</span></label><label>止盈设置<input aria-label="DCA止盈设置" value={takeProfit} onChange={(event) => setTakeProfit(event.target.value)} placeholder="例如 20"/><span>%</span></label></>}<button onClick={createStrategy}>创建模拟DCA</button></div></>:<BotStrategyList title={section} icon={I.CalendarCheck} onCreate={()=>setSection("创建DCA")} strategies={strategies} setStrategies={setStrategies} say={say}/>}</section></div>;
}

function FuturesDcaPanel({ symbol, openOverlay, say }) {
  const [section, setSection] = useState("创建DCA");
  const [mode, setMode] = useState("平衡型");
  const [direction, setDirection] = useState("做多");
  const [amount, setAmount] = useState("");
  const [frequency, setFrequency] = useState("每4小时");
  const [leverage, setLeverage] = useState("3x");
  const [addRatio, setAddRatio] = useState("2.5");
  const [takeProfit, setTakeProfit] = useState("8");
  const [estimated, setEstimated] = useState(false);
  const [strategies, setStrategies] = useLocalState("ai-trading-assistant-futures-dca-strategies", []);
  const valid = Number(amount) >= 20 && Number(addRatio) > 0 && Number(takeProfit) > 0;
  return (
    <div className="bot-terminal futures-dca-terminal">
      <aside>
        {["创建DCA", "运行中", "历史策略"].map((name) => (
          <button className={section === name ? "on" : ""} key={name} onClick={() => setSection(name)}>{name}<em>{name === "运行中" ? strategies.filter((item) => item.status !== "已终止").length : name === "历史策略" ? strategies.filter((item) => item.status === "已终止").length : ""}</em></button>
        ))}
      </aside>
      <section>
        {section === "创建DCA" ? (
          <>
            <div className="risk-banner">合约DCA会放大收益与亏损。本地复刻只生成模拟任务，不发送真实委托。</div>
            <div className="bot-modes centered">
              {["平衡型", "保守型", "进取型"].map((name) => (
                <button className={mode === name ? "on" : ""} key={name} onClick={() => { setMode(name); setEstimated(false); }}>{name}</button>
              ))}
              <button onClick={() => openOverlay("help", "合约DCA教程")}>DCA教程</button>
            </div>
            <div className="futures-dca-form">
              <header><span><b>{symbol}/USDT 合约DCA</b><small>分批建仓 · 固定风险预算</small></span><em>{mode}</em></header>
              <label>方向<select value={direction} onChange={(event) => { setDirection(event.target.value); setEstimated(false); }}><option>做多</option><option>做空</option></select></label>
              <label>杠杆<select value={leverage} onChange={(event) => { setLeverage(event.target.value); setEstimated(false); }}><option>1x</option><option>2x</option><option>3x</option><option>5x</option><option>10x</option></select></label>
              <label>首次保证金<input value={amount} onChange={(event) => { setAmount(event.target.value); setEstimated(false); }} inputMode="decimal" placeholder="≥ 20 USDT" /></label>
              <label>执行频率<select value={frequency} onChange={(event) => setFrequency(event.target.value)}><option>每1小时</option><option>每4小时</option><option>每天</option><option>每周</option></select></label>
              <label>涨跌多少加仓<input value={addRatio} onChange={(event) => { setAddRatio(event.target.value); setEstimated(false); }} inputMode="decimal" /><span>%</span></label>
              <label>单次止盈目标<input value={takeProfit} onChange={(event) => { setTakeProfit(event.target.value); setEstimated(false); }} inputMode="decimal" /><span>%</span></label>
              <footer>
                <output>{estimated ? <><b>{direction} · {leverage}</b><span>预计最大加仓 6 次 · 风险预算 {(Number(amount) * 1.75).toFixed(2)} USDT</span></> : <span>先测算保证金、加仓间距与止盈参数</span>}</output>
                <button onClick={() => { if (!valid) return say("首次保证金需不少于20 USDT，并填写有效比例"); setEstimated(true); }}>风险测算</button>
                <button className="primary" onClick={() => { if (!estimated) return say("请先完成风险测算"); const record = makeLocalStrategy({ kind: "合约DCA", name: `${symbol} ${direction}DCA`, symbol: `${symbol}/USDT`, amount, mode: `${mode} · ${direction} · ${leverage}`, detail: `${frequency} · 每${addRatio}%加仓 · ${takeProfit}%止盈` }); setStrategies((current) => [record, ...current]); setSection("运行中"); setAmount(""); setEstimated(false); say("合约DCA本地模拟策略已创建"); }}>创建模拟任务</button>
              </footer>
            </div>
          </>
        ) : <BotStrategyList title={section} icon={I.ChartLineDown} onCreate={() => setSection("创建DCA")} strategies={strategies} setStrategies={setStrategies} say={say} />}
      </section>
    </div>
  );
}

function TradeHistoryPanel({ symbol, say }) {
  const [tab, setTab] = useState("成交记录");
  const [period, setPeriod] = useState("近7天");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(null);
  const [exported, setExported] = useState(false);
  const datasets = {
    "成交记录": [
      ["07-29 16:42:18", `${symbol}/USDT`, "买入", "65,731.77", "0.012", "+12.84"],
      ["07-29 14:06:31", "ETH/USDT", "卖出", "3,174.28", "0.28", "+18.63"],
      ["07-28 21:17:04", "SOL/USDT", "买入", "148.36", "4.20", "-6.12"],
    ],
    "策略执行": [
      ["07-29 15:40:00", "BTC震荡网格", "网格成交", "第18格", "0.008", "+7.42"],
      ["07-29 12:00:00", "ETH长期定投", "定投买入", "第12期", "0.16", "+4.18"],
      ["07-28 20:00:00", "TD序列反转", "信号平仓", "超买", "0.010", "+21.06"],
    ],
    "资金费用": [
      ["07-29 16:00:00", "BTC/USDT", "资金费", "0.0081%", "多仓", "-2.14"],
      ["07-29 08:00:00", "ETH/USDT", "资金费", "-0.0032%", "空仓", "+0.86"],
      ["07-28 24:00:00", "SOL/USDT", "手续费", "Maker", "成交", "-0.42"],
    ],
  };
  const rows = datasets[tab].filter((row) => row.join(" ").toLowerCase().includes(query.toLowerCase()));
  return (
    <div className="trade-history-terminal">
      <header>
        <div>{Object.keys(datasets).map((name) => <button className={tab === name ? "on" : ""} key={name} onClick={() => { setTab(name); setSelected(null); }}>{name}</button>)}</div>
        <select value={period} onChange={(event) => setPeriod(event.target.value)}><option>今天</option><option>近7天</option><option>近30天</option><option>自定义</option></select>
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索交易对或策略" />
        <button className={exported ? "exported" : ""} onClick={() => { setExported(true); say(`${tab}已生成本地导出记录`); }}>{exported ? "已导出" : "导出记录"}</button>
      </header>
      <section>
        <div className="terminal-table history-table">
          <header>{["时间", tab === "策略执行" ? "策略" : "交易对", "类型/方向", "价格/参数", "数量/仓位", "盈亏/费用"].map((name) => <b key={name}>{name}</b>)}</header>
          {rows.map((row) => <button className={selected?.[0] === row[0] ? "selected" : ""} key={`${tab}-${row[0]}`} onClick={() => setSelected(row)}>{row.map((value, index) => <span className={index === 5 ? (value.startsWith("+") ? "green" : "red") : ""} key={`${index}-${value}`}>{value}</span>)}</button>)}
          {!rows.length && <div className="terminal-empty"><I.MagnifyingGlass/><b>没有匹配的交易记录</b><small>修改关键词或时间范围后重试</small></div>}
        </div>
        <aside className={selected ? "history-detail open" : "history-detail"}>
          {selected ? <><small>{tab}详情 · {period}</small><h3>{selected[1]}</h3>{selected.map((value, index) => <p key={`${index}-${value}`}><span>{["时间", "标的", "动作", "价格/参数", "数量/仓位", "盈亏/费用"][index]}</span><b>{value}</b></p>)}<button onClick={() => setSelected(null)}>关闭详情</button></> : <><I.CursorClick/><b>选择记录查看详情</b></>}
        </aside>
      </section>
    </div>
  );
}

function BotStrategyList({ title, icon: Icon, onCreate, strategies, setStrategies, say }) {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState(title.includes("历史") ? "已终止" : "全部状态");
  const [selected, setSelected] = useState(null);
  const [selectedIds, setSelectedIds] = useState([]);
  const [detailTab, setDetailTab] = useState("收益概览");
  const [rangeDraft, setRangeDraft] = useState("");
  const historical = title === "历史策略" || title.includes("历史");
  useEffect(() => {
    setStatus(historical ? "已终止" : "全部状态");
    setSelected(null);
    setSelectedIds([]);
  }, [historical, title]);
  const rows = strategies.filter((item) => {
    const inSection = historical ? item.status === "已终止" : item.status !== "已终止";
    const statusMatch = status === "全部状态" || item.status === status;
    const queryMatch = `${item.name} ${item.symbol} ${item.mode}`.toLowerCase().includes(query.toLowerCase());
    return inSection && statusMatch && queryMatch;
  });
  const patchStrategy = (id, patch) => setStrategies((current) => current.map((item) => item.id === id ? { ...item, ...patch } : item));
  const batchPatch = (patch, message) => {
    if (!selectedIds.length) return say("请先选择策略");
    setStrategies((current) => current.map((item) => selectedIds.includes(item.id) ? { ...item, ...patch } : item));
    setSelectedIds([]);
    say(message);
  };
  const terminate = (item) => {
    patchStrategy(item.id, { status: "已终止", stoppedAt: "刚刚" });
    setSelected(null);
    say(`${item.name}已终止并归档`);
  };
  const restart = (item) => {
    const next = { ...item, id: Date.now(), status: "运行中", pnl: "+0.00", orders: 0, createdAt: "刚刚", stoppedAt: undefined };
    setStrategies((current) => [next, ...current]);
    say(`${item.name}已重新创建为本地模拟策略`);
  };
  return (
    <div className="bot-history strategy-lifecycle">
      <header><b>{title}</b><div><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索策略或交易对"/><select value={status} onChange={(event) => setStatus(event.target.value)}>{historical ? <><option>已终止</option></> : <><option>全部状态</option><option>运行中</option><option>已暂停</option><option>异常</option></>}</select>{historical && strategies.some((item) => item.status === "已终止") && <button className="danger" onClick={() => { setStrategies((current) => current.filter((item) => item.status !== "已终止")); setSelected(null); say("本地策略历史已清空"); }}>清空历史</button>}</div></header>
      {!historical&&rows.length>0&&<div className="strategy-batchbar"><label><input type="checkbox" checked={selectedIds.length===rows.length} onChange={(event)=>setSelectedIds(event.target.checked?rows.map((item)=>item.id):[])}/>全选</label><span>已选 {selectedIds.length}</span><button onClick={()=>batchPatch({status:"已暂停"},"所选策略已批量暂停")}>批量暂停</button><button onClick={()=>batchPatch({status:"运行中",error:null},"所选策略已批量恢复")}>批量恢复</button><button className="danger" onClick={()=>batchPatch({status:"已终止",stoppedAt:"刚刚"},"所选策略已批量终止并归档")}>批量终止</button></div>}
      {rows.length ? <div className="strategy-lifecycle-table"><header>{["策略", "标的", "投入", "状态", historical ? "终止时间" : "累计收益", "操作"].map((name) => <b key={name}>{name}</b>)}</header>{rows.map((item) => <div className={item.error?"has-error":""} key={item.id}><span><label><input type="checkbox" checked={selectedIds.includes(item.id)} onChange={(event)=>setSelectedIds(event.target.checked?[...selectedIds,item.id]:selectedIds.filter((id)=>id!==item.id))}/><strong>{item.name}</strong></label><small>{item.mode}</small></span><b>{item.symbol}</b><span>{item.amount} USDT</span><em className={item.status === "运行中" ? "green" : item.status === "已暂停" ? "amber" : item.status === "异常" ? "red" : ""}>{item.status}</em><span className={historical ? "" : item.pnl.startsWith("+") ? "green" : "red"}>{historical ? item.stoppedAt || item.createdAt : `${item.pnl} USDT`}</span><span className="strategy-actions"><button onClick={() => {setSelected(item);setDetailTab("收益概览");setRangeDraft(item.detail)}}>订单详情</button>{historical ? <button onClick={() => restart(item)}>重新运行</button> : item.error?<button onClick={()=>{patchStrategy(item.id,{status:"运行中",error:null});say("连接检查通过，策略已恢复运行")}}>检查并恢复</button>:<><button onClick={() => patchStrategy(item.id, { status: item.status === "运行中" ? "已暂停" : "运行中" })}>{item.status === "运行中" ? "暂停" : "继续"}</button><button className="danger" onClick={() => terminate(item)}>终止</button></>}</span>{item.error&&<p className="strategy-error"><I.WarningCircle/>{item.error}<button onClick={()=>{patchStrategy(item.id,{status:"运行中",error:null});say("异常已处理，策略恢复运行")}}>重试</button></p>}</div>)}</div> : <div className="terminal-empty"><Icon/><b>{query ? `没有匹配“${query}”的策略` : `${title}暂无策略`}</b><small>{historical ? "终止的策略会保留参数与结果，可重新创建模拟任务" : "创建后可在此管理运行状态、收益与策略参数"}</small><button onClick={onCreate}>创建新策略</button></div>}
      {selected && <aside className="strategy-detail order-detail"><header><div><small>本地模拟策略 · 订单详情</small><h3>{selected.name}</h3></div><button aria-label="关闭策略详情" onClick={() => setSelected(null)}><I.X/></button></header><nav>{["收益概览","当前委托","成交记录","策略参数"].map((name)=><button className={detailTab===name?"on":""} key={name} onClick={()=>setDetailTab(name)}>{name}</button>)}</nav>{detailTab==="收益概览"?<><div className="strategy-detail-metrics">{[["总收益",selected.pnl+" USDT"],["24H配对","12次"],["累计配对",`${selected.orders+38}次`],["月化收益","+8.42%"]].map(([label,value])=><span key={label}><small>{label}</small><b>{value}</b></span>)}</div><div className="strategy-mini-curve"><i/><small>策略收益曲线 · 本地样例</small></div></>:detailTab==="策略参数"?<div className="strategy-parameter-editor"><label>策略参数<input value={rangeDraft} onChange={(event)=>setRangeDraft(event.target.value)}/></label><button onClick={()=>{patchStrategy(selected.id,{detail:rangeDraft});setSelected({...selected,detail:rangeDraft});say("策略参数已更新")}}>保存修改</button><button onClick={()=>{patchStrategy(selected.id,{status:"异常",error:"行情连接中断，最近一次轮询未返回数据"});setSelected(null);say("已生成异常状态用于恢复流程验证")}}>模拟运行异常</button></div>:<div className="detail-orders"><header>{["时间","方向","价格","数量","状态"].map((name)=><b key={name}>{name}</b>)}</header>{(detailTab==="当前委托"?[["刚刚","买入","64,820","0.01","等待成交"]]:[["12:18:06","买入","64,720","0.01","已成交"],["11:42:31","卖出","65,140","0.01","已成交"]]).map((row)=><p key={row[0]}>{row.map((value)=><span key={value}>{value}</span>)}</p>)}</div>}<footer>本地模拟记录，不连接交易所，不提交真实订单。</footer></aside>}
    </div>
  );
}

function BasketPanel({ openOverlay, say }) {
  const [tab,setTab]=useState("组合下单"),[rows,setRows]=useState([{id:1,pair:"BTC/USDT",side:"买入",type:"限价",price:"",amount:""},{id:2,pair:"ETH/USDT",side:"买入",type:"限价",price:"",amount:""}]);
  const update=(id,key,value)=>setRows(rows.map(r=>r.id===id?{...r,[key]:value}:r));
  return <div className="basket-terminal"><div className="work-subtabs">{["组合下单","当前委托","历史委托"].map(x=><button className={tab===x?"on":""} key={x} onClick={()=>setTab(x)}>{x}</button>)}</div>{tab==="组合下单"?<><header><div><b>组合订单</b><small>一次配置多个交易对，提交前统一预览</small></div><button onClick={()=>setRows([...rows,{id:Date.now(),pair:"SOL/USDT",side:"买入",type:"限价",price:"",amount:""}])}>＋ 添加订单</button><button onClick={()=>setRows([])}>清空</button></header><div className="basket-grid"><b>交易对</b><b>方向</b><b>委托类型</b><b>价格</b><b>数量</b><b>操作</b>{rows.map(r=><React.Fragment key={r.id}><input value={r.pair} onChange={e=>update(r.id,"pair",e.target.value)}/><select value={r.side} onChange={e=>update(r.id,"side",e.target.value)}><option>买入</option><option>卖出</option></select><select value={r.type} onChange={e=>update(r.id,"type",e.target.value)}><option>限价</option><option>市价</option></select><input value={r.price} onChange={e=>update(r.id,"price",e.target.value)} placeholder="USDT"/><input value={r.amount} onChange={e=>update(r.id,"amount",e.target.value)} placeholder="数量"/><button onClick={()=>setRows(rows.filter(x=>x.id!==r.id))}><I.Trash/></button></React.Fragment>)}</div><footer><span>共 {rows.length} 笔订单 · 买入 {rows.filter(r=>r.side==="买入").length} · 卖出 {rows.filter(r=>r.side==="卖出").length}</span><button onClick={()=>{if(!rows.length)return say("请先添加组合订单");if(rows.some(r=>!r.amount||(!r.price&&r.type==="限价")))return say("请补全价格与数量");const estimated=rows.reduce((sum,r)=>sum+(Number(r.price)||65731.77)*Number(r.amount),0);openOverlay("basketPreview","组合订单预览",{description:"仅展示预览，不会执行真实交易。",orders:rows,estimatedTotal:`${estimated.toFixed(2)} USDT`})}}>预览组合订单</button></footer></>:<EmptyTable tab={tab} authorized={false} openOverlay={openOverlay}/>}</div>;
}

function CopyPanel({ openOverlay, say, venue = "CEX" }) {
  const [tab, setTab] = useState("策略广场");
  const [risk, setRisk] = useState("全部风险");
  const [selected, setSelected] = useState(null);
  const [amount, setAmount] = useState("500");
  const [stopLoss, setStopLoss] = useState("50");
  const [mode, setMode] = useState("定额跟单");
  const [subscriptions, setSubscriptions] = useLocalState(venue === "DEX" ? "ai-trading-assistant-dex-copy-subscriptions" : "ai-trading-assistant-copy-subscriptions", []);
  const strategies = venue === "DEX"
    ? [{ name:"0x71…8A 趋势仓",author:"Hyperliquid · 0x71…8A",profit:"+92.6%",win:"74%",risk:"中风险",symbol:"BTC-PERP" },{ name:"Smart Whale 08",author:"Hyperliquid · 0x9F…31",profit:"+138.1%",win:"61%",risk:"高风险",symbol:"ETH-PERP" },{ name:"Macro Fund 链上组合",author:"Hyperliquid · 0x42…D7",profit:"+38.4%",win:"79%",risk:"低风险",symbol:"SOL-PERP" }]
    : [{ name:"山寨轮动",author:"量化研究院",profit:"+84.2%",win:"68%",risk:"中风险",symbol:"SOL/USDT" },{ name:"趋势突破",author:"Crypto Alpha",profit:"+62.7%",win:"72%",risk:"中风险",symbol:"BTC/USDT" },{ name:"Meme猎手",author:"Whale Lab",profit:"+118.4%",win:"54%",risk:"高风险",symbol:"PEPE/USDT" }];
  const active = subscriptions.filter((item) => item.status !== "已终止");
  const history = subscriptions.filter((item) => item.status === "已终止");
  const startFollowing = () => {
    if (Number(amount) <= 0 || Number(stopLoss) <= 0) return say("请输入有效投入金额与跟单止损");
    if (active.some((item) => item.name === selected.name)) return say("该策略已在跟单中");
    const record = makeLocalStrategy({ kind: venue === "DEX" ? "DEX链上跟单" : "CEX策略跟单", name: selected.name, symbol: selected.symbol, amount, mode, detail: `来源 ${selected.author} · 最大亏损 ${stopLoss} USDT` });
    setSubscriptions((current) => [record, ...current]);
    setSelected(null);
    setTab("我的跟单");
    say(`${venue} 本地模拟跟单已启动`);
  };
  const patchSubscription = (id, patch) => setSubscriptions((current) => current.map((item) => item.id === id ? { ...item, ...patch } : item));
  const records = tab === "我的跟单" ? active : history;
  return <div className="copy-terminal"><header><div><b className="copy-venue">{venue === "DEX" ? "Hyperliquid 链上跟单" : "CEX 策略跟单"}</b>{["策略广场","我的跟单","跟单历史"].map((name)=><button className={tab===name?"on":""} key={name} onClick={()=>{setTab(name);setSelected(null)}}>{name}{name === "我的跟单" && active.length ? ` (${active.length})` : name === "跟单历史" && history.length ? ` (${history.length})` : ""}</button>)}{tab === "跟单历史" && history.length > 0 && <button className="danger" onClick={() => { setSubscriptions((current) => current.filter((item) => item.status !== "已终止")); say(`${venue} 跟单历史已清空`); }}>清空跟单历史</button>}</div><select aria-label={`${venue}跟单风险筛选`} value={risk} onChange={event=>setRisk(event.target.value)}><option>全部风险</option><option>低风险</option><option>中风险</option><option>高风险</option></select></header>{tab==="策略广场"?<div className="copy-grid">{strategies.filter(item=>risk==="全部风险"||item.risk===risk).map(item=><article key={item.name}><header><i>{item.name.slice(0,1)}</i><span><b>{item.name}</b><small>{item.author}</small></span><em>{item.risk}</em></header><div><span><small>30D收益</small><strong>{item.profit}</strong></span><span><small>胜率</small><strong>{item.win}</strong></span><span><small>{venue === "DEX" ? "地址跟随" : "跟单人数"}</small><strong>{venue === "DEX" ? "428" : "1,284"}</strong></span></div><p>{venue === "DEX" ? "追踪公开链上仓位变化，按本地风控参数生成模拟订阅。" : "根据资金流、趋势强度与波动率动态调整仓位。"}</p><button onClick={()=>setSelected(item)}>{active.some((entry) => entry.name === item.name) ? "已跟单 · 查看" : "查看策略"}</button></article>)}</div>:records.length?<div className="copy-subscription-list"><header>{["策略", "交易对", "模式", "投入上限", "状态", "操作"].map((name)=><b key={name}>{name}</b>)}</header>{records.map((item)=><div key={item.id}><span><strong>{item.name}</strong><small>{item.createdAt}</small></span><b>{item.symbol}</b><span>{item.mode}</span><span>{item.amount} USDT</span><em className={item.status === "运行中" ? "green" : item.status === "已暂停" ? "amber" : ""}>{item.status}</em><span>{tab === "我的跟单" ? <><button onClick={()=>patchSubscription(item.id,{status:item.status === "运行中" ? "已暂停" : "运行中"})}>{item.status === "运行中" ? "暂停" : "恢复"}</button><button className="danger" onClick={()=>{patchSubscription(item.id,{status:"已终止",stoppedAt:"刚刚"});say(`${venue} 模拟跟单已终止并归档`)}}>结束</button></> : <button onClick={()=>{setSelected(strategies.find((strategy)=>strategy.name===item.name) || strategies[0]);setTab("策略广场")}}>重新跟单</button>}</span></div>)}</div>:<div className="terminal-empty"><I.UsersThree/><b>{tab}暂无记录</b><small>{tab === "我的跟单" ? "前往策略广场选择策略并配置风险参数" : "结束的跟单会归档到这里"}</small><button onClick={()=>setTab("策略广场")}>前往策略广场</button></div>}{selected&&<aside className="copy-follow-sheet"><header><div><small>{selected.author}</small><h3>{selected.name}</h3></div><button aria-label="关闭跟单设置" onClick={()=>setSelected(null)}><I.X/></button></header><div className="copy-follow-stats"><span><small>近30日收益</small><b>{selected.profit}</b></span><span><small>胜率</small><b>{selected.win}</b></span><span><small>风险</small><b>{selected.risk}</b></span></div><label>跟单模式<select value={mode} onChange={(event)=>setMode(event.target.value)}><option>定额跟单</option><option>定比跟单</option></select></label><label>投入上限<input value={amount} onChange={(event)=>setAmount(event.target.value)} inputMode="decimal"/><span>USDT</span></label><label>跟单止损<input value={stopLoss} onChange={(event)=>setStopLoss(event.target.value)} inputMode="decimal"/><span>USDT</span></label><p>{venue === "DEX" ? "只读取公开链上仓位并生成本地模拟订阅，不连接钱包，不发送链上交易。" : "只生成本地模拟订阅，不绑定账户，不发送真实跟单委托。"}</p><footer><button onClick={()=>openOverlay("copyTrade",`跟单 ${selected.name} 风险说明`,{description:"跟单收益不代表未来表现；请设置可承受的投入与最大亏损。"})}>风险说明</button><button className="primary" onClick={startFollowing}>{active.some((item)=>item.name===selected.name)?"已在跟单":"开始模拟跟单"}</button></footer></aside>}</div>;
}

function AiAnalysisPanel({ symbol, openOverlay, say }) {
  const [tab,setTab]=useState("综合解读"),[question,setQuestion]=useState(""),[generated,setGenerated]=useState(false);
  return <div className="ai-analysis-terminal"><header><div>{["综合解读","趋势分析","主力订单","风险事件"].map(x=><button className={tab===x?"on":""} key={x} onClick={()=>setTab(x)}>{x}</button>)}</div><button onClick={()=>{setGenerated(true);say("AI分析已刷新")}}>刷新解读</button></header><section><article className="ai-score"><div><I.Sparkle/><span><b>{symbol}/USDT</b><small>AI行情评分</small></span></div><strong>62</strong><em>中性偏多</em></article><article className="ai-report"><h3>{tab}</h3>{generated?<><p>短线价格仍处于下降通道末端，65,553 一线出现承接。主力挂买量高于挂卖量，但主动成交仍偏空，反转尚需放量确认。</p><ul><li>关键支撑：65,553 / 64,820</li><li>关键阻力：66,120 / 66,956</li><li>风险：临近高波动时段，避免追涨杀跌</li></ul></>:<div className="report-placeholder"><I.MagicWand/><b>点击“刷新解读”生成当前行情报告</b></div>}</article><aside><h3>数据依据</h3>{[["趋势","MA20 下穿 MA60"],["主力","挂单差 +$12.4M"],["情绪","恐惧贪婪 40"],["合约","资金费率 0.0081%"]].map(x=><p key={x[0]}><span>{x[0]}</span><b>{x[1]}</b></p>)}</aside></section><footer><input value={question} onChange={e=>setQuestion(e.target.value)} placeholder="继续追问，例如：现在适合分批建仓吗？"/><button onClick={()=>question?openOverlay("aiChart","AI行情问答",{description:`${question}：建议等待66,120突破确认，并设置明确止损。`}):say("请输入问题")}>提问</button></footer></div>;
}

export function StrategyProductWorkbench({ category, say, openOverlay, authorizedAccounts = [] }) {
  const [symbol, setSymbol] = useState("BTC");
  const authorized = authorizedAccounts.length > 0;
  let panel = null;
  if (category === 2) panel = <DcaPanel symbol={symbol} openOverlay={openOverlay} say={say}/>;
  else if (category === 3) panel = <GridPanel symbol={symbol} authorized={authorized} openOverlay={openOverlay} say={say}/>;
  else if (category === 4) panel = <IndicatorPanel symbol={symbol} setSymbol={setSymbol} say={say}/>;
  else if (category === 5) panel = <CopyPanel openOverlay={openOverlay} say={say} venue="CEX"/>;
  else if (category === 6) panel = <CopyPanel openOverlay={openOverlay} say={say} venue="DEX"/>;
  return <div className="strategy-product-workbench"><header><label>策略标的<select aria-label="策略工作台交易对" value={symbol} onChange={(event)=>setSymbol(event.target.value)}><option>BTC</option><option>ETH</option><option>SOL</option><option>PEPE</option></select></label><span>{authorized ? "已关联本地演示账户" : "未连接账户 · 所有运行均为本地模拟"}</span></header>{panel}</div>;
}

export function MarketWorkbench({ active, setActive, symbol, setSymbol, say, openOverlay, authorizedAccounts }) {
  const [viewMode, setViewMode] = useState("normal");
  const tabs=["委单区","自定义指标/回测/实盘","AI网格","现货DCA","合约DCA","组合下单","跟单面板","AI分析","交易历史"];
  const authorized=authorizedAccounts.length>0;
  let panel;
  if(active==="委单区") panel=<OrdersPanel symbol={symbol} authorized={authorized} openOverlay={openOverlay} say={say}/>;
  else if(active==="自定义指标/回测/实盘") panel=<IndicatorPanel symbol={symbol} setSymbol={setSymbol} say={say}/>;
  else if(active==="AI网格") panel=<GridPanel symbol={symbol} authorized={authorized} openOverlay={openOverlay} say={say}/>;
  else if(active==="现货DCA") panel=<DcaPanel symbol={symbol} openOverlay={openOverlay} say={say}/>;
  else if(active==="合约DCA") panel=<FuturesDcaPanel symbol={symbol} openOverlay={openOverlay} say={say}/>;
  else if(active==="组合下单") panel=<BasketPanel openOverlay={openOverlay} say={say}/>;
  else if(active==="跟单面板") panel=<CopyPanel openOverlay={openOverlay} say={say}/>;
  else if(active==="AI分析") panel=<AiAnalysisPanel symbol={symbol} openOverlay={openOverlay} say={say}/>;
  else panel=<TradeHistoryPanel symbol={symbol} say={say}/>;
  return <div className={`bottom-work market-workbench ${viewMode}`}><nav>{tabs.map(x=><button className={active===x?"on":""} key={x} onClick={()=>{setActive(x);setViewMode("normal")}}>{x}</button>)}<span/><button aria-label="收起工作台" onClick={()=>setViewMode(viewMode==="collapsed"?"normal":"collapsed")}><I.Minus/></button><button aria-label="展开工作台" onClick={()=>setViewMode(viewMode==="expanded"?"normal":"expanded")}><I.ArrowsOutSimple/></button></nav>{viewMode!=="collapsed"&&panel}</div>;
}

export function ChartToolPopover({ tool, close, studies, setStudies, say, openOverlay, symbol, replayOpen = false, replayConfig, onStartReplay, onFeature, onReplayOption }) {
  if(!tool) return null;
  const groups={
    指标:["MA","EMA","BOLL","Volume","持仓量(OI)","MACD","RSI","KDJ","资金费率","主力大单"],
    高级:["指标胜率","信号预警","筹码分布","大额成交","主力挂单统计"],
    多窗:["单窗","双窗","四窗","六窗","九窗"],
    复盘:["开始K线复盘","选择起始时间",`复盘速度 x${replayConfig?.speed || 1}`,"隐藏未来K线"],
    显示:["价格线","倒计时","买卖信号","委托线","持仓成本线","网格线"],
  };
  const items=groups[tool]||[];
  const toggle=(item)=>setStudies(studies.includes(item)?studies.filter((value)=>value!==item):[...studies,item]);
  const choose=(item)=>{
    if(tool==="复盘"&&item==="开始K线复盘") return onStartReplay?.();
    if(tool==="复盘") return onReplayOption?.(item);
    if(tool==="高级"&&item==="信号预警") {
      close();
      return openOverlay("alertCenter","信号预警",{initialTab:"信号",symbol:`${symbol || "BTC"}/USDT`});
    }
    if(tool==="高级") { close(); return onFeature?.(item); }
    if(tool==="指标"||tool==="显示") return toggle(item);
    if(tool==="多窗"){
      setStudies([...studies.filter((value)=>!groups.多窗.includes(value)),item]);
      return say(`图表布局已切换为${item}`);
    }
    if(item.includes("时间")) return openOverlay("dateLocator","选择复盘起始时间");
    toggle(item);
    say(`${item}${studies.includes(item)?"已关闭":"已开启"}`);
  };
  const itemActive=(x)=>x==="开始K线复盘"?replayOpen:x==="隐藏未来K线"?Boolean(replayConfig?.hideFuture):studies?.includes(x);
  return <div className="chart-tool-popover"><header><b>{tool}</b><button onClick={close}><I.X/></button></header>{items.map(x=><button className={itemActive(x)?"on":""} key={x} onClick={()=>choose(x)}><span>{x}</span>{itemActive(x)?<I.Check/>:<I.CaretRight/>}</button>)}</div>;
}

export function KlineReplayPanel({ symbol, quote, period, onChooseStart, onClose, say, initialSpeed = 1, hideFuture = true, startLabel = "最近90天" }) {
  const [playing,setPlaying]=useState(false),[speed,setSpeed]=useState(initialSpeed),[step,setStep]=useState(18),[mode,setMode]=useState("简洁模式"),[position,setPosition]=useState(0),[trades,setTrades]=useState([]),[summary,setSummary]=useState(false);
  const base=Number(quote?.price||65553), price=base*(1+(step-18)*0.0007), pnl=position?(price-base)*position:0;
  useEffect(()=>{if(!playing)return;const timer=setInterval(()=>setStep(value=>value>=100?100:value+1),Math.max(180,900/speed));return()=>clearInterval(timer)},[playing,speed]);
  useEffect(()=>{if(step>=100)setPlaying(false)},[step]);
  const trade=(side)=>{const quantity=side==="买入"?0.01:-0.01;setPosition(value=>Number((value+quantity).toFixed(4)));setTrades(value=>[...value,{id:Date.now(),side,price}]);say(`复盘${side} 0.01 ${symbol} · 本地模拟`) };
  const reset=()=>{setPlaying(false);setStep(18);setPosition(0);setTrades([]);say("已重新选择复盘起点")};
  return <div className="kline-replay" role="region" aria-label="K线复盘训练">
    <header><div><I.ClockCounterClockwise/><span><b>K线复盘</b><small>{symbol}/USDT · {period} · {startLabel.replace("T"," ")} · {hideFuture?"未来K线已隐藏":"未来K线可见"}</small></span></div><button onClick={()=>setSummary(true)}>结束训练</button><button aria-label="关闭K线复盘" onClick={onClose}><I.X/></button></header>
    <section className="replay-stats"><span><small>复盘进度</small><b>{step}%</b></span><span><small>模拟持仓</small><b>{position.toFixed(2)} {symbol}</b></span><span><small>浮动盈亏</small><b className={pnl>=0?"green":"red"}>{pnl>=0?"+":""}{pnl.toFixed(2)} USDT</b></span><span><small>交易次数</small><b>{trades.length}</b></span></section>
    <div className="replay-progress"><i style={{width:`${step}%`}}/></div>
    <footer><button onClick={onChooseStart}><I.CalendarBlank/>选择起始时间</button><button onClick={reset}><I.ArrowCounterClockwise/>重新选择起点</button><button onClick={()=>setStep(value=>Math.min(100,value+1))}><I.SkipForward/>单步</button><button className="replay-play" onClick={()=>setPlaying(!playing)}>{playing?<I.Pause/>:<I.Play/>}{playing?"暂停":"播放"}</button>{[1,2,4].map(value=><button className={speed===value?"on":""} key={value} onClick={()=>setSpeed(value)}>{value}x</button>)}<span/>{["简洁模式","持仓模式"].map(value=><button className={mode===value?"on":""} key={value} onClick={()=>setMode(value)}>{value}</button>)}<button className="replay-buy" onClick={()=>trade("买入")}>模拟买入</button><button className="replay-sell" onClick={()=>trade("卖出")}>模拟卖出</button></footer>
    {summary&&<div className="replay-summary"><article><header><I.ChartLineUp/><div><b>复盘训练结果</b><small>{symbol}/USDT · {period}</small></div></header><strong className={pnl>=0?"green":"red"}>{pnl>=0?"+":""}{pnl.toFixed(2)} USDT</strong><p><span>完成进度</span><b>{step}%</b></p><p><span>交易次数</span><b>{trades.length}</b></p><p><span>推荐指标胜率</span><b>68.4%</b></p><footer><button onClick={()=>setSummary(false)}>继续复盘</button><button onClick={onClose}>结束并退出</button></footer><small>训练结果仅保存在当前页面，不会启用实盘交易。</small></article></div>}
  </div>;
}
