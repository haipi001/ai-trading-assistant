import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import * as I from "@phosphor-icons/react";
import "./styles.css";
import "./channels.css";
import "./chart-drawings.css";
import "./quick-trade.css";
import "./strategy-filters.css";
import "./professional-sidebar.css";
import "./brand.css";
import "./backend-status.css";
import { ChartToolPopover, KlineReplayPanel, MarketWorkbench, StrategyProductWorkbench } from "./market-workbench.jsx";
import { FEATURE_OVERLAY_TYPES, FeatureOverlayPanel } from "./feature-overlays.jsx";
import { TradingChartGrid } from "./trading-chart.jsx";
import { CapitalTracker, FloatingAIChat, StrategyNotebook } from "./strategy-intelligence.jsx";
import { loadBackendCandles } from "./market-api.js";
import { getBackendStatus, runBackendQuery } from "./backend-api.js";
import { CustomPeriodCenter, IndicatorCenter, MultiWindowCenter } from "./chart-command-centers.jsx";

const NAV = [
  ["home", "首页", I.House],
  ["market", "行情", I.ChartBar],
  ["flash", "快讯", I.Lightning],
  ["news", "要闻", I.Article],
  ["strategy", "策略", I.Robot],
  ["chain", "链上", I.BezierCurve],
  ["assets", "资产", I.Wallet],
  ["auth", "授权", I.Key],
  ["data", "数据", I.Database],
  ["more", "更多", I.SquaresFour],
];
const META = {
  home: {
    title: "首页",
    tabs: [
      "AI智搜",
      "市场概览",
      "条件选币",
      "热门榜单",
      "排行",
      "功能指南",
      "云图",
      "合约雷达",
    ],
  },
  market: {
    title: "BTC / USDT",
    tabs: ["图表", "深度", "资金流", "合约数据", "自选"],
  },
  flash: {
    title: "快讯",
    tabs: [
      "精选",
      "直播",
      "巨鲸",
      "主力",
      "推特",
      "市场",
      "特朗普",
      "上新",
      "链上",
      "ETF",
      "宏观",
      "币股",
    ],
  },
  news: {
    title: "要闻",
    tabs: [
      "精选",
      "活动FUN放",
      "分析",
      "直播回顾",
      "币股",
      "产品教程",
      "科普",
      "长推",
      "媒体报道",
      "Web3.0",
      "行业报告",
      "AI号",
    ],
  },
  strategy: {
    title: "策略",
    tabs: ["自动赚币", "套利机会", "专业套利", "我的套利"],
  },
  chain: { title: "链上", tabs: ["聪明钱", "Hyperliquid", "Polymarket"] },
  assets: {
    title: "资产",
    tabs: ["总览", "币种分布", "API账号分布", "盈亏日历", "流水", "风控"],
  },
  auth: { title: "API授权", tabs: ["已授权账户", "添加授权", "安全说明"] },
  data: { title: "数据", tabs: ["加密货币储备", "Hyperliquid"] },
  more: { title: "更多", tabs: ["钱包", "宏观", "自定义导航", "帮助中心"] },
};
const HOME_TABS = {
  web3: META.home.tabs,
  stocks: ["AI智搜", "市场概览", "条件选股", "热门股票", "涨幅榜", "财经日历", "板块热力", "财报雷达"],
};
const STRATEGY_CATEGORY_LABELS = ["我的策略", "智能套利", "全币种 DCA", "AI网格", "指标策略", "跟单策略 · CEX", "跟单策略 · DEX", "主力追踪", "游资追踪"];
const coins = [
  ["XAU", "4,067.95", "+0.19%", "美股合约"],
  ["XAG", "58.67", "+1.24%", "美股合约"],
  ["TSLA", "312.25", "+1.11%", "美股合约"],
  ["INTC", "92.55", "+2.81%", "美股合约"],
  ["HOOD", "87.81", "+1.94%", "美股合约"],
  ["MSTR", "93.36", "+0.45%", "美股合约"],
  ["BTC", "64,020.04", "+1.44%"],
  ["ETH", "3,172.22", "+0.55%"],
  ["SOL", "148.32", "+0.29%"],
  ["HYPE", "42.06", "-2.20%"],
  ["XRP", "0.55", "0.00%"],
  ["ADA", "0.74", "+3.30%"],
  ["AVAX", "28.16", "+0.92%"],
];
const stocks = [
  ["AAPL", "229.35", "+1.26%", "NASDAQ", "Apple Inc."],
  ["NVDA", "181.42", "+2.18%", "NASDAQ", "NVIDIA"],
  ["TSLA", "312.25", "+1.11%", "NASDAQ", "Tesla"],
  ["MSFT", "527.75", "+0.62%", "NASDAQ", "Microsoft"],
  ["AMZN", "231.44", "+1.31%", "NASDAQ", "Amazon"],
  ["META", "782.16", "-0.48%", "NASDAQ", "Meta Platforms"],
  ["GOOGL", "213.19", "+0.83%", "NASDAQ", "Alphabet"],
  ["PLTR", "124.11", "+0.74%", "NYSE", "Palantir"],
];
const MARKET_QUOTES = {
  XAU: { price: 4067.95, change: "+0.19%", open: 4059.28, high: 4082.14, low: 4041.62, turnover: "$1.52B", inflow: "+$8.4M", marketCap: "$18.4T", volatility: "1.26%", decimals: 2 },
  XAG: { price: 58.67, change: "+1.24%", open: 57.92, high: 59.14, low: 57.61, turnover: "$76.74M", inflow: "+$2.1M", marketCap: "$1.8T", volatility: "2.64%", decimals: 2 },
  TSLA: { price: 312.25, change: "+1.11%", open: 308.84, high: 315.61, low: 306.18, turnover: "$5.61B", inflow: "+$18.2M", marketCap: "$998B", volatility: "3.12%", decimals: 2 },
  INTC: { price: 92.55, change: "+2.81%", open: 90.02, high: 93.14, low: 89.76, turnover: "$13.30M", inflow: "+$4.7M", marketCap: "$402B", volatility: "3.75%", decimals: 2 },
  HOOD: { price: 87.81, change: "+1.94%", open: 86.14, high: 88.52, low: 85.61, turnover: "$11.70M", inflow: "+$3.9M", marketCap: "$78B", volatility: "4.12%", decimals: 2 },
  MSTR: { price: 93.36, change: "+0.45%", open: 92.94, high: 95.18, low: 91.82, turnover: "$58.30M", inflow: "+$5.2M", marketCap: "$28B", volatility: "4.88%", decimals: 2 },
  BTC: { price: 64020.04, change: "+0.14%", open: 64011, high: 64032.6, low: 63886.65, turnover: "$2.18B", inflow: "-$0.70M", marketCap: "$1.28T", volatility: "2.41%", decimals: 2 },
  ETH: { price: 3172.22, change: "+0.55%", open: 3154.18, high: 3198.62, low: 3128.44, turnover: "$1.14B", inflow: "+$3.20M", marketCap: "$381.2B", volatility: "3.08%", decimals: 2 },
  SOL: { price: 148.32, change: "+0.29%", open: 147.86, high: 150.41, low: 145.72, turnover: "$684.6M", inflow: "+$1.84M", marketCap: "$72.4B", volatility: "4.12%", decimals: 2 },
  HYPE: { price: 42.06, change: "-2.20%", open: 43.11, high: 43.48, low: 41.62, turnover: "$318.2M", inflow: "-$2.16M", marketCap: "$14.1B", volatility: "5.24%", decimals: 2 },
  XRP: { price: 0.55, change: "0.00%", open: 0.55, high: 0.57, low: 0.54, turnover: "$892.4M", inflow: "+$0.42M", marketCap: "$31.8B", volatility: "2.86%", decimals: 4 },
  ADA: { price: 0.74, change: "+3.30%", open: 0.7164, high: 0.7528, low: 0.7082, turnover: "$426.8M", inflow: "+$4.62M", marketCap: "$26.2B", volatility: "4.86%", decimals: 4 },
  AVAX: { price: 28.16, change: "+0.92%", open: 27.88, high: 28.64, low: 27.42, turnover: "$214.7M", inflow: "+$0.96M", marketCap: "$11.7B", volatility: "3.72%", decimals: 2 },
  AAPL: { price: 229.35, change: "+1.26%", open: 226.48, high: 230.11, low: 225.92, turnover: "$12.6B", inflow: "+$184M", marketCap: "$3.42T", volatility: "1.84%", decimals: 2 },
  NVDA: { price: 181.42, change: "+2.18%", open: 177.55, high: 183.08, low: 176.91, turnover: "$28.4B", inflow: "+$426M", marketCap: "$4.43T", volatility: "3.16%", decimals: 2 },
  MSFT: { price: 527.75, change: "+0.62%", open: 524.49, high: 529.08, low: 522.84, turnover: "$9.7B", inflow: "+$96M", marketCap: "$3.92T", volatility: "1.32%", decimals: 2 },
  AMZN: { price: 231.44, change: "+1.31%", open: 228.45, high: 232.12, low: 227.83, turnover: "$8.3B", inflow: "+$112M", marketCap: "$2.46T", volatility: "2.04%", decimals: 2 },
  META: { price: 782.16, change: "-0.48%", open: 786.02, high: 790.34, low: 776.18, turnover: "$7.1B", inflow: "-$52M", marketCap: "$1.97T", volatility: "2.21%", decimals: 2 },
  GOOGL: { price: 213.19, change: "+0.83%", open: 211.43, high: 214.02, low: 210.88, turnover: "$6.8B", inflow: "+$74M", marketCap: "$2.59T", volatility: "1.56%", decimals: 2 },
  PLTR: { price: 124.11, change: "+0.74%", open: 123.20, high: 125.46, low: 122.61, turnover: "$4.1B", inflow: "+$48M", marketCap: "$294B", volatility: "3.74%", decimals: 2 },
};
const quoteFor = (symbol) => MARKET_QUOTES[symbol] || MARKET_QUOTES.BTC;
const formatPrice = (value, decimals = 2) => Number(value).toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
const news = [
  ["18:08", "美联储官员讲话偏鹰，美元指数短线走高", "宏观", "中性"],
  ["17:53", "BTC 交易所净流入转负，抛压暂缓", "资金流", "利好"],
  ["17:31", "巨鲸 0x71…8A 增持 1,840 ETH", "链上", "观察"],
  ["17:20", "BTC 期权隐含波动率升至近七日高位", "衍生品", "风险"],
];

function readLastWorkspace() {
  const fallback = { page: "home", tab: "AI智搜" };
  try {
    const saved = JSON.parse(localStorage.getItem("ai-trading-assistant-workspace") || "null");
    if (saved?.page === "home" && saved?.tab === "Ace智搜") return fallback;
    if (saved && META[saved.page]?.tabs.includes(saved.tab)) return saved;
  } catch {
    return fallback;
  }
  return fallback;
}

function useStoredState(key, initialValue) {
  const [state, setState] = useState(() => {
    try {
      const saved = localStorage.getItem(key);
      return saved ? JSON.parse(saved) : initialValue;
    } catch {
      return initialValue;
    }
  });
  useEffect(() => {
    localStorage.setItem(key, JSON.stringify(state));
    window.dispatchEvent(new CustomEvent("ai-trading-assistant-local-state", { detail: { key, value: state } }));
  }, [key, state]);
  return [state, setState];
}

function App() {
  const initialWorkspace = useMemo(readLastWorkspace, []);
  const canvasRef = useRef(null);
  const [page, setPage] = useState(initialWorkspace.page),
    [tab, setTab] = useState(initialWorkspace.tab),
    [drawer, setDrawer] = useState(null);
  const [strategyCategory, setStrategyCategory] = useState(1);
  const [sidebarMode, setSidebarMode] = useStoredState(
    "ai-trading-assistant-sidebar-mode",
    "professional",
  );
  const [marketSideTab, setMarketSideTab] = useStoredState("ai-trading-assistant-market-side-tab", "depth");
  const [marketSideOpen, setMarketSideOpen] = useStoredState("ai-trading-assistant-market-side-open", true);
  const [marketOrderOpen, setMarketOrderOpen] = useStoredState("ai-trading-assistant-market-order-open", false);
  const [watch, setWatch] = useStoredState("ai-trading-assistant-watch", [
      "BTC",
      "ETH",
      "SOL",
    ]),
    [query, setQuery] = useState(""),
    [toast, setToast] = useState("");
  const [prefs, setPrefs] = useStoredState("ai-trading-assistant-prefs", {
    currency: "USD",
    desktop: true,
    sound: false,
    auto: true,
    redUp: false,
    showDepthBars: true,
  });
  const [quickTradePrefill, setQuickTradePrefill] = useState(null);
  const [savedStrategies, setSavedStrategies] = useStoredState(
    "ai-trading-assistant-strategies",
    [],
  );
  const [assetGroups, setAssetGroups] = useStoredState("ai-trading-assistant-groups", []);
  const [authorizedAccounts, setAuthorizedAccounts] = useStoredState(
    "ai-trading-assistant-accounts",
    [],
  );
  const [followedTraders, setFollowedTraders] = useStoredState(
    "ai-trading-assistant-followed-traders",
    [],
  );
  const [chartTraders, setChartTraders] = useStoredState(
    "ai-trading-assistant-chart-traders",
    [],
  );
  const [chartSnapshots, setChartSnapshots] = useStoredState(
    "ai-trading-assistant-chart-snapshots",
    [],
  );
  const [marketSymbol, setMarketSymbol] = useStoredState("ai-trading-assistant-market-symbol", "BTC");
  const [marketMode, setMarketMode] = useStoredState("ai-trading-assistant-market-mode", "web3");
  const [marketCommand, setMarketCommand] = useState(null);
  const [overlay, setOverlay] = useState(null);
  const [aiFloatOpen, setAiFloatOpen] = useState(false);
  const [backendStatus, setBackendStatus] = useState({ connected: false, status: "checking" });
  useEffect(() => {
    let active = true;
    const check = () => getBackendStatus().then((result) => active && setBackendStatus(result));
    check();
    const timer = setInterval(check, 30000);
    return () => { active = false; clearInterval(timer); };
  }, []);
  useEffect(() => {
    localStorage.setItem("ai-trading-assistant-workspace", JSON.stringify({ page, tab }));
    if (canvasRef.current) canvasRef.current.scrollTop = 0;
  }, [page, tab]);
  useEffect(() => {
    const handlePrefill = (event) => {
      setQuickTradePrefill(event.detail);
      setMarketSideOpen(true);
      setMarketOrderOpen(true);
    };
    window.addEventListener("ai-trading-assistant-prefill-order", handlePrefill);
    return () => window.removeEventListener("ai-trading-assistant-prefill-order", handlePrefill);
  }, []);
  const go = (p) => {
    setPage(p);
    setTab(META[p].tabs[0]);
    if (p === "strategy") setStrategyCategory(1);
  };
  const say = (s) => {
    setToast(s);
    setTimeout(() => setToast(""), 1600);
  };
  const openOverlay = (type, title, payload = {}) =>
    setOverlay({ type, title, ...payload });
  const ctx = {
    page,
    tab,
    go,
    watch,
    setWatch,
    say,
    openOverlay,
    savedStrategies,
    setSavedStrategies,
    assetGroups,
    setAssetGroups,
    authorizedAccounts,
    setAuthorizedAccounts,
    strategyCategory,
    setStrategyCategory,
    followedTraders,
    setFollowedTraders,
    chartTraders,
    setChartTraders,
    chartSnapshots,
    setChartSnapshots,
    marketCommand,
    marketSymbol,
    setMarketSymbol,
    marketMode,
    setMarketMode,
    prefs,
    setPrefs,
    marketSideTab,
    setMarketSideTab,
    marketSideOpen,
    setMarketSideOpen,
    marketOrderOpen,
    setMarketOrderOpen,
    sidebarMode,
    quickTradePrefill,
  };
  return (
    <div className={`terminal ${prefs.redUp ? "red-up" : "green-up"}`}>
      <GlobalTop
        query={query}
        setQuery={setQuery}
        go={go}
        openOverlay={openOverlay}
        currency={prefs.currency}
        openAI={() => setAiFloatOpen(true)}
        backendStatus={backendStatus}
      />
      <PrimaryNav page={page} go={go} openOverlay={openOverlay} />
      <div className={`pagebar ${page === "market" ? `with-symbol ${marketSideOpen ? "market-side-expanded" : "market-side-collapsed"}` : "channels-only"}`}>
        <div>
          {(page === "home" || page === "market") && <div className={`market-mode-switch ${marketMode}`} role="group" aria-label="市场类型切换"><button className={marketMode === "web3" ? "on" : ""} onClick={() => { setMarketMode("web3"); setMarketSymbol("BTC"); if (page === "home" && !HOME_TABS.web3.includes(tab)) setTab("AI智搜"); }}>WEB3</button><button className={marketMode === "stocks" ? "on" : ""} onClick={() => { setMarketMode("stocks"); setMarketSymbol("AAPL"); if (page === "home" && !HOME_TABS.stocks.includes(tab)) setTab("AI智搜"); }}>股票</button></div>}
          {page === "strategy" && strategyCategory !== 1 && <small>{STRATEGY_CATEGORY_LABELS[strategyCategory]}</small>}
          {(page === "strategy" && strategyCategory !== 1 ? [] : page === "home" ? HOME_TABS[marketMode] : META[page].tabs).map((x) => (
            <button
              key={x}
              className={tab === x ? "on" : ""}
              onClick={() => { setTab(x); if (page === "strategy") setStrategyCategory(1); }}
            >
              {x}
            </button>
          ))}
        </div>
        <PageActions
          page={page}
          say={say}
          openOverlay={openOverlay}
          chartSnapshotCount={chartSnapshots.length}
          onMarketAction={(type) => setMarketCommand({ type, id: Date.now() })}
        />
      </div>
      <main className={`canvas ${page === "market" && marketSideOpen ? "market-drawer-open" : ""}`} ref={canvasRef}>
        {page === "home" ? (
          <Home {...ctx} />
        ) : page === "market" ? (
          <Market {...ctx} />
        ) : page === "news" ? (
          <News {...ctx} />
        ) : page === "flash" ? (
          <FlashPage {...ctx} />
        ) : page === "strategy" ? (
          <Strategy {...ctx} />
        ) : page === "chain" ? (
          <ChainPage {...ctx} />
        ) : page === "assets" ? (
          <Assets {...ctx} />
        ) : page === "auth" ? (
          <Auth {...ctx} />
        ) : page === "data" ? (
          <DataPage {...ctx} />
        ) : page === "more" ? (
          <MorePage {...ctx} />
        ) : (
          <ModulePage {...ctx} />
        )}
      </main>
      <RightRail
        page={page}
        drawer={drawer}
        setDrawer={setDrawer}
        openOverlay={openOverlay}
        sidebarMode={sidebarMode}
        setSidebarMode={setSidebarMode}
        openAI={() => setAiFloatOpen(true)}
        say={say}
        marketSideTab={marketSideTab}
        setMarketSideTab={setMarketSideTab}
        marketSideOpen={marketSideOpen}
        setMarketSideOpen={setMarketSideOpen}
        marketOrderOpen={marketOrderOpen}
        setMarketOrderOpen={setMarketOrderOpen}
      />
      {drawer && drawer !== "sidebarLayout" && page !== "market" && (
        <UtilityDrawer
          type={drawer}
          close={() => setDrawer(null)}
          go={go}
          say={say}
          watch={watch}
          setWatch={setWatch}
          marketSymbol={marketSymbol}
          prefill={quickTradePrefill}
          openOverlay={openOverlay}
          openDrawer={setDrawer}
          authorizedAccounts={authorizedAccounts}
          sidebarMode={sidebarMode}
        />
      )}
      {overlay && (
        <ActionOverlay
          model={overlay}
          close={() => setOverlay(null)}
          say={say}
          go={go}
          prefs={prefs}
          setPrefs={setPrefs}
          watch={watch}
          setWatch={setWatch}
          savedStrategies={savedStrategies}
          setSavedStrategies={setSavedStrategies}
          assetGroups={assetGroups}
          setAssetGroups={setAssetGroups}
          authorizedAccounts={authorizedAccounts}
          setAuthorizedAccounts={setAuthorizedAccounts}
        />
      )}
      <FloatingAIChat open={aiFloatOpen} onClose={() => setAiFloatOpen(false)} page={page} symbol={marketSymbol} say={say} />
      <Ticker symbol={marketSymbol} />
      {toast && <div className="toast">{toast}</div>}
    </div>
  );
}

function GlobalTop({ query, setQuery, go, openOverlay, currency, openAI, backendStatus }) {
  const searchRef = useRef(null);
  const suggestions = ["AI建议：BTC 4小时波动收窄，等待突破确认", "AI建议：主力净流入增强，留意 64,200 压力位", "AI建议：3 篇交易笔记待补全失效条件"];
  const [suggestionIndex, setSuggestionIndex] = useState(0);
  useEffect(() => {
    const focusSearch = (event) => {
      const target = event.target;
      const isTyping = ["INPUT", "TEXTAREA", "SELECT"].includes(target?.tagName);
      if (event.key === "/" && !isTyping) {
        event.preventDefault();
        searchRef.current?.focus();
      }
      if (event.key === "Escape" && target === searchRef.current) {
        setQuery("");
        searchRef.current?.blur();
      }
    };
    window.addEventListener("keydown", focusSearch);
    return () => window.removeEventListener("keydown", focusSearch);
  }, [setQuery]);
  useEffect(() => { const timer = setInterval(() => setSuggestionIndex((index) => (index + 1) % suggestions.length), 6500); return () => clearInterval(timer); }, []);
  return (
    <header className="global-top">
      <div className="traffic">
        <i />
        <i />
        <i />
      </div>
      <I.Browsers className="window-mark" />
      <div className="pulse" />
      <strong className="service-name">AI交易助手</strong>
      <button className={`backend-health ${backendStatus.connected ? "connected" : backendStatus.status}`} title={backendStatus.baseUrl || "正在检查后端"} onClick={()=>openOverlay("tool","后端连接状态",{description:backendStatus.connected?`API 已连接 · ${backendStatus.status}`:`API 未连接 · ${backendStatus.error || "正在检查"}`})}><i/>{backendStatus.connected ? "API 已连接" : backendStatus.status === "checking" ? "检查 API" : "本地模式"}</button>
      <button className="ai-suggestion" aria-label="打开AI建议" onClick={openAI}><I.Sparkle/><span>{suggestions[suggestionIndex]}</span></button>
      <div className="command">
        <I.MagnifyingGlass />
        <input
          ref={searchRef}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key !== "Enter") return;
            if (!query.trim()) return openOverlay("searchResults", "全局搜索", { query: "BTC/USDT" });
            openOverlay("searchResults", `搜索：${query.trim()}`, { query: query.trim() });
          }}
          placeholder="OKX BTC/USDT 永续"
        />
        <kbd>/</kbd>
      </div>
      <button
        aria-label="通知"
        onClick={() => openOverlay("notifications", "通知中心")}
      >
        <I.Bell />
      </button>
      <button
        className="ai-launch"
        aria-label="打开AI交易助手"
        onClick={openAI}
      >
        <I.ChatTeardropDots weight="fill" />
      </button>
      <button
        className="currency"
        onClick={() => openOverlay("currency", "计价单位")}
      >
        {currency} <I.CaretDown />
      </button>
      <button
        className="profile"
        onClick={() => openOverlay("profile", "账户中心")}
      >
        <I.UserCircle />
        <span>60716203</span>
      </button>
    </header>
  );
}
function PrimaryNav({ page, go, openOverlay }) {
  return (
    <aside className="primary-nav">
      {NAV.map(([id, n, Icon]) => (
        <button
          key={id}
          className={page === id ? "on" : ""}
          onClick={() => go(id)}
          title={n}
        >
          <Icon weight={page === id ? "fill" : "regular"} />
          <span>{n}</span>
        </button>
      ))}
      <div />
      <button onClick={() => openOverlay("settings", "系统设置")}>
        <I.Gear />
        <span>设置</span>
      </button>
    </aside>
  );
}
function PageActions({ page, say, openOverlay, chartSnapshotCount = 0, onMarketAction = () => {} }) {
  const [audioOn, setAudioOn] = useState(false);
  const [readingMode, setReadingMode] = useState(false);
  useEffect(() => {
    document.documentElement.classList.toggle("news-reading-mode", page === "news" && readingMode);
    if (page !== "news") {
      setReadingMode(false);
      setAudioOn(false);
      window.speechSynthesis?.cancel();
    }
    return () => document.documentElement.classList.remove("news-reading-mode");
  }, [page, readingMode]);
  const toggleArticleAudio = () => {
    const next = !audioOn;
    setAudioOn(next);
    window.speechSynthesis?.cancel();
    if (next && "SpeechSynthesisUtterance" in window) {
      const utterance = new SpeechSynthesisUtterance("AI交易助手 要闻朗读。当前文章关注市场流动性、风险偏好与政策预期，投资需独立判断并控制风险。");
      utterance.lang = "zh-CN";
      utterance.onend = () => setAudioOn(false);
      window.speechSynthesis.speak(utterance);
    }
    say(next ? "开始朗读当前文章" : "已停止朗读");
  };
  return (
    <aside className="page-actions">
      {page === "market" && (
        <>
          <button
            className={chartSnapshotCount ? "on" : ""}
            onClick={() => onMarketAction("snapshot")}
          >
            <I.Camera />
            {chartSnapshotCount ? `快照 ${chartSnapshotCount}` : "快照"}
          </button>
          <button
            onClick={() => onMarketAction("saveLayout")}
          >
            <I.FloppyDisk />
            保存布局
          </button>
          <button className="solid" onClick={() => openOverlay("create", "新建图表布局")}>
            <I.Plus /> 新建
          </button>
        </>
      )}
      {page === "news" && (
        <>
          <button
            className={audioOn ? "on" : ""}
            title="听文章"
            onClick={toggleArticleAudio}
          >
            <I.SpeakerHigh />
          </button>
          <button
            className={readingMode ? "on" : ""}
            title="阅读模式"
            onClick={() => setReadingMode(!readingMode)}
          >
            <I.Columns />
          </button>
          <button className="solid" onClick={() => openOverlay("submit", "我要投稿")}>
            <I.NotePencil /> 我要投稿
          </button>
        </>
      )}
      {page === "strategy" && (
        <button onClick={() => openOverlay("help", "策略使用教程")}>
          <I.BookOpen /> 教程
        </button>
      )}
      {page === "auth" && (
        <button className="solid" onClick={() => openOverlay("apiAuth", "添加授权")}>
          <I.Plus /> 添加授权
        </button>
      )}
    </aside>
  );
}

function Home({ tab, go, say, openOverlay, marketMode }) {
  const [range, setRange] = useState("24H");
  const [heatScale, setHeatScale] = useState("x1");
  const [heatMode, setHeatMode] = useState({
    cap: "前100",
    type: "涨跌幅",
    area: "流通市值",
    group: "板块分组",
  });
  if (tab !== "云图")
    return (
      <HomeChannel tab={tab} go={go} say={say} openOverlay={openOverlay} marketMode={marketMode} />
    );
  return (
    <div className="ai-trading-assistant-home">
      <div className="heat-controls">
        <button
          onClick={() =>
            setHeatMode({
              ...heatMode,
              cap: heatMode.cap === "前100" ? "前50" : "前100",
            })
          }
        >
          市值：{heatMode.cap} <I.CaretDown />
        </button>
        <button
          onClick={() =>
            setHeatMode({
              ...heatMode,
              type: heatMode.type === "涨跌幅" ? "成交额" : "涨跌幅",
            })
          }
        >
          类型：{heatMode.type} <I.CaretDown />
        </button>
        <button
          onClick={() =>
            setHeatMode({
              ...heatMode,
              area: heatMode.area === "流通市值" ? "成交额" : "流通市值",
            })
          }
        >
          面积：{heatMode.area} <I.CaretDown />
        </button>
        <button
          onClick={() =>
            setHeatMode({
              ...heatMode,
              group: heatMode.group === "板块分组" ? "不分组" : "板块分组",
            })
          }
        >
          {heatMode.group} <I.CaretDown />
        </button>
        <span />
        {["5Min", "1H", "4H", "24H"].map((x) => (
          <button
            key={x}
            className={range === x ? "on" : ""}
            onClick={() => setRange(x)}
          >
            {x}
          </button>
        ))}
        <I.Question />
        <select
          value={heatScale}
          onChange={(e) => setHeatScale(e.target.value)}
          aria-label="云图缩放倍率"
        >
          <option>x1</option>
          <option>x2</option>
        </select>
        <div className="legend">
          <i>-3%</i>
          <i>-2%</i>
          <i>-1.2%</i>
          <i>0%</i>
          <i>1.2%</i>
          <i>2%</i>
          <i>3%</i>
        </div>
      </div>
      <div className="heatmap">
        <section className="heat-major">
          <header>
            a16z投资 <em>+1.46%</em>
          </header>
          <div className="major-grid">
            <Heat coin="BTC" value="+1.44%" cls="g3" open={openOverlay} />
            <Heat coin="ETH" value="+0.55%" cls="n" open={openOverlay} />
            <Heat coin="XRP" value="0.00%" cls="n" open={openOverlay} />
            <Heat coin="SUI" value="+0.05%" cls="n" open={openOverlay} />
            <Heat coin="ICP" value="+0.94%" cls="g1" open={openOverlay} />
            <Heat coin="WLD" value="-1.02%" cls="r1" open={openOverlay} />
          </div>
        </section>
        <section className="heat-public">
          <header>
            公链 <em>+0.62%</em>
          </header>
          <div className="public-grid">
            <Heat coin="ETH" value="+0.55%" cls="n" open={openOverlay} />
            <Heat coin="SOL" value="+0.29%" cls="n" open={openOverlay} />
            <Heat coin="TRX" value="+0.19%" cls="n" open={openOverlay} />
            <Heat coin="ADA" value="+3.30%" cls="g3" open={openOverlay} />
            <Heat coin="AVAX" value="+0.92%" cls="g1" open={openOverlay} />
            <Heat coin="NEAR" value="-1.04%" cls="r1" open={openOverlay} />
            <Heat coin="OKB" value="+1.53%" cls="g2" open={openOverlay} />
            <Heat coin="ICP" value="+0.94%" cls="g1" open={openOverlay} />
          </div>
        </section>
        <section className="heat-defi">
          <header>
            DeFi <em className="red">-0.16%</em>
          </header>
          <div className="defi-grid">
            <Heat coin="HYPE" value="-2.20%" cls="r2" open={openOverlay} />
            <Heat coin="USDS" value="-0.99%" cls="r1" open={openOverlay} />
            <Heat coin="DAI" value="-0.61%" cls="r1" open={openOverlay} />
            <Heat coin="LINK" value="+1.10%" cls="g1" open={openOverlay} />
            <Heat coin="UNI" value="+0.57%" cls="n" open={openOverlay} />
            <Heat coin="AAVE" value="-3.22%" cls="r3" open={openOverlay} />
            <Heat coin="JUP" value="+0.83%" cls="g1" open={openOverlay} />
          </div>
        </section>
        <aside className="heat-sectors">
          {[
            "LSD +0.22%",
            "Layer1 +0.11%",
            "币安 IEO -0.08%",
            "DePIN -0.10%",
            "RWA -0.12%",
            "跨链&侧链 -0.26%",
            "Layer2 -0.76%",
            "模块化",
            "钱包",
          ].map((x, i) => (
            <div key={x}>
              <b>{x}</b>
              <span className={i % 3 === 1 ? "mini-red" : "mini-green"}>
                {["STETH", "SUI", "INJ", "POL", "ARB", "RENDER"][i % 6]}
              </span>
              <span>{["LDO", "APT", "TAO", "AAVE", "DOT", "CRO"][i % 6]}</span>
            </div>
          ))}
        </aside>
      </div>
    </div>
  );
}
function Heat({ coin, value, cls, open }) {
  return (
    <button
      className={"heat " + cls}
      onClick={() =>
        open("coin", `${coin}/USDT`, {
          description: `${coin} 最新涨跌 ${value}，点击进入完整行情。`,
        })
      }
    >
      <b>{coin}</b>
      <span>{value}</span>
    </button>
  );
}
function HomeChannel({ tab, go, say, openOverlay, marketMode = "web3" }) {
  const [aceQuery, setAceQuery] = useState("");
  const [aceMode, setAceMode] = useState("快速回答");
  const [attachmentOpen, setAttachmentOpen] = useState(false);
  const [aceLoading, setAceLoading] = useState(false);
  const isStocks = marketMode === "stocks";
  const submitAIQuery = async () => {
    if (!aceQuery.trim()) return say("请输入问题");
    setAceLoading(true);
    try {
      const payload = await runBackendQuery(aceQuery.trim());
      const result = payload.result?.structured_result_json || payload.result || payload;
      openOverlay("aceResult", "AI 智搜 · 后端结果", { description: result.summary || result.answer || result.reason || JSON.stringify(result).slice(0, 320) });
    } catch {
      openOverlay("aceResult", "AI 智搜 · 本地回退", { description: `后端暂不可用，已保留问题：“${aceQuery.trim()}”。部署 API 后将自动切换为结构化研究结果。` });
    } finally { setAceLoading(false); }
  };
  if (tab === "AI智搜")
    return (
      <div className="ace-search">
        <div className="ace-logo">
          <I.Sparkle />
          <h1>寻找答案，从这里开始</h1>
        </div>
        <div className="ace-box">
          <textarea
            value={aceQuery}
            onChange={(e) => setAceQuery(e.target.value)}
            placeholder={isStocks ? "行情、财报、估值、新闻和宏观数据的一站式股票搜索引擎" : "行情、指标、数据、信息和功能的一站式 Web3 搜索引擎"}
          />
          <footer>
            <button
              className={attachmentOpen ? "on" : ""}
              aria-label="添加附件"
              title="添加附件"
              onClick={() => setAttachmentOpen(!attachmentOpen)}
            >
              <I.Plus />
            </button>
            <button
              aria-label="提交 AI 智搜"
              onClick={() =>
                setAceMode(aceMode === "快速回答" ? "深度思考" : "快速回答")
              }
            >
              {aceMode} <I.CaretDown />
            </button>
            <button aria-label="发送 AI 智搜问题" disabled={aceLoading} onClick={submitAIQuery}>
              {aceLoading ? <I.CircleNotch className="spin"/> : <I.ArrowUp />}
            </button>
          </footer>
          {attachmentOpen ? (
            <div className="ace-attachments">
              <button
                onClick={() =>
                  openOverlay("attachment", "添加图表快照", {
                    description: "选择当前行情图表作为 AI 智搜上下文。",
                  })
                }
              >
                <I.ChartLine /> 图表快照
              </button>
              <button
                onClick={() =>
                  openOverlay("attachment", "添加自选币种", {
                    description: `选择一个自选${isStocks ? "股票" : "币种"}作为问题上下文。`,
                  })
                }
              >
                <I.Star /> 自选{isStocks ? "股票" : "币种"}
              </button>
            </div>
          ) : null}
        </div>
        <div className="question-grid">
          {[
            ...(isStocks ? [
              ["财报速读", "NVDA 最新财报的增长质量如何？"],
              ["市场情绪", "利率变化如何影响科技股估值？"],
              ["价格分析", "AAPL 当前关键支撑位在哪里？"],
            ] : [
              ["快速学习", "特朗普关税政策如何影响BTC？"],
              ["市场情绪", "当前恐惧与贪婪指数意味着什么？"],
              ["价格分析", "BTC关键支撑位在哪里？"],
            ]),
          ].map((x) => (
            <button key={x[0]} onClick={() => setAceQuery(x[1])}>
              <b>{x[0]}</b>
              <span>{x[1]}</span>
              <small>点击开始提问</small>
            </button>
          ))}
        </div>
      </div>
    );
  if (tab === "市场概览")
    return (
      <div className="overview-page">
        <section className="market-cards">
          {(isStocks ? [["标普 500","6,389.77","+0.32%"],["纳斯达克","21,108.32","+0.41%"],["VIX 波动率","14.72","-2.18%"],["美股总市值","$62.8万亿","+0.36%"]] : [["恐惧&贪婪指数","40","中性"],["全网爆仓","$1.82亿","24H -12.4%"],["BTC 市占率","54.21%","+0.18%"],["市场总市值","$2.34万亿","+1.02%"]]).map((item) => <OverviewCard key={item[0]} t={item[0]} v={item[1]} s={item[2]} onClick={()=>openOverlay("tool",item[0])} />)}
        </section>
        <div className="overview-grid">
          <section>
            <h3>市场异动</h3>
            {news.map((x) => (
              <button key={`${x[0]}-${x[1]}`} onClick={()=>openOverlay("flash","市场异动详情",{description:`${x[1]} · ${x[2]} · ${x[3]}`})}>
                <time>{x[0]}</time>
                <b>{x[1]}</b>
                <em>{x[3]}</em>
              </button>
            ))}
          </section>
          <section>
            <h3>热门{isStocks ? "股票" : "币种"}</h3>
            {(isStocks ? stocks : coins).map((x) => (
              <button key={x[0]} onClick={()=>openOverlay("coin",isStocks ? x[0] : `${x[0]}/USDT`,{description:`最新价 ${x[1]}，24H涨跌 ${x[2]}`})}>
                <b>{x[0]}</b>
                <span>{x[1]}</span>
                <em>{x[2]}</em>
              </button>
            ))}
          </section>
          <section>
            <h3>{isStocks ? "市场数据" : "合约数据"}</h3>
            {(isStocks ? ["美债 10Y 4.24%", "美元指数 97.84", "今日财报 42 家", "北向 ADR +0.62%"] : [
              "多空持仓人数比 1.62",
              "BTC 资金费率 0.0081%",
              "24H 爆仓 $8,420万",
              "主力挂单 $43.56亿",
            ]).map((x) => (
              <p key={x}>{x}</p>
            ))}
          </section>
        </div>
      </div>
    );
  if (tab === "条件选币" || tab === "条件选股") return <Screener marketMode={marketMode} />;
  if (["热门榜单", "排行", "热门股票", "涨幅榜"].includes(tab)) return <Ranking title={tab} marketMode={marketMode} />;
  if (["财经日历", "板块热力", "财报雷达"].includes(tab)) return <StockChannel tab={tab} openOverlay={openOverlay} />;
  if (tab === "功能指南") return <Toolbox go={go} />;
  if (tab === "合约雷达") return <FuturesRadar />;
  return <div />;
}
function OverviewCard({ t, v, s, onClick }) {
  return (
    <button onClick={onClick}>
      <small>{t}</small>
      <strong>{v}</strong>
      <em>{s}</em>
      <I.CaretRight />
    </button>
  );
}
function Screener({ marketMode = "web3" }) {
  const isStocks = marketMode === "stocks";
  const [filter, setFilter] = useState("市值排名");
  const [search, setSearch] = useState("");
  const cryptoRows = [
    ["BTC", "64,020.04", "+1.44%", "$1.28万亿", "$21.8亿"],
    ["ETH", "3,172.22", "+0.55%", "$3820亿", "$12.4亿"],
    ["SOL", "148.32", "+0.29%", "$714亿", "$6.8亿"],
    ["XRP", "0.55", "0.00%", "$302亿", "$3.2亿"],
    ["HYPE", "42.06", "-2.20%", "$126亿", "$2.7亿"],
  ];
  const stockRows = stocks.slice(0, 6).map((x) => [x[0], x[1], x[2], quoteFor(x[0]).marketCap, quoteFor(x[0]).turnover]);
  const rows = isStocks ? stockRows : cryptoRows;
  const sortedRows = rows.slice().sort((a,b)=>{
    if(filter === "涨跌幅") return parseFloat(b[2])-parseFloat(a[2]);
    if(filter === "成交额") return parseFloat(b[4].replace(/[^\d.]/g,""))-parseFloat(a[4].replace(/[^\d.]/g,""));
    if(filter === "流通市值") return parseFloat(b[3].replace(/[^\d.]/g,""))-parseFloat(a[3].replace(/[^\d.]/g,""));
    return rows.indexOf(a)-rows.indexOf(b);
  });
  return (
    <div className="list-page">
      <div className="filterbar">
        <button
          className={filter === "市值排名" ? "on" : ""}
          onClick={() => setFilter("市值排名")}
        >
          市值排名 <I.CaretDown />
        </button>
        <button
          className={filter === "涨跌幅" ? "on" : ""}
          onClick={() => setFilter("涨跌幅")}
        >
          涨跌幅 <I.CaretDown />
        </button>
        <button
          className={filter === "成交额" ? "on" : ""}
          onClick={() => setFilter("成交额")}
        >
          成交额 <I.CaretDown />
        </button>
        <button
          className={filter === "流通市值" ? "on" : ""}
          onClick={() => setFilter("流通市值")}
        >
          流通市值 <I.CaretDown />
        </button>
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder={`搜索${isStocks ? "股票" : "币种"}`}
        />
      </div>
      <Table
        rows={sortedRows.filter((r) =>
          r[0].toLowerCase().includes(search.toLowerCase()),
        )}
        heads={[isStocks ? "股票" : "币种", "最新价", "24H涨跌", "流通市值", "成交额"]}
      />
    </div>
  );
}
function Ranking({ title, marketMode = "web3" }) {
  const isStocks = marketMode === "stocks";
  const [rankType, setRankType] = useState("涨幅榜");
  const baseRows = [
    ["1", "BTC", "+1.44%", "$21.8亿", "热度 98"],
    ["2", "ADA", "+3.30%", "$8.6亿", "热度 94"],
    ["3", "INJ", "+2.85%", "$4.2亿", "热度 91"],
    ["4", "CRO", "+2.60%", "$2.9亿", "热度 88"],
    ["5", "CAKE", "+2.17%", "$1.8亿", "热度 82"],
  ];
  const stockBaseRows = stocks.slice(0, 5).map((x, index) => [String(index + 1), x[0], x[2], quoteFor(x[0]).turnover, `关注 ${98 - index * 4}`]);
  const rankRows = isStocks ? (rankType === "跌幅榜" ? stockBaseRows.slice().sort((a,b)=>parseFloat(a[2])-parseFloat(b[2])) : stockBaseRows.slice().sort((a,b)=>parseFloat(b[2])-parseFloat(a[2]))) : rankType === "跌幅榜"
    ? [["1","HYPE","-2.20%","$2.7亿","热度 89"],["2","AAVE","-3.22%","$1.9亿","热度 86"],["3","GNO","-4.50%","$0.8亿","热度 72"],["4","POL","-3.64%","$1.4亿","热度 78"],["5","BDX","-4.24%","$0.6亿","热度 69"]]
    : rankType === "成交榜"
      ? baseRows.slice().sort((a,b)=>parseFloat(b[3].replace(/[^\d.]/g,""))-parseFloat(a[3].replace(/[^\d.]/g,"")))
      : rankType === "热搜榜"
        ? [["1","PEPE","+0.82%","$9.6亿","热度 100"],["2","BTC","+1.44%","$21.8亿","热度 98"],["3","ETH","+0.55%","$12.4亿","热度 96"],["4","SOL","+0.29%","$6.8亿","热度 94"],["5","XRP","0.00%","$3.2亿","热度 92"]]
        : baseRows;
  return (
    <div className="list-page">
      <div className="channel-title">
        <h1>{title}</h1>
        <div>
          {["涨幅榜", "跌幅榜", "成交榜", "热搜榜"].map((x) => (
            <button
              key={x}
              className={rankType === x ? "on" : ""}
              onClick={() => setRankType(x)}
            >
              {x}
            </button>
          ))}
        </div>
      </div>
      <Table rows={rankRows} heads={["排名", isStocks ? "股票" : "币种", "涨跌幅", "成交额", isStocks ? "关注度" : "热度"]} />
    </div>
  );
}
function StockChannel({ tab, openOverlay }) {
  const data = {
    财经日历: { heads: ["时间", "事件", "重要性", "预期", "前值"], rows: [["20:30", "美国初请失业金人数", "高", "23.1万", "22.8万"], ["22:00", "美国成屋销售", "中", "3.92M", "3.93M"], ["次日 02:00", "美联储褐皮书", "高", "—", "—"], ["次日 04:30", "API 原油库存", "中", "—", "+130万桶"]] },
    板块热力: { heads: ["板块", "涨跌幅", "领涨股", "成交额", "资金趋势"], rows: [["半导体", "+2.41%", "NVDA", "$38.6B", "净流入"], ["云计算", "+1.32%", "MSFT", "$19.2B", "净流入"], ["电动车", "+0.84%", "TSLA", "$12.8B", "震荡"], ["金融科技", "-0.26%", "HOOD", "$6.4B", "净流出"]] },
    财报雷达: { heads: ["股票", "发布时间", "EPS 预期", "营收预期", "关注点"], rows: [["NVDA", "盘后", "$1.01", "$45.8B", "AI 芯片指引"], ["CRM", "盘后", "$2.78", "$10.1B", "订阅增长"], ["DELL", "盘后", "$2.30", "$29.2B", "服务器订单"], ["BABA", "盘前", "$2.19", "$34.6B", "云业务利润"]] },
  }[tab];
  return <div className="list-page stock-channel"><div className="channel-title"><div><small>股票市场 · 本地模拟数据</small><h1>{tab}</h1></div><button onClick={() => openOverlay("tool", `${tab}提醒`, { description: `已创建${tab}本地提醒预览。` })}><I.Bell /> 设置提醒</button></div><Table heads={data.heads} rows={data.rows} /></div>;
}
function Toolbox({ go }) {
  const tools = [
    ["K线行情", I.ChartBar, "专业图表、指标与画线", "market"],
    ["条件选币", I.Funnel, "多维度筛选机会", "home"],
    ["AI网格", I.Robot, "智能捕捉震荡差价", "strategy"],
    ["链上聪明钱", I.BezierCurve, "追踪巨鲸与高手地址", "chain"],
    ["资产分析", I.Wallet, "统一查看多平台资产", "assets"],
    ["API授权", I.Key, "连接交易所账户", "auth"],
  ];
  return (
    <div className="toolbox">
      <h1>功能指南</h1>
      <p>快速找到适合你的行情、交易和数据工具</p>
      <div>
        {tools.map(([n, Icon, d, p]) => (
          <button key={n} onClick={() => go(p)}>
            <Icon />
            <span>
              <b>{n}</b>
              <small>{d}</small>
            </span>
            <I.CaretRight />
          </button>
        ))}
      </div>
    </div>
  );
}
function FuturesRadar() {
  const [metric, setMetric] = useState("资金费率");
  const radarRows = coins.map((x, i) => [
    x[0],
    (0.006 + i * 0.0012).toFixed(4) + "%",
    (12 - i * 1.4).toFixed(1) + "亿美元",
    8420 - i * 730 + "万",
    "1." + (62 - i * 7),
  ]).sort((a,b)=>{
    const column={资金费率:1,持仓量:2,爆仓:3,多空比:4}[metric];
    return parseFloat(String(b[column]).replace(/[^\d.]/g,""))-parseFloat(String(a[column]).replace(/[^\d.]/g,""));
  });
  return (
    <div className="list-page">
      <div className="channel-title">
        <h1>合约雷达</h1>
        <div>
          {["资金费率", "爆仓", "持仓量", "多空比"].map((x) => (
            <button
              key={x}
              className={metric === x ? "on" : ""}
              onClick={() => setMetric(x)}
            >
              {x}
            </button>
          ))}
        </div>
      </div>
      <Table
        heads={["币种", "资金费率", "持仓量", "24H爆仓", "多空比"]}
        rows={radarRows}
      />
    </div>
  );
}
function Table({ heads, rows }) {
  const [selected, setSelected] = useState(null);
  const rowsKey = rows.map((row) => row.join("|")).join("~");
  useEffect(() => setSelected(null), [rowsKey]);
  return (
    <div className="data-table-wrap">
      <div className="data-table">
        <header>
          {heads.map((x) => (
            <b key={x}>{x}</b>
          ))}
        </header>
        {rows.map((r, rowIndex) => (
          <button
            key={`${r[0]}-${rowIndex}`}
            className={selected === rowIndex ? "selected" : ""}
            onClick={() => setSelected(selected === rowIndex ? null : rowIndex)}
          >
            {r.map((x, i) => (
              <span
                key={`${x}-${i}`}
                className={
                  String(x).startsWith("+")
                    ? "green"
                    : String(x).startsWith("-")
                      ? "red"
                      : ""
                }
              >
                {x}
              </span>
            ))}
          </button>
        ))}
      </div>
      {selected !== null && (
        <div className="row-detail">
          <b>{rows[selected][0]} 详情</b>
          <span>{rows[selected].join("　")}</span>
          <button onClick={() => setSelected(null)}>关闭</button>
        </div>
      )}
    </div>
  );
}
function Decision({ level, title, meta, onClick }) {
  return (
    <button className="decision" onClick={onClick}>
      <em className={"l-" + level}>{level}</em>
      <span>
        <b>{title}</b>
        <small>{meta}</small>
      </span>
      <I.CaretRight />
    </button>
  );
}
function Risk({ name, value, bad }) {
  return (
    <div className="risk">
      <span>{name}</span>
      <b>{value}%</b>
      <div>
        <i className={bad ? "bad" : ""} style={{ width: value + "%" }} />
      </div>
    </div>
  );
}

function Market({
  tab,
  go,
  watch,
  setWatch,
  say,
  openOverlay,
  authorizedAccounts,
  chartTraders,
  setChartTraders,
  chartSnapshots,
  setChartSnapshots,
  marketCommand,
  marketSymbol,
  setMarketSymbol,
  marketMode,
  setMarketMode,
  prefs,
  marketSideTab,
  setMarketSideTab,
  marketSideOpen,
  setMarketSideOpen,
  marketOrderOpen,
  setMarketOrderOpen,
  sidebarMode,
  quickTradePrefill,
}) {
  const [period, setPeriod] = useState("5分"),
    [tool, setTool] = useState(null),
    [bottom, setBottom] = useState("自定义指标/回测/实盘");
  const [watchOpen, setWatchOpen] = useState(false);
  const [orderSplit, setOrderSplit] = useStoredState("ai-trading-assistant-market-order-split", 58);
  const [drawingTool, setDrawingTool] = useState("光标");
  const [drawings, setDrawings] = useStoredState("ai-trading-assistant-chart-drawings", []);
  const [drawingHistory, setDrawingHistory] = useState([]);
  const [drawingRedo, setDrawingRedo] = useState([]);
  const [drawingLocked, setDrawingLocked] = useState(false);
  const [magnetEnabled, setMagnetEnabled] = useState(false);
  const symbol = marketSymbol;
  const setSymbol = setMarketSymbol;
  const startOrderResize = (event) => {
    event.preventDefault();
    const workspace = event.currentTarget.closest(".market-side-workspace");
    if (!workspace) return;
    const update = (moveEvent) => {
      const rect = workspace.getBoundingClientRect();
      const next = Math.max(28, Math.min(76, ((moveEvent.clientY - rect.top) / rect.height) * 100));
      setOrderSplit(Math.round(next * 10) / 10);
    };
    const stop = () => {
      window.removeEventListener("pointermove", update);
      window.removeEventListener("pointerup", stop);
      document.body.classList.remove("resizing-market-order");
    };
    document.body.classList.add("resizing-market-order");
    window.addEventListener("pointermove", update);
    window.addEventListener("pointerup", stop, { once: true });
  };
  const isStocks = marketMode === "stocks";
  const instrument = isStocks ? symbol : `${symbol}/USDT`;
  const marketRows = isStocks ? stocks : coins;
  const [backendMarket, setBackendMarket] = useState({ status: "loading", candles: [], source: "连接后端…" });
  const [symbolFilter, setSymbolFilter] = useState("");
  const [marketCategory, setMarketCategory] = useState("平台");
  const [marketPlatform, setMarketPlatform] = useState(isStocks ? "NASDAQ" : "币安");
  const [marketSort, setMarketSort] = useState("成交额");
  const venueFactor = isStocks ? 1 : ({"币安":1,"欧易OKX":1.0006,"Hyperliquid":.9993,"Bitget":1.0002}[marketPlatform] || 1);
  const baseQuote = quoteFor(symbol);
  const quote = {...baseQuote,price:baseQuote.price*venueFactor,open:baseQuote.open*venueFactor,high:baseQuote.high*venueFactor,low:baseQuote.low*venueFactor};
  useEffect(() => {
    let active = true;
    setBackendMarket({ status: "loading", candles: [], source: "连接后端…" });
    const timeframe = {"1分":"1m","5分":"5m","15分":"15m","30分":"30m","45分":"45m","分时":"5m","1时":"1h","4时":"4h","8时":"8h","1日":"1d","1周":"1wk","1月":"1mo"}[period] || "1d";
    loadBackendCandles(symbol, timeframe).then((result) => { if (active) setBackendMarket(result); });
    return () => { active = false; };
  }, [symbol, marketMode, period]);
  useEffect(() => {
    setMarketPlatform(isStocks ? "NASDAQ" : "币安");
    setMarketCategory(isStocks ? "美股" : "平台");
    setPeriod(isStocks ? "1日" : "5分");
  }, [isStocks]);
  const [studies, setStudies] = useState(["MA", "Volume", "价格线", "倒计时", "买卖信号", "网格线"]);
  const [fullscreen, setFullscreen] = useState(false);
  const [snapshotAt, setSnapshotAt] = useState("");
  const [replayOpen, setReplayOpen] = useState(false);
  const [chartFeature, setChartFeature] = useState(null);
  const [replayConfig, setReplayConfig] = useState({ speed: 1, hideFuture: true, startLabel: "最近90天" });
  const [layoutManagerOpen, setLayoutManagerOpen] = useState(false);
  const [layoutDraft, setLayoutDraft] = useState({ name: "专业多窗", mode: "双窗" });
  const [chartType, setChartType] = useState("蜡烛图");
  const [panePeriods, setPanePeriods] = useState(["分时", "4时", "1日", "15分", "1时", "8时", "1周", "5分", "45分"]);
  const [paneCount, setPaneCount] = useStoredState("ai-trading-assistant-chart-pane-count", 1);
  const [paneSync, setPaneSync] = useStoredState("ai-trading-assistant-chart-pane-sync", ["十字光标", "周期"]);
  const [chartReset, setChartReset] = useState(0);
  const [chartLayouts, setChartLayouts] = useStoredState("ai-trading-assistant-chart-tabs", [
    { id: "default", name: "未命名", symbol: "BTC", saved: true },
  ]);
  const [activeLayout, setActiveLayout] = useState(() => chartLayouts[0]?.id || "default");
  const addChartLayout = () => {
    const next = {
      id: `layout-${Date.now()}`,
      name: `未命名 ${chartLayouts.length + 1}`,
      symbol,
      saved: false,
    };
    setChartLayouts([...chartLayouts, next]);
    setActiveLayout(next.id);
    say("已新建图表标签页");
  };
  const selectChartLayout = (layout) => {
    setActiveLayout(layout.id);
    setSymbol(layout.symbol || "BTC");
  };
  const removeChartLayout = (layoutId) => {
    if (chartLayouts.length === 1) return say("至少保留一个图表标签页");
    const next = chartLayouts.filter((layout) => layout.id !== layoutId);
    setChartLayouts(next);
    if (activeLayout === layoutId) {
      setActiveLayout(next[0].id);
      setSymbol(next[0].symbol || "BTC");
    }
  };
  const saveActiveLayout = () => {
    setChartLayouts(chartLayouts.map((layout) => layout.id === activeLayout ? { ...layout, symbol, saved: true } : layout));
    say("当前图表标签页已保存");
  };
  const createChartSnapshot = (source = "图表工具栏") => {
    const now = new Date();
    const record = {
      id: now.getTime(),
      createdAt: now.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" }),
      symbol,
      period,
      studies: [...studies],
      drawingCount: drawings.length,
      layoutId: activeLayout,
      layoutName: chartLayouts.find((layout) => layout.id === activeLayout)?.name || "未命名",
      source,
    };
    setChartSnapshots([record, ...chartSnapshots].slice(0, 20));
    setSnapshotAt(record.createdAt);
    say(`行情快照已保存 · ${instrument} ${period}`);
  };
  useEffect(() => {
    if (!marketCommand?.id) return;
    if (marketCommand.type === "snapshot") createChartSnapshot("顶部工具栏");
    if (marketCommand.type === "saveLayout") saveActiveLayout();
  }, [marketCommand?.id]);
  const commitDrawings = (next, message) => {
    setDrawingHistory((history) => [...history, drawings]);
    setDrawingRedo([]);
    setDrawings(next);
    if (message) say(message);
  };
  const addDrawing = ({ x, y }) => {
    if (drawingTool === "光标") return;
    if (drawingLocked) return say("图表画线已锁定，请先解锁");
    const snappedX = magnetEnabled ? Math.round(x / 5) * 5 : x;
    const snappedY = magnetEnabled ? Math.round(y / 5) * 5 : y;
    const nextDrawing = {
      id: `drawing-${Date.now()}-${Math.random().toString(16).slice(2)}`,
      type: drawingTool,
      x: Math.max(5, Math.min(90, snappedX)),
      y: Math.max(8, Math.min(82, snappedY)),
      color: drawingTool === "文本" ? "#f0a11a" : "#2979ff",
    };
    commitDrawings([...drawings, nextDrawing], `${drawingTool}已添加到图表`);
  };
  useEffect(() => {
    setChartLayouts((layouts) => layouts.map((layout) => layout.id === activeLayout && layout.symbol !== symbol ? { ...layout, symbol, saved: false } : layout));
  }, [activeLayout, symbol, setChartLayouts]);
  if (tab !== "图表") return <MarketChannel tab={tab} openOverlay={openOverlay} watch={watch} setWatch={setWatch} symbol={symbol} />;
  return (
    <div className={`market ${watchOpen ? "watch-open" : "watch-collapsed"} ${marketSideOpen ? "side-open" : "side-collapsed"} ${marketOrderOpen ? "order-open" : ""}`}>
      <aside className="watchlist">
        <nav className="market-category-tabs">{(isStocks ? ["自选","美股","科技","大型股","高波动"] : ["自选","平台","指数","美股合约","板块"]).map((name)=><button className={marketCategory===name?"on":""} key={name} onClick={()=>setMarketCategory(name)}>{name}</button>)}</nav>
        <nav className="market-platform-tabs">{(isStocks ? ["NASDAQ","NYSE","全部美股"] : ["币安","欧易OKX","Hyperliquid","Bitget"]).map((name)=><button className={marketPlatform===name?"on":""} key={name} onClick={()=>setMarketPlatform(name)}>{name}</button>)}</nav>
        <header>
          <b>{marketCategory}行情</b><small>{marketPlatform}</small>
          <button
            aria-label="添加自选"
            onClick={() => openOverlay("addWatch", "添加自选")}
          >
            <I.Plus />
          </button>
        </header>
        <input
          value={symbolFilter}
          onChange={(e) => setSymbolFilter(e.target.value)}
          placeholder="筛选标的"
        />
        <div className="market-list-head">{["名称","成交额","最新价","涨跌幅"].map((name)=><button className={marketSort===name?"on":""} key={name} onClick={()=>setMarketSort(name)}>{name}<I.CaretUpDown/></button>)}</div>
        {marketRows
          .filter((c) => marketCategory === "自选" ? watch.includes(c[0]) : isStocks ? (marketPlatform === "全部美股" || c[3] === marketPlatform) : marketCategory === "美股合约" ? c[3] === "美股合约" : marketCategory === "指数" ? ["XAU","XAG"].includes(c[0]) : c[3] !== "美股合约")
          .filter((c) =>
            c[0].toLowerCase().includes(symbolFilter.toLowerCase()),
          )
          .sort((a,b)=>marketSort==="名称"?a[0].localeCompare(b[0]):marketSort==="最新价"?Number(String(b[1]).replace(/,/g,""))-Number(String(a[1]).replace(/,/g,"")):marketSort==="涨跌幅"?parseFloat(b[2])-parseFloat(a[2]):marketRows.indexOf(a)-marketRows.indexOf(b))
          .map((c) => (
            <button
              key={c[0]}
              className={c[0] === symbol ? "on" : ""}
              onClick={() => setSymbol(c[0])}
            >
              <span>
                <b>{c[0]}</b>
                <small>{isStocks ? `${c[4]} · ${c[3]}` : `USDT · ${marketPlatform}`}</small>
              </span>
              <span>
                {c[1]}
                <em>{c[2]}</em>
              </span>
            </button>
          ))}
      </aside>
      <section
        className={
          fullscreen ? "chart-workspace chart-fullscreen" : "chart-workspace"
        }
      >
        <div className="chart-layout-bar">
          <button className="symbol-chip" onClick={() => setWatchOpen(!watchOpen)}>
            <i>{symbol.slice(0, 1)}</i>
            <span><b>{instrument}</b><small>{formatPrice(quote.price, quote.decimals)}　{quote.change}</small></span>
          </button>
          <div className={`market-data-status ${backendMarket.status}`} title={backendMarket.source}><i/><span>{backendMarket.status === "connected" ? `后端行情 · ${backendMarket.source}` : backendMarket.status === "loading" ? "正在读取市场数据" : `${backendMarket.source} · 演示回退`}</span></div>
          <div className="chart-layout-tabs">
            {chartLayouts.map((layout) => (
              <span className={activeLayout === layout.id ? "on" : ""} key={layout.id}>
                <button onClick={() => selectChartLayout(layout)}><I.Square />{layout.name}{layout.saved ? <small>默认</small> : <em>●</em>}</button>
                <button aria-label={`关闭${layout.name}`} onClick={() => removeChartLayout(layout.id)}><I.X /></button>
              </span>
            ))}
            <button aria-label="新增图表标签页" onClick={addChartLayout}><I.Plus /></button>
          </div>
          <button className="layout-save" onClick={saveActiveLayout}><I.FloppyDisk />保存</button>
          <button className={layoutManagerOpen?"layout-manage on":"layout-manage"} onClick={() => setLayoutManagerOpen(!layoutManagerOpen)}><I.SquaresFour />布局</button>
          <button
            className="snapshot-history"
            onClick={() => openOverlay("chartSnapshots", "行情快照记录", {
              snapshots: chartSnapshots,
              onDeleteSnapshot: (id) => setChartSnapshots((current) => current.filter((snapshot) => snapshot.id !== id)),
              onClearSnapshots: () => setChartSnapshots([]),
              onRestoreSnapshot: (snapshot) => {
                setSymbol(snapshot.symbol);
                setPeriod(snapshot.period);
                setStudies(snapshot.studies || []);
                if (chartLayouts.some((layout) => layout.id === snapshot.layoutId)) setActiveLayout(snapshot.layoutId);
              },
            })}
          ><I.Images />快照记录 {chartSnapshots.length}</button>
        </div>
        {layoutManagerOpen&&<aside className="chart-layout-manager"><header><b>图表布局管理</b><button aria-label="关闭图表布局管理" onClick={()=>setLayoutManagerOpen(false)}><I.X/></button></header><label>布局名称<input value={layoutDraft.name} onChange={(event)=>setLayoutDraft({...layoutDraft,name:event.target.value})}/></label><div>{["单窗","双窗","四窗","六窗","九窗"].map((name)=><button className={layoutDraft.mode===name?"on":""} key={name} onClick={()=>setLayoutDraft({...layoutDraft,mode:name})}>{name}</button>)}</div><footer><button onClick={()=>{setStudies([...studies.filter((name)=>!["单窗","双窗","四窗","六窗","九窗"].includes(name)),layoutDraft.mode]);say(`已预览${layoutDraft.mode}`)}}>预览布局</button><button onClick={()=>{if(!layoutDraft.name.trim())return say("请输入布局名称");const next={id:`layout-${Date.now()}`,name:layoutDraft.name.trim(),symbol,saved:true};setChartLayouts([...chartLayouts,next]);setActiveLayout(next.id);setStudies([...studies.filter((name)=>!["单窗","双窗","四窗","六窗","九窗"].includes(name)),layoutDraft.mode]);setLayoutManagerOpen(false);say(`${layoutDraft.name}布局已保存`)}}>保存布局</button></footer></aside>}
        <div className="chart-tools">
          <button
            className={watchOpen ? "on watch-toggle" : "watch-toggle"}
            aria-label={watchOpen ? "收起自选列表" : "展开自选列表"}
            title={watchOpen ? "收起自选列表" : "展开自选列表"}
            onClick={() => setWatchOpen(!watchOpen)}
          >
            <I.List />
          </button>
          <div>
            {["指标", "高级", "多窗", "复盘"].map((x) => (
              <button
                key={x}
                className={tool === x ? "on" : ""}
                onClick={() => setTool(tool === x ? null : x)}
              >
                {x}
              </button>
            ))}
          </div>
          <i />
          <label className="chart-type-select" title="切换图表类型">
            <I.ChartLine />
            <select aria-label="图表类型" value={chartType} onChange={(event)=>setChartType(event.target.value)}>
              <option>蜡烛图</option>
              <option>空心蜡烛</option>
              <option>折线图</option>
              <option>面积图</option>
            </select>
          </label>
          {(isStocks ? ["分时", "5分", "15分", "1时", "1日", "1周"] : ["1分", "5分", "15分", "1时", "4时", "1日"]).map((x) => (
            <button
              key={x}
              className={period === x ? "on" : ""}
              onClick={() => setPeriod(x)}
            >
              {x}
            </button>
          ))}
          <button className={tool === "周期" ? "on" : ""} title="自定义周期" onClick={()=>setTool(tool === "周期" ? null : "周期")}><I.CaretDown/></button>
          <span />
          <button
            className={snapshotAt ? "saved" : ""}
            title={snapshotAt ? `快照保存于 ${snapshotAt}` : "保存图表快照"}
            onClick={() => {
              createChartSnapshot("图表工具栏");
            }}
          >
            <I.Camera />
          </button>
          <button title="分享当前图表" onClick={()=>openOverlay("shareArticle","分享当前图表",{description:`${instrument} · ${period} · ${studies.join("、")}`})}><I.ShareNetwork/></button>
          <button title="在新标签中打开图表" onClick={addChartLayout}><I.Browser/></button>
          <button
            className={fullscreen ? "on" : ""}
            title={fullscreen ? "退出全屏" : "全屏图表"}
            onClick={() => setFullscreen(!fullscreen)}
          >
            {fullscreen ? <I.ArrowsIn /> : <I.ArrowsOut />}
          </button>
          <button
            className={tool === "显示" ? "on" : ""}
            title="图表显示设置"
            onClick={() => setTool(tool === "显示" ? null : "显示")}
          >
            <I.ListDashes /> 显示
          </button>
          <button
            className="ai"
            onClick={() =>
              openOverlay("aiChart", "AI K线解读", {
                description: `${instrument} · ${period} 周期正在分析`,
              })
            }
          >
            AI 解读
          </button>
        </div>
        <ChartToolPopover
          tool={["指标", "多窗", "周期"].includes(tool) ? null : tool}
          close={() => setTool(null)}
          studies={studies}
          setStudies={setStudies}
          say={say}
          openOverlay={openOverlay}
          symbol={symbol}
          replayOpen={replayOpen}
          replayConfig={replayConfig}
          onStartReplay={() => {
            setReplayOpen(true);
            setTool(null);
            say("K线复盘已启动 · 所有交易均为本地模拟");
          }}
          onFeature={(name) => setChartFeature(name)}
          onReplayOption={(item) => {
            if (item === "选择起始时间") return openOverlay("dateLocator", "选择复盘起始时间", {description:"选择后将重置本地复盘进度。",onApplyDate:(date)=>setReplayConfig({...replayConfig,startLabel:date})});
            if (item.startsWith("复盘速度")) {
              const next = replayConfig.speed === 1 ? 2 : replayConfig.speed === 2 ? 4 : 1;
              setReplayConfig({...replayConfig,speed:next});
              return say(`复盘速度已切换为 ${next}x`);
            }
            if (item === "隐藏未来K线") {
              setReplayConfig({...replayConfig,hideFuture:!replayConfig.hideFuture});
              return say(`未来K线已${replayConfig.hideFuture?"显示":"隐藏"}`);
            }
          }}
        />
        {tool === "指标" && <IndicatorCenter studies={studies} setStudies={setStudies} close={()=>setTool(null)} say={say} openOverlay={openOverlay}/>} 
        {tool === "多窗" && <MultiWindowCenter current={paneCount} close={()=>setTool(null)} say={say} onApply={(count,sync)=>{setPaneCount(count);setPaneSync(sync);say(`已应用 ${count} 窗布局 · 同步 ${sync.length} 项`);}}/>}
        {tool === "周期" && <CustomPeriodCenter current={period} close={()=>setTool(null)} say={say} onSelect={(value)=>{setPeriod(value);setPanePeriods(paneSync.includes("周期")?panePeriods.map(()=>value):panePeriods);}}/>}
        {replayOpen && (
          <KlineReplayPanel
            symbol={symbol}
            quote={quote}
            period={period}
            onChooseStart={() => openOverlay("dateLocator", "选择复盘起始时间", {description:"选择日期和时间后，从该K线开始本地模拟复盘。",onApplyDate:(date)=>setReplayConfig({...replayConfig,startLabel:date})})}
            onClose={() => setReplayOpen(false)}
            say={say}
            initialSpeed={replayConfig.speed}
            hideFuture={replayConfig.hideFuture}
            startLabel={replayConfig.startLabel}
          />
        )}
        {chartFeature && <ChartFeaturePanel feature={chartFeature} symbol={symbol} quote={quote} studies={studies} setStudies={setStudies} onClose={()=>setChartFeature(null)} openOverlay={openOverlay} say={say}/>} 
        <div className="drawing-tools" aria-label="K线绘图工具栏">
          {[
            ["光标", "↖"],
            ["趋势线", "／"],
            ["水平线", "—"],
            ["平行线", "≡"],
            ["测量", "↔"],
            ["矩形", "□"],
            ["文本", "T"],
            ["斐波那契", "F"],
            ["画笔", "✎"],
            ["磁吸", "⊙"],
            ["锁定", "▣"],
            ["删除", "⌫"],
          ].map(([name, glyph]) => (
            <button
              key={name}
              className={
                name === "磁吸"
                  ? magnetEnabled ? "on" : ""
                  : name === "锁定"
                    ? drawingLocked ? "on" : ""
                    : drawingTool === name ? "on" : ""
              }
              title={name}
              onClick={() => {
                if (name === "磁吸") {
                  setMagnetEnabled(!magnetEnabled);
                  say(`磁吸模式已${magnetEnabled ? "关闭" : "开启"}`);
                  return;
                }
                if (name === "锁定") {
                  setDrawingLocked(!drawingLocked);
                  say(`图表画线已${drawingLocked ? "解锁" : "锁定"}`);
                  return;
                }
                if (name === "删除") {
                  if (!drawings.length) return say("图表上暂无可删除的画线");
                  if (drawingLocked) return say("图表画线已锁定，请先解锁");
                  commitDrawings([], `已删除 ${drawings.length} 个图表对象`);
                  return;
                }
                setDrawingTool(name);
                say(name === "光标" ? "已切换为光标模式" : `已选择${name}，点击图表放置`);
              }}
            >
              <span>{glyph}</span>
            </button>
          ))}
          <i />
          <button
            title={`撤销 · ${drawingHistory.length}步`}
            className={drawingHistory.length ? "available" : ""}
            onClick={() => {
              if (!drawingHistory.length) return say("暂无可撤销的绘图操作");
              const previous = drawingHistory[drawingHistory.length - 1];
              setDrawingHistory(drawingHistory.slice(0, -1));
              setDrawingRedo([drawings, ...drawingRedo]);
              setDrawings(previous);
              say("已撤销上一步绘图操作");
            }}
          >
            ↶
          </button>
          <button
            title={`重做 · ${drawingRedo.length}步`}
            className={drawingRedo.length ? "available" : ""}
            onClick={() => {
              if (!drawingRedo.length) return say("暂无可重做的绘图操作");
              const next = drawingRedo[0];
              setDrawingHistory([...drawingHistory, drawings]);
              setDrawingRedo(drawingRedo.slice(1));
              setDrawings(next);
              say("已重做绘图操作");
            }}
          >
            ↷
          </button>
        </div>
        {chartTraders.length > 0 && (
          <div className="chart-trader-strip">
            <span><I.BezierCurve />链上交易员</span>
            {chartTraders.map((trader) => (
              <div className={trader.symbol === symbol ? "active" : ""} key={`${trader.market}-${trader.name}`}>
                <button onClick={() => setSymbol(trader.symbol)}>{trader.name}<small>{trader.symbol}</small></button>
                <button aria-label={`从K线移除${trader.name}`} onClick={() => setChartTraders(chartTraders.filter((item) => !(item.name === trader.name && item.market === trader.market)))}><I.X /></button>
              </div>
            ))}
            <button className="clear" onClick={() => { setChartTraders([]); say("已清空K线交易员轨迹"); }}>清空</button>
          </div>
        )}
        <TradingChartGrid
          layout={paneCount}
          period={period}
          symbol={symbol}
          instrument={instrument}
          marketMode={marketMode}
          externalCandles={backendMarket.candles}
          quote={quote}
          venue={marketPlatform}
          chartType={chartType}
          studies={studies}
          drawings={drawings}
          drawingTool={drawingTool}
          drawingLocked={drawingLocked}
          magnetEnabled={magnetEnabled}
          onDraw={addDrawing}
          trackedTraders={chartTraders.filter((trader) => trader.symbol === symbol)}
          openOverlay={openOverlay}
          replayMode={replayOpen && replayConfig.hideFuture}
          redUp={prefs?.redUp}
          resetSignal={chartReset}
          panePeriods={panePeriods}
          onPanePeriodChange={(index,value)=>{
            if(index===0) setPeriod(value);
            else setPanePeriods(panePeriods.map((item,paneIndex)=>paneIndex===index?value:item));
          }}
          onCreateAlert={(price)=>openOverlay("alertCenter", "预警中心", {symbol:instrument,price:String(price)})}
          onPrefillOrder={(price,side)=>window.dispatchEvent(new CustomEvent("ai-trading-assistant-prefill-order",{detail:{symbol,price:String(price),side}}))}
          onToggleWatch={()=>setWatch(watch.includes(symbol)?watch.filter((coin)=>coin!==symbol):[...watch,symbol])}
          onClearDrawings={()=>commitDrawings([], `已清除 ${drawings.length} 个图表对象`)}
          onStartReplay={()=>setReplayOpen(true)}
          onResetChart={()=>setChartReset((value)=>value+1)}
        />
        <div className="studybar">
          {(isStocks ? ["MA", "EMA", "BOLL", "Volume", "VWAP", "MACD", "RSI", "盘前盘后"] : ["MA", "EMA", "BOLL", "Volume", "持仓量(OI)", "MACD", "RSI", "资金费率"]).map((x) => (
            <button
              key={x}
              className={studies.includes(x) ? "on" : ""}
              onClick={() =>
                setStudies(
                  studies.includes(x)
                    ? studies.filter((s) => s !== x)
                    : [...studies, x],
                )
              }
            >
              {x}
            </button>
          ))}
        </div>
        <div className="period-strip">
          <button onClick={() => openOverlay("dateLocator", "定位到指定时间", {description:"选择日期和时间后，K线将移动到对应位置。"})}>定位到…</button>
          <button onClick={() => openOverlay("dateRange", "选择K线日期范围", {description:"选择起止日期以调整当前图表可见区间。"})}>日期范围⌄</button>
          <i />
          {(isStocks ? ["分时", "5分", "15分", "30分", "1时", "1日", "1周", "1月"] : ["1分", "5分", "15分", "45分", "分时", "1时", "4时", "8时", "1日", "1周"]).map(
            (x) => (
              <button
                key={x}
                className={period === x ? "on" : ""}
                onClick={() => setPeriod(x)}
              >
                {x}
              </button>
            ),
          )}
        </div>
        <MarketWorkbench
          active={bottom}
          setActive={setBottom}
          symbol={symbol}
          setSymbol={setSymbol}
          say={say}
          openOverlay={openOverlay}
          authorizedAccounts={authorizedAccounts}
        />
      </section>
      {marketSideOpen && (
        <aside className="market-side-workspace" aria-label="行情侧栏工作区" style={{ "--market-data-split": `${orderSplit}%` }}>
          <button className="market-side-collapse-handle" aria-label="收起行情侧栏" title="收起行情侧栏" onClick={() => setMarketSideOpen(false)}><I.CaretRight /></button>
          <div className="market-side-data">
            {marketSideTab === "depth" ? (
              <OrderBook openOverlay={openOverlay} watch={watch} setWatch={setWatch} symbol={symbol} instrument={instrument} marketMode={marketMode} venue={marketPlatform} quoteOverride={quote} showDepthBars={prefs?.showDepthBars !== false} />
            ) : (
              <UtilityDrawer
                embedded
                type={marketSideTab}
                close={() => setMarketSideOpen(false)}
                go={go}
                say={say}
                watch={watch}
                setWatch={setWatch}
                marketSymbol={symbol}
                openOverlay={openOverlay}
                openDrawer={(next) => { setMarketSideTab(next); setMarketSideOpen(true); }}
                authorizedAccounts={authorizedAccounts}
                sidebarMode={sidebarMode}
              />
            )}
          </div>
          {marketOrderOpen && (
            <>
            <button className="market-order-resize-handle" aria-label="上下拖动调整下单面板高度" title="拖动调整下单面板高度，双击恢复默认" onClick={(event) => event.preventDefault()} onPointerDown={startOrderResize} onDoubleClick={() => setOrderSplit(58)}><span /></button>
            <div className="market-side-order">
              <UtilityDrawer
                embedded
                type="trade"
                close={() => setMarketOrderOpen(false)}
                go={go}
                say={say}
                watch={watch}
                setWatch={setWatch}
                marketSymbol={symbol}
                prefill={quickTradePrefill}
                openOverlay={openOverlay}
                openDrawer={setMarketSideTab}
                authorizedAccounts={authorizedAccounts}
                sidebarMode={sidebarMode}
              />
            </div>
            </>
          )}
        </aside>
      )}
    </div>
  );
}
function BottomWorkbench({
  active,
  setActive,
  symbol,
  say,
  openOverlay,
  authorizedAccounts,
}) {
  const tabs = [
    "委单区",
    "自定义指标/回测/实盘",
    "AI网格",
    "现货DCA",
    "组合下单",
    "跟单面板",
    "AI分析",
  ];
  const [sub, setSub] = useState("当前委托");
  const [gridMode, setGridMode] = useState("AI推荐");
  const [dcaFrequency, setDcaFrequency] = useState("每天");
  const [basket, setBasket] = useState(["BTC", "ETH"]);
  const [basketDetails, setBasketDetails] = useState({
    BTC: { side: "买入", amount: "" },
    ETH: { side: "买入", amount: "" },
  });
  const [aiText, setAiText] = useState("");
  const [indicatorSection, setIndicatorSection] = useState("指标编辑");
  const [indicatorStatus, setIndicatorStatus] = useState("未保存");
  const [gridInputs, setGridInputs] = useState({
    range: "62,000 - 66,000",
    count: "20",
    amount: "",
  });
  const [gridEstimate, setGridEstimate] = useState(null);
  const [dcaTab, setDcaTab] = useState("创建DCA");
  const [dcaAmount, setDcaAmount] = useState("");
  let panel;
  if (active === "委单区")
    panel = (
      <div className="orders-work">
        <div className="work-subtabs">
          {[
            "现货仓位(0)",
            "当前委托",
            "策略(0)",
            "历史委托",
            "买卖记录",
            "账户资产",
          ].map((x) => (
            <button
              key={x}
              className={sub === x ? "on" : ""}
              onClick={() => setSub(x)}
            >
              {x}
            </button>
          ))}
        </div>
        <div className="work-empty">
          <I.Tray />
          <span>
            {authorizedAccounts.length ? `${sub}暂无记录` : `${sub}暂无数据`}
          </span>
          <button onClick={() => openOverlay("apiAuth", "连接交易账户")}>
            连接账户
          </button>
        </div>
      </div>
    );
  else if (active === "自定义指标/回测/实盘")
    panel = (
      <div className="indicator-work">
        <aside>
          {[
            "指标编辑",
            "指标选币",
            "策略回测",
            "实盘运行 (0/30)",
            "实盘历史",
          ].map((x) => (
            <button
              key={x}
              className={indicatorSection === x ? "on" : ""}
              onClick={() => setIndicatorSection(x)}
            >
              {x}
            </button>
          ))}
        </aside>
        <section>
          <header>
            <b>{indicatorSection} · 自定义TD指标策略_副本</b>
            <em className={indicatorStatus === "编译通过" ? "ok" : ""}>
              {indicatorStatus}
            </em>
            <span />
            <button
              onClick={() => {
                setIndicatorStatus("已保存");
                say("指标已保存");
              }}
            >
              保存
            </button>
            <button
              onClick={() => {
                setIndicatorStatus("编译通过");
                say("编译通过");
              }}
            >
              运行
            </button>
            <button
              onClick={() => {
                setIndicatorSection("策略回测");
                setIndicatorStatus("回测排队中");
                say("回测任务已创建");
              }}
            >
              立即回测
            </button>
          </header>
          <pre>
            <code>
              <i>1</i> // AI交易助手 自定义指标示例
              <br />
              <i>2</i> [td]=td(close)
              <br />
              <i>3</i> plot(td, color.green)
              <br />
              <i>4</i> alertcondition(td &gt; 8)
            </code>
          </pre>
        </section>
      </div>
    );
  else if (active === "AI网格")
    panel = (
      <div className="form-work">
        <div className="work-subtabs">
          {["AI推荐", "手动创建", "运行中(0)", "历史"].map((x) => (
            <button
              key={x}
              className={gridMode === x ? "on" : ""}
              onClick={() => setGridMode(x)}
            >
              {x}
            </button>
          ))}
        </div>
        <div className="inline-form">
          <label>
            价格区间
            <input
              value={gridInputs.range}
              onChange={(e) =>
                setGridInputs({ ...gridInputs, range: e.target.value })
              }
            />
          </label>
          <label>
            网格数量
            <input
              value={gridInputs.count}
              onChange={(e) =>
                setGridInputs({ ...gridInputs, count: e.target.value })
              }
            />
          </label>
          <label>
            投入金额
            <input
              value={gridInputs.amount}
              onChange={(e) =>
                setGridInputs({ ...gridInputs, amount: e.target.value })
              }
              placeholder="≥ 20 USDT"
            />
          </label>
          <button
            onClick={() => {
              if (Number(gridInputs.amount) < 20)
                return say("投入金额不能低于 20 USDT");
              const estimate = (
                Number(gridInputs.amount) *
                (Number(gridInputs.count) > 30 ? 0.021 : 0.0168)
              ).toFixed(2);
              setGridEstimate(estimate);
              say(`${gridMode}网格参数已计算`);
            }}
          >
            计算收益
          </button>
          <button
            className="primary"
            onClick={() => openOverlay("apiAuth", "连接账户后创建网格")}
          >
            创建网格
          </button>
          {gridEstimate && (
            <output className="inline-result">
              预估7日收益 <b>+{gridEstimate} USDT</b>
            </output>
          )}
        </div>
      </div>
    );
  else if (active === "现货DCA")
    panel = (
      <div className="form-work">
        <div className="work-subtabs">
          {["创建DCA", "运行中(0)", "已完成"].map((x) => (
            <button
              key={x}
              className={dcaTab === x ? "on" : ""}
              onClick={() => setDcaTab(x)}
            >
              {x}
            </button>
          ))}
        </div>
        {dcaTab === "创建DCA" ? (
          <div className="inline-form">
            <label>
              定投币种
              <input value={symbol} readOnly />
            </label>
            <label>
              每期金额
              <input
                value={dcaAmount}
                onChange={(e) => setDcaAmount(e.target.value)}
                placeholder="100 USDT"
              />
            </label>
            <label>
              频率
              <select
                value={dcaFrequency}
                onChange={(e) => setDcaFrequency(e.target.value)}
              >
                <option>每天</option>
                <option>每周</option>
                <option>每月</option>
              </select>
            </label>
            <button
              className="primary"
              onClick={() => {
                if (Number(dcaAmount) <= 0) return say("请输入每期金额");
                openOverlay("apiAuth", `创建${dcaFrequency}DCA`);
              }}
            >
              创建DCA
            </button>
          </div>
        ) : (
          <div className="work-empty compact">
            <I.CalendarCheck />
            <span>{dcaTab}暂无定投计划</span>
          </div>
        )}
      </div>
    );
  else if (active === "组合下单")
    panel = (
      <div className="basket-work">
        <header>
          <b>组合币种</b>
          <button
            onClick={() => {
              const name = `币种${basket.length + 1}`;
              setBasket([...basket, name]);
              setBasketDetails({
                ...basketDetails,
                [name]: { side: "买入", amount: "" },
              });
            }}
          >
            + 添加币种
          </button>
          <button
            onClick={() => {
              setBasket(["BTC", "ETH"]);
              setBasketDetails({
                BTC: { side: "买入", amount: "" },
                ETH: { side: "买入", amount: "" },
              });
            }}
          >
            重置
          </button>
        </header>
        {basket.map((x, i) => (
          <div key={`${x}-${i}`}>
            <b>{x}</b>
            <select
              value={basketDetails[x]?.side || "买入"}
              onChange={(e) =>
                setBasketDetails({
                  ...basketDetails,
                  [x]: {
                    side: e.target.value,
                    amount: basketDetails[x]?.amount || "",
                  },
                })
              }
            >
              <option>买入</option>
              <option>卖出</option>
            </select>
            <input
              value={basketDetails[x]?.amount || ""}
              onChange={(e) =>
                setBasketDetails({
                  ...basketDetails,
                  [x]: {
                    side: basketDetails[x]?.side || "买入",
                    amount: e.target.value,
                  },
                })
              }
              placeholder="数量"
            />
            <button
              onClick={() => {
                setBasket(basket.filter((_, n) => n !== i));
                const nextDetails = { ...basketDetails };
                delete nextDetails[x];
                setBasketDetails(nextDetails);
              }}
            >
              <I.Trash />
            </button>
          </div>
        ))}
        <footer>
          <button
            onClick={() => {
              if (!basket.length) return say("请先添加组合币种");
              if (basket.some((x) => Number(basketDetails[x]?.amount) <= 0))
                return say("请填写每个币种的有效数量");
              openOverlay("apiAuth", "连接账户后组合下单", {
                description: basket
                  .map((x) => `${basketDetails[x].side} ${x} ${basketDetails[x].amount}`)
                  .join("；"),
              });
            }}
          >
            预览组合订单
          </button>
        </footer>
      </div>
    );
  else if (active === "跟单面板")
    panel = (
      <div className="copy-work">
        {[
          ["Smart Whale 08", "+84.2%", "68%"],
          ["Delta Hunter", "+62.7%", "72%"],
          ["Macro Fund", "+41.3%", "64%"],
        ].map((x) => (
          <article key={x[0]}>
            <i>{x[0].slice(0, 2)}</i>
            <span>
              <b>{x[0]}</b>
              <small>
                30D收益 {x[1]} · 胜率 {x[2]}
              </small>
            </span>
            <button onClick={() => openOverlay("apiAuth", `跟单 ${x[0]}`)}>
              立即跟单
            </button>
          </article>
        ))}
      </div>
    );
  else
    panel = (
      <div className="ai-work">
        <I.Sparkle />
        <span>
          <b>AI 分析 {symbol}/USDT</b>
          <small>输入问题，结合当前K线、盘口和资金数据回答</small>
        </span>
        <input
          value={aiText}
          onChange={(e) => setAiText(e.target.value)}
          placeholder="例如：当前主力方向如何？"
        />
        <button
          onClick={() =>
            aiText
              ? openOverlay("aiChart", "AI行情分析", {
                  description: `问题：${aiText}。当前趋势中性偏强，关注 63,600 支撑。`,
                })
              : say("请输入分析问题")
          }
        >
          分析
        </button>
      </div>
    );
  return (
    <div className="bottom-work">
      <nav>
        {tabs.map((x) => (
          <button
            key={x}
            className={active === x ? "on" : ""}
            onClick={() => setActive(x)}
          >
            {x}
          </button>
        ))}
      </nav>
      {panel}
    </div>
  );
}
function MarketChannel({ tab, openOverlay, watch, setWatch, symbol = "BTC" }) {
  const quote = quoteFor(symbol);
  const [platform, setPlatform] = useState("全部平台");
  const [depthStep, setDepthStep] = useState("0.1%");
  const [depthMode, setDepthMode] = useState("累计深度");
  useEffect(() => setPlatform(tab === "资金流" ? "净流入" : "全部平台"), [tab]);
  if (tab === "深度")
    return (
      <div className="market-channel">
        <div className="depth-chart">
          <header className="depth-channel-head"><div><h2>{symbol}/USDT 市场深度</h2><small>聚合 Binance、OKX、Bybit 实时委托</small></div><div>{["累计深度", "增量深度"].map((x)=><button key={x} className={depthMode===x?"on":""} onClick={()=>setDepthMode(x)}>{x}</button>)}</div></header>
          <div className="depth-channel-tools"><span>价格精度</span>{["0.01%", "0.1%", "0.5%", "1%"].map((x)=><button key={x} className={depthStep===x?"on":""} onClick={()=>setDepthStep(x)}>{x}</button>)}<button onClick={()=>openOverlay("aiChart","AI 深度解读",{description:`${symbol}/USDT · ${depthMode} · ${depthStep} 精度，当前买盘占优。`})}>AI 解读</button></div>
          <div className="depth-visual">
            <i />
            <i />
            <b>{depthMode}</b>
            <small>精度 {depthStep}</small>
          </div>
          <footer>
            <span>累计买单 $82.4M</span>
            <span>中间价 {formatPrice(quote.price, quote.decimals)}</span>
            <span>累计卖单 $79.8M</span>
          </footer>
        </div>
        <OrderBook openOverlay={openOverlay} watch={watch} setWatch={setWatch} symbol={symbol} />
      </div>
    );
  const map = {
    资金流: {
      title: `${symbol} 资金流向`,
      heads: ["周期", "净流入", "大单流入", "大单流出", "主力方向"],
      rows: [
        ["5分钟", "-$70万", "$182万", "$252万", "流出"],
        ["1小时", "+$420万", "$1,280万", "$860万", "流入"],
        ["4小时", "-$810万", "$3,120万", "$3,930万", "流出"],
        ["24小时", "+$2,860万", "$1.42亿", "$1.13亿", "流入"],
      ],
    },
    合约数据: {
      title: `${symbol} 合约数据`,
      heads: ["平台", "资金费率", "持仓量", "24H成交额", "多空比"],
      rows: [
        ["Binance", "0.0081%", "$82.6亿", "$218亿", "1.62"],
        ["OKX", "0.0068%", "$51.2亿", "$164亿", "1.54"],
        ["Bybit", "0.0092%", "$38.4亿", "$122亿", "1.71"],
        ["Bitget", "0.0075%", "$21.7亿", "$68亿", "1.48"],
      ],
    },
    自选: {
      title: "我的自选",
      heads: ["交易对", "平台", "最新价", "24H涨跌", "成交额"],
      rows: coins.filter((x)=>watch.includes(x[0])).map((x, i) => [
        x[0] + "/USDT",
        i % 2 ? "OKX" : "Binance",
        x[1],
        x[2],
        "$" + (8 + i * 2.7).toFixed(1) + "亿",
      ]),
    },
  }[tab];
  const controls = tab === "资金流" ? ["净流入", "大单", "主力"] : ["全部平台", "币安", "OKX"];
  let rows = map.rows;
  if (tab === "合约数据" && platform !== "全部平台") rows = rows.filter((row)=>row[0] === (platform === "币安" ? "Binance" : platform));
  if (tab === "自选" && platform !== "全部平台") rows = rows.filter((row)=>row[1] === (platform === "币安" ? "Binance" : platform));
  if (tab === "资金流" && platform === "大单") rows = [...rows].sort((a,b)=>parseFloat(String(b[2]).replace(/[^\d.]/g,""))-parseFloat(String(a[2]).replace(/[^\d.]/g,"")));
  if (tab === "资金流" && platform === "主力") rows = rows.filter((row)=>row[4] === "流入");
  return (
    <div className="list-page">
      <div className="channel-title">
        <h1>{map.title}<small>{tab === "自选" ? ` · ${watch.length} 个标的` : " · 实时更新"}</small></h1>
        <div>
          {controls.map((x) => (
            <button
              key={x}
              className={platform === x ? "on" : ""}
              onClick={() => setPlatform(x)}
            >
              {x}
            </button>
          ))}
          {tab === "自选" && <button onClick={()=>openOverlay("addWatch","管理自选")}>＋ 管理自选</button>}
        </div>
      </div>
      {tab === "资金流" && <section className="flow-summary"><article><small>5分钟净流入</small><b className="red">-$0.70M</b></article><article><small>1小时净流入</small><b className="green">+$4.20M</b></article><article><small>24小时净流入</small><b className="green">+$28.60M</b></article><button onClick={()=>openOverlay("aiChart","AI 资金流解读",{description:"短周期仍有卖压，但 24 小时大单净流入保持正向。"})}>解读资金流</button></section>}
      {tab === "合约数据" && <section className="contract-summary"><article><small>全网持仓</small><b>$19.4B</b></article><article><small>24H爆仓</small><b className="red">$182M</b></article><article><small>平均资金费率</small><b>0.0079%</b></article><button onClick={()=>openOverlay("tool","合约数据")}>查看合约雷达</button></section>}
      {rows.length ? <Table heads={map.heads} rows={rows} /> : <div className="market-empty"><I.Star/><b>{tab === "自选" ? "当前筛选下暂无自选标的" : "当前平台暂无数据"}</b><small>{tab === "自选" ? "点击管理自选添加 BTC、ETH、SOL 等交易对" : "切换全部平台查看聚合数据"}</small>{tab === "自选"&&<button onClick={()=>openOverlay("addWatch","添加自选")}>添加自选</button>}</div>}
    </div>
  );
}
function ChartFeaturePanel({ feature, symbol, quote, studies, setStudies, onClose, openOverlay, say }) {
  const [tab,setTab]=useState("概览"),[range,setRange]=useState("24H");
  const added=studies.includes(feature);
  const panels={
    指标胜率:{title:"指标胜率",tabs:["概览","多头","空头"],metrics:[["综合胜率","68.4%"],["信号次数","126"],["平均收益","+3.82%"],["最大回撤","-7.14%"]]},
    筹码分布:{title:"筹码分布",tabs:["价格分布","获利盘","套牢盘"],metrics:[["平均成本",formatPrice(quote.price*.986,quote.decimals)],["获利比例","61.8%"],["密集区",formatPrice(quote.price*.974,quote.decimals)],["集中度","72.4%"]]},
    大额成交:{title:"大额成交",tabs:["实时大单","买入","卖出"],metrics:[["大单净额","+$8.42M"],["主动买入","58.6%"],["最大单笔","$2.18M"],["笔数","43"]]},
    主力挂单统计:{title:"主力挂单统计",tabs:["主力挂单","买盘","卖盘"],metrics:[["委比","+31.42%"],["挂买总额","$28.6M"],["挂卖总额","$16.8M"],["撤单率","18.2%"]]},
  };
  const config=panels[feature]||panels.指标胜率;
  return <aside className="chart-feature-panel"><header><div><small>{symbol}/USDT · 高级行情</small><h3>{config.title}</h3></div><button aria-label={`关闭${config.title}`} onClick={onClose}><I.X/></button></header><nav>{config.tabs.map((name)=><button className={tab===name?"on":""} key={name} onClick={()=>setTab(name)}>{name}</button>)}</nav><div className="chart-feature-range">{["1H","24H","7D"].map((name)=><button className={range===name?"on":""} key={name} onClick={()=>setRange(name)}>{name}</button>)}</div><section className="chart-feature-metrics">{config.metrics.map(([label,value])=><article key={label}><small>{label}</small><b className={String(value).startsWith("+")?"green":String(value).startsWith("-")?"red":""}>{value}</b></article>)}</section><div className={`chart-feature-visual feature-${feature}`}><i/><i/><i/><i/><i/><span>{tab} · {range}</span></div><div className="chart-feature-table">{[["19:14:22","买入",quote.price,"$1.28M"],["19:12:08","卖出",quote.price*1.0012,"$0.86M"],["19:08:41","买入",quote.price*.9984,"$2.18M"]].map((row)=><button key={row[0]} onClick={()=>say(`已定位到 ${row[0]} 的${feature}信号`)}>{row.map((value,index)=><span className={index===1?(value==="买入"?"green":"red"):""} key={value}>{typeof value==="number"?formatPrice(value,quote.decimals):value}</span>)}</button>)}</div><footer><button onClick={()=>openOverlay("alertCenter",`${feature}预警`,{symbol:`${symbol}/USDT`,price:String(quote.price)})}>创建预警</button><button className={added?"on":""} onClick={()=>{setStudies(added?studies.filter((name)=>name!==feature):[...studies,feature]);say(`${feature}已${added?"从K线移除":"显示到K线"}`)}}>{added?"已显示到K线":"显示到K线"}</button></footer></aside>;
}

function Chart({ period, symbol = "BTC", drawings = [], drawingTool = "光标", drawingLocked = false, magnetEnabled = false, onDraw = () => {}, trackedTraders = [], openOverlay = () => {} }) {
  const quote = quoteFor(symbol);
  const move = quote.price - quote.open;
  const support = quote.price * 0.994;
  const resistance = quote.price * 1.006;
  const axis = [quote.price * 1.008, quote.price, quote.price * 0.992, quote.price * 0.984];
  const bars = useMemo(
    () =>
      Array.from({ length: 76 }, (_, i) => ({
        h: 20 + ((i * 17) % 55),
        y: 16 + Math.sin(i / 6) * 17 + (i < 24 ? (24 - i) * 0.8 : 0),
        up: i % 3 !== 0,
      })),
    [],
  );
  return (
    <div className="chart">
      <div className="chart-title">
        <div>
          <b>{symbol}/USDT 币安 · {period}⌄</b>
          <span>3s</span>
        </div>
        <p>
          ◉ {symbol}/USDT　2026-07-18 19:15　开 <em>{formatPrice(quote.open, quote.decimals)}</em>　高 <em>{formatPrice(quote.high, quote.decimals)}</em>　低 {formatPrice(quote.low, quote.decimals)}　收 <em>{formatPrice(quote.price, quote.decimals)}</em>　涨幅 <em>{quote.change}({move >= 0 ? "+" : ""}{formatPrice(move, quote.decimals)})</em>　振幅 <em>{quote.volatility}</em>
        </p>
        <p className="strategy-line">◉ 自定义TD指标策略_副本</p>
      </div>
      <div
        className={`plot ${drawingTool !== "光标" ? "drawing-active" : ""}`}
        aria-label="K线绘图区"
        title={drawingLocked ? "画线已锁定" : drawingTool === "光标" ? "K线图表" : `点击放置${drawingTool}${magnetEnabled ? " · 磁吸开启" : ""}`}
        onClick={(event) => {
          const rect = event.currentTarget.getBoundingClientRect();
          onDraw({
            x: ((event.clientX - rect.left) / rect.width) * 100,
            y: ((event.clientY - rect.top) / rect.height) * 100,
          });
        }}
      >
        <div className="price">
          <span>{formatPrice(quote.price, quote.decimals)}</span>
        </div>
        {bars.map((b, i) => (
          <i
            key={i}
            className={b.up ? "up" : "down"}
            style={{
              left: i * 1.28 + 1 + "%",
              height: b.h,
              top: 40 + b.y + "%",
            }}
          />
        ))}
        <div className="signal sell s1">超买</div>
        <div className="signal buy s2">超卖</div>
        <div className="signal sell s3">超买</div>
        <div className="signal sell s4">超买</div>
        <div className="chart-high">↳ {formatPrice(resistance, quote.decimals)}</div>
        <div className="chart-low">↰ {formatPrice(support, quote.decimals)}</div>
        {trackedTraders.map((trader, index) => (
          <button
            className={`trader-marker ${trader.side === "卖出" ? "sell" : "buy"}`}
            style={{ left: `${18 + (index * 23) % 68}%`, top: `${22 + (index * 17) % 46}%` }}
            key={`${trader.market}-${trader.name}`}
            onClick={(event) => {
              event.stopPropagation();
              openOverlay("trader", trader.name, { description: `${trader.market} · ${trader.role} · ${trader.side} ${trader.symbol}/USDT · 参考价 ${trader.price}` });
            }}
          >
            <b>{trader.side}</b><span>{trader.name}</span><small>{trader.price}</small>
          </button>
        ))}
        <div className="price-axis">
          {axis.map((price) => <span key={price}>{formatPrice(price, quote.decimals)}</span>)}
        </div>
        <div className="time-axis">
          <span>06:00</span><span>09:00</span><span>12:00</span><span>15:00</span><span>18:00</span><span>21:00</span>
        </div>
        <svg className="chart-drawing-layer" viewBox="0 0 100 100" preserveAspectRatio="none" aria-label={`图表对象 ${drawings.length} 个`}>
          {drawings.map((drawing) => {
            const x1 = Math.max(2, drawing.x - 11);
            const x2 = Math.min(96, drawing.x + 13);
            const y1 = Math.max(4, drawing.y + 9);
            const y2 = Math.min(92, drawing.y - 9);
            if (drawing.type === "趋势线") return <line key={drawing.id} x1={x1} y1={y1} x2={x2} y2={y2} />;
            if (drawing.type === "水平线") return <line key={drawing.id} x1="1" y1={drawing.y} x2="97" y2={drawing.y} />;
            if (drawing.type === "平行线") return <g key={drawing.id}><line x1={x1} y1={y1} x2={x2} y2={y2}/><line x1={x1} y1={y1 + 8} x2={x2} y2={y2 + 8}/></g>;
            if (drawing.type === "测量") return <g key={drawing.id}><line className="measure-line" x1={x1} y1={drawing.y} x2={x2} y2={drawing.y}/><text x={drawing.x - 4} y={drawing.y - 3}>+4.82%</text></g>;
            if (drawing.type === "矩形") return <rect key={drawing.id} x={x1} y={drawing.y - 8} width="24" height="17" rx="1" />;
            if (drawing.type === "文本") return <text className="drawing-text" key={drawing.id} x={drawing.x - 3} y={drawing.y}>交易注释</text>;
            if (drawing.type === "斐波那契") return <g className="fib-lines" key={drawing.id}>{[0, 4, 8, 12, 16].map((offset, index) => <g key={offset}><line x1={x1} y1={drawing.y - 8 + offset} x2={x2} y2={drawing.y - 8 + offset}/><text x={x2 + 1} y={drawing.y - 7 + offset}>{["0", ".236", ".5", ".618", "1"][index]}</text></g>)}</g>;
            if (drawing.type === "画笔") return <path key={drawing.id} d={`M ${x1} ${drawing.y + 5} Q ${drawing.x - 5} ${drawing.y - 10}, ${drawing.x} ${drawing.y} T ${x2} ${drawing.y - 5}`} />;
            return null;
          })}
        </svg>
        {drawingTool !== "光标" && <div className="drawing-mode-tip"><b>{drawingTool}</b><span>{drawingLocked ? "已锁定" : `点击图表放置${magnetEnabled ? " · 磁吸" : ""}`}</span></div>}
        <label>AI交易助手</label>
      </div>
    </div>
  );
}
function OrderBook({ openOverlay, watch = [], setWatch = () => {}, symbol = "BTC", instrument = `${symbol}/USDT`, marketMode = "web3", venue = "币安", quoteOverride, showDepthBars = true }) {
  const [bookAction, setBookAction] = useState("盘口");
  const [bookTab, setBookTab] = useState("盘口");
  const quote = quoteOverride || quoteFor(symbol);
  const tick = quote.decimals > 2 ? 0.0001 : 0.01;
  const isWatched = watch.includes(symbol);
  const prefillOrder = (price, side = "买入") => window.dispatchEvent(new CustomEvent("ai-trading-assistant-prefill-order", { detail: { symbol, price: String(price), side } }));
  const selectAction = (action) => {
    if (action === "加预警") {
      openOverlay("alertCenter", "预警中心", {
        symbol: instrument,
        price: String(quote.price),
      });
      return;
    }
    if (action === "加自选") {
      setWatch(isWatched ? watch.filter((coin) => coin !== symbol) : [...watch, symbol]);
      setBookAction(action);
      return;
    }
    setBookAction(action);
  };
  return (
    <aside className="orderbook">
      <header>
        <b>{instrument}　▣</b>
        <span>{venue} 〉</span>
      </header>
      <div className="book-summary">
        <span>{marketMode === "stocks" ? "成交额(USD)" : "成交额($)"}：<b>{quote.turnover}</b></span><span>最高：{formatPrice(quote.high, quote.decimals)}</span>
        <span>{marketMode === "stocks" ? "主动资金" : "净流入($)"}：<em>{quote.inflow}</em></span><span>最低：{formatPrice(quote.low, quote.decimals)}</span>
      </div>
      <div className="book-actions">
        {['加预警',isWatched?'已自选':'加自选','策略','简况'].map((x) => {
          const action = x === "已自选" ? "加自选" : x;
          return (
          <button
            key={x}
            className={bookAction === action || (action === "加自选" && isWatched) ? "on" : ""}
            onClick={() => selectAction(action)}
          >
            {x}
          </button>
        )})}
      </div>
      {bookAction === "策略" && <div className="book-action-panel strategy"><span>基于 {symbol}/USDT 创建策略</span><button onClick={()=>openOverlay("strategyCreate",`创建 ${symbol} 策略`,{strategy:{coin:symbol,type:"正向套利"}})}>创建策略</button></div>}
      {bookAction === "简况" && <div className="book-brief"><p><span>24H成交额</span><b>{quote.turnover}</b></p><p><span>流通市值</span><b>{quote.marketCap}</b></p><p><span>波动率</span><b>{quote.volatility}</b></p></div>}
      <div className="book-tabs">
        {["盘口","成交","资金"].map((name)=><button className={bookTab===name?"on":""} key={name} onClick={()=>setBookTab(name)}>{name}</button>)}
      </div>
      {bookTab === "盘口" ? <><div className="book-head">
        <span>价格</span>
        <span>数量</span>
        <span>累计</span>
      </div>
      {Array.from({ length: 9 }, (_, i) => {
        const price = quote.price + (5 - i) * tick;
        return (
        <button key={`sell-${i}`} className="book sell" title="点击填入卖出价格" onClick={()=>prefillOrder(price, "卖出")}>
          {showDepthBars && <i className="depth-fill" style={{width:`${18+i*8}%`}}/>}
          <span>{formatPrice(price, quote.decimals)}</span>
          <span>{(i * 0.271 + 0.08).toFixed(3)}</span>
          <span>{12 + i * 21}K</span>
        </button>
      )})}
      <button className="last" onClick={()=>prefillOrder(quote.price)} title="点击填入当前价格">
        {formatPrice(quote.price, quote.decimals)} <em>{quote.change}</em>
      </button>
      {Array.from({ length: 9 }, (_, i) => {
        const price = quote.price - (i + 1) * tick;
        return (
        <button key={`buy-${i}`} className="book buy" title="点击填入买入价格" onClick={()=>prefillOrder(price, "买入")}>
          {showDepthBars && <i className="depth-fill" style={{width:`${74-i*6}%`}}/>}
          <span>{formatPrice(price, quote.decimals)}</span>
          <span>{(i * 0.419 + 0.12).toFixed(3)}</span>
          <span>{31 + i * 17}K</span>
        </button>
      )})}</> : bookTab === "成交" ? <div className="recent-trades"><header><span>价格</span><span>数量</span><span>时间</span></header>{Array.from({length:10},(_,i)=>{const price=quote.price+(i%3?-tick:tick*2)*i;return <button key={i} onClick={()=>prefillOrder(price,i%3?"买入":"卖出")}><b className={i%3?"green":"red"}>{formatPrice(price,quote.decimals)}</b><span>{(0.0042+i*.0031).toFixed(4)}</span><time>19:14:{22-i}</time></button>})}</div> : <div className="book-funds"><article><small>5分钟净流入</small><strong className={quote.inflow.startsWith("-") ? "red" : "green"}>{quote.inflow}</strong></article><article><small>1小时净流入</small><strong className="green">+$4.20M</strong></article><article><small>24小时净流入</small><strong className="green">+$28.60M</strong></article><div><i style={{width:"58%"}}/><span>主动买入 58%</span></div></div>}
    </aside>
  );
}

function News({ tab, openOverlay }) {
  const [selectedArticle, setSelectedArticle] = useState(0);
  const [followed, setFollowed] = useState(false);
  const [liked, setLiked] = useState(false);
  const channelArticles = {
    精选: [
      "AI交易助手｜7.18快照：战略储备法案、美股暴跌、黄金突破",
      "美国参议院今日讨论战略比特币储备法案",
      "高盛：央行购金需求将支撑金价",
    ],
    "Web3.0": [
      "Web3 生存手册 01｜私钥、助记词和钱包密码",
      "Coding 的投注面板赚钱了，但 Polymarket 真不是套利",
      "链上身份与钱包安全指南",
    ],
    分析: [
      "BTC 波动率抬升，市场在交易什么？",
      "ETH 质押率再创新高",
      "稳定币供应与流动性周期",
    ],
    科普: [
      "一分钟科普：什么是 TradFi？",
      "永续合约资金费率怎么理解？",
      "什么是链上聪明钱？",
    ],
    活动FUN放: ["香港 Web3 嘉年华报名开启", "开发者黑客松进入决赛周", "AI交易助手 城市交易者沙龙回顾"],
    直播回顾: ["直播回顾｜BTC 关键位置与仓位管理", "圆桌实录｜稳定币的新一轮竞争", "宏观数据发布夜直播精华"],
    币股: ["COIN 财报前瞻：交易收入能否延续增长", "矿企算力扩张与比特币周期", "美股加密概念板块资金流向"],
    产品教程: ["五分钟上手自定义指标", "如何配置价格与链上异动预警", "组合下单与策略回测操作指南"],
    长推: ["长推｜从流动性理解本轮行情", "一张图读懂交易所储备变化", "研究员复盘：市场叙事如何轮动"],
    媒体报道: ["全球媒体聚焦数字资产监管进展", "传统金融机构加速布局代币化", "本周国际加密媒体观点摘要"],
    行业报告: ["2026 Q2 数字资产市场报告", "稳定币支付产业全景研究", "链上衍生品用户行为洞察"],
    AI号: ["AI 交易助手如何识别无效信号", "智能体正在改变投研工作流", "AI号精选：本周十个关键结论"],
  };
  const base = channelArticles[tab] || channelArticles.精选;
  const articles = [...base, `${tab}行业一周回顾`, `${tab}值得关注的五件事`];
  return (
    <div className="news-reader">
      <aside>
        <div className="reader-channel">
          {tab}
          <small>频道内容已切换</small>
        </div>
        {articles.map((x, i) => (
          <button
            key={`${tab}-${x}`}
            className={i === selectedArticle ? "on" : ""}
            onClick={() => setSelectedArticle(i)}
          >
            <div>
              <b>{x}</b>
              <p>AI交易助手研究院　07-{String(18 - i).padStart(2, "0")}</p>
              <small>♨ {(9.2 + i * 0.1).toFixed(1)}K</small>
            </div>
            <span className={`article-thumb thumb-${i % 5}`}>
              <em>{tab === "Web3.0" ? "WEB3" : "AI交易助手"}</em>
            </span>
          </button>
        ))}
      </aside>
      <article>
        <div className="article-tag">{tab}</div>
        <h1>{articles[selectedArticle]}</h1>
        <div className="author">
          <i>AC</i>
          <span>
            AI交易助手运营<small>2026/07/18 08:00</small>
          </span>
          <button
            className={followed ? "followed" : ""}
            onClick={() => setFollowed(!followed)}
          >
            {followed ? "已关注" : "+ 关注"}
          </button>
        </div>
        <div className="ai-summary">
          <I.Notebook />
          全文约3432字，阅读需要15分钟，AI总结5秒把握重点{" "}
          <button
            onClick={() =>
              openOverlay("summary", "AI 文章总结", {
                description: `${articles[selectedArticle]}：核心影响集中在市场流动性、风险偏好与政策预期三个方面。`,
              })
            }
          >
            看AI总结
          </button>
        </div>
        <blockquote>{({
          "Web3.0": "钱包密码忘了，不一定会丢币；助记词一旦泄露，才是真危险。",
          产品教程: "先理解每个参数的含义，再让工具替你执行重复工作。",
          行业报告: "数据本身不是结论，趋势、结构和样本边界同样重要。",
          AI号: "AI 可以压缩信息处理时间，但最终决策仍需要人的风险判断。",
          活动FUN放: "把线上观点带到真实交流场景，往往能看到更具体的问题。",
        })[tab] || "市场信息很多，真正重要的是理解事件对流动性与价格预期的影响。"}</blockquote>
        <h3>撰文：AI交易助手研究院</h3>
        <p>
          {({
            活动FUN放: "本频道聚合行业活动、开发者赛事和线下沙龙，并提供时间、地点与参与方式。",
            直播回顾: "本频道将直播中的行情判断、嘉宾观点与问答整理成可快速检索的文字记录。",
            产品教程: "本频道用逐步示例说明行情、预警、策略与资产工具的使用方法。",
            行业报告: "本频道汇总市场规模、资金结构和用户行为研究，并标注数据口径。",
            AI号: "本频道关注 AI 与交易研究的结合，区分辅助分析、自动执行与风险控制。",
          })[tab] || "本频道汇总最新市场信息、数据变化与行业动态，并按重要程度进行整理。"}
        </p>
        <p>
          市场仍在等待更多数据确认。短线资金在不同资产之间快速切换，理解账户、钱包与链上资产之间的区别，是进入市场前最重要的一步。
        </p>
        <footer className="article-actions">
          <button
            className={liked ? "on" : ""}
            onClick={() => setLiked(!liked)}
          >
            ♡ {liked ? 1 : 0}
          </button>
          <span>分享至</span>
          {['𝕏','✈','f','◫','🔗'].map((x) => (
            <button
              key={x}
              onClick={() =>
                openOverlay("shareArticle", "分享文章", {
                  description: `已准备分享：${articles[selectedArticle]}`,
                })
              }
            >
              {x}
            </button>
          ))}
        </footer>
      </article>
    </div>
  );
}

function FlashPage({ tab, say, openOverlay }) {
  const [importantOnly, setImportantOnly] = useState(false);
  const [titleOnly, setTitleOnly] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [refreshedAt, setRefreshedAt] = useState("19:14");
  const [reactions, setReactions] = useState({});
  const [sharedIndex, setSharedIndex] = useState(null);
  const [showAllHot, setShowAllHot] = useState(false);
  const channelLead = {
    精选: ["AI交易助手｜战略储备法案、美股波动与黄金突破", "美国参议院讨论比特币储备法案，风险资产短线波动加剧。", "BTC +0.88%"],
    直播: ["直播｜BTC 跌破关键支撑，分析师正在解盘", "行情直播间已切换至高波动模式，实时跟踪成交与挂单变化。", "BTC -1.24%"],
    巨鲸: ["巨鲸地址 20 分钟内增持 1,840 ETH", "链上地址 0x71…8A 完成两笔大额转入，持仓升至七日高位。", "ETH +0.55%"],
    主力: ["BTC 主力买单墙升至 5,800 万美元", "关键价位下方新增集中承接，委买强度较一小时前提高 23%。", "BTC +0.42%"],
    推特: ["社交热度异动：SOL 讨论量一小时上升 38%", "开发者大会相关话题推动 SOL 进入社交趋势榜前三。", "SOL +1.82%"],
    市场: ["全市场成交额回升，山寨币分化加剧", "过去四小时现货成交增长 17%，资金继续集中在高流动性币种。", "TOTAL +0.31%"],
    特朗普: ["特朗普称将公布新的数字资产政策框架", "市场等待政策细节，相关概念币成交量快速放大。", "TRUMP +3.12%"],
    上新: ["交易平台宣布上线 NEW/USDT 现货交易", "充币通道已开放，集合竞价将在 20:00 开始。", "NEW 上新"],
    链上: ["交易所 BTC 净流入转负，短线抛压暂缓", "过去一小时交易所净流出 420 BTC，活跃地址数同步回升。", "BTC +0.42%"],
    ETF: ["美国现货 BTC ETF 单日净流入 4.2 亿美元", "连续第三个交易日录得净流入，机构资金保持正向。", "ETF +$420M"],
    宏观: ["美国 CPI 低于预期，美元指数短线回落", "利率期货提高年内降息概率，风险资产同步反弹。", "DXY -0.36%"],
    币股: ["COIN 盘前上涨 4.8%，加密概念股走强", "比特币反弹带动矿企与交易平台概念股集体高开。", "COIN +4.8%"],
  }[tab];
  const feed = [
    [
      "18:08",
      true,
      channelLead[0],
      channelLead[1],
      channelLead[2],
    ],
    [
      "17:53",
      false,
      `${tab}｜BTC 交易所净流入转负，短线抛压暂缓`,
      "过去一小时交易所净流出 420 BTC。",
      "BTC +0.42%",
    ],
    [
      "17:31",
      true,
      `${tab}｜巨鲸地址增持 1,840 ETH`,
      "链上地址 0x71…8A 完成两笔大额转入。",
      "ETH +0.55%",
    ],
    [
      "17:20",
      false,
      `${tab}｜期权隐含波动率升至近七日高位`,
      "衍生品市场开始计价晚间宏观数据风险。",
      "BTC +0.14%",
    ],
  ];
  const visibleFeed = importantOnly ? feed.filter((x) => x[1]) : feed;
  return (
    <div className="flash-full">
      <section className="flash-stream">
        <header className="flash-tools">
          <button
            className={importantOnly ? "on" : ""}
            onClick={() => setImportantOnly(!importantOnly)}
          >
            <I.CheckSquare />
            只看重要
          </button>
          <button
            className={titleOnly ? "on" : ""}
            onClick={() => setTitleOnly(!titleOnly)}
          >
            <I.TextT />
            只看标题
          </button>
          <button
            className={autoRefresh ? "on" : ""}
            onClick={() => setAutoRefresh(!autoRefresh)}
          >
            <I.ArrowsClockwise />
            自动刷新
          </button>
          <span />
          <small>更新于 {refreshedAt}</small>
          <button
            onClick={() => {
              const time = new Date().toLocaleTimeString("zh-CN", {
                hour: "2-digit",
                minute: "2-digit",
              });
              setRefreshedAt(time);
              say(`快讯已刷新 · ${time}`);
            }}
          >
            刷新
          </button>
          <button onClick={() => openOverlay("settings", "快讯设置")}>
            <I.Gear />
            设置
          </button>
        </header>
        <div className="flash-date">
          <b>18</b>
          <span>7月</span>
          <em>{tab}</em>
        </div>
        {visibleFeed.map((x, i) => (
          <article key={`${tab}-${x[0]}`} className="flash-item">
            <time>{x[0]}</time>
            <i className={x[1] ? "important" : ""} />
            <div>
              <button
                onClick={() =>
                  openOverlay("flash", "快讯详情", {
                    description: `${x[2]}。${x[3]}`,
                  })
                }
              >
                {x[2]}
              </button>
              {!titleOnly && <p>{x[3]}</p>}
              <footer>
                <span>{x[4]}</span>
                <button
                  className={reactions[i] === "good" ? "reacted good" : ""}
                  onClick={() =>
                    setReactions({
                      ...reactions,
                      [i]: reactions[i] === "good" ? null : "good",
                    })
                  }
                >
                  利好 {i + 2 + (reactions[i] === "good" ? 1 : 0)}
                </button>
                <button
                  className={reactions[i] === "bad" ? "reacted bad" : ""}
                  onClick={() =>
                    setReactions({
                      ...reactions,
                      [i]: reactions[i] === "bad" ? null : "bad",
                    })
                  }
                >
                  利空 {i + (reactions[i] === "bad" ? 1 : 0)}
                </button>
                <button
                  className={sharedIndex === i ? "reacted" : ""}
                  onClick={() => {
                    setSharedIndex(i);
                    say("分享链接已复制");
                  }}
                >
                  {sharedIndex === i ? "已复制" : "分享"}
                </button>
              </footer>
            </div>
          </article>
        ))}
      </section>
      <aside className="flash-side">
        <h3>热点排行榜</h3>
        {[
          "特朗普媒体推出高价推送服务",
          "美国参议院讨论比特币储备",
          "黄金突破关键阻力位",
          ...(showAllHot
            ? ["以太坊ETF单日净流入创新高", "BTC期权波动率快速上升"]
            : []),
        ].map((x, i) => (
          <button
            key={x}
            onClick={() =>
              openOverlay("flash", `热点 ${i + 1}`, { description: x })
            }
          >
            <b>{i + 1}</b>
            <span>{x}</span>
            <I.CaretRight />
          </button>
        ))}
        <h3>舆情指数</h3>
        <div className="sentiment">
          <strong>40</strong>
          <span>中性</span>
        </div>
        <h3>BTC价格与舆情指数</h3>
        <div className="sentiment-chart">
          <svg viewBox="0 0 260 100" preserveAspectRatio="none">
            <polyline points="0,80 30,95 55,35 85,20 115,45 150,28 185,55 220,42 260,65" />
          </svg>
        </div>
        <button
          className="side-more"
          onClick={() => setShowAllHot(!showAllHot)}
        >
          {showAllHot ? "收起热点榜" : "查看完整热点榜"}
        </button>
      </aside>
    </div>
  );
}

function ChainPage({ tab, say, openOverlay, go, followedTraders, setFollowedTraders, chartTraders, setChartTraders }) {
  const chainConfigs = {
    聪明钱: {
      title: "交易员一键上K线，买卖轨迹直接看",
      description: "选择推荐交易员，将其显示到K线，即可在线观察交易活动",
      roles: ["全部", "巨鲸", "聪明钱", "KOL", "机构"],
      rows: [["0x7d…91Af", "巨鲸", "+84.2%", "68%", "$12.8M", "BTC", "买入", "63,820"], ["Smart Whale 08", "聪明钱", "+62.7%", "72%", "$8.4M", "ETH", "买入", "3,145"], ["Macro Fund", "机构", "+41.3%", "64%", "$48.2M", "BTC", "卖出", "64,380"], ["KOL Alpha", "KOL", "+35.8%", "61%", "$2.1M", "SOL", "买入", "146.8"], ["0x33…B21c", "巨鲸", "+28.5%", "58%", "$6.9M", "ETH", "卖出", "3,188"], ["Delta Hunter", "聪明钱", "+24.1%", "66%", "$4.7M", "BTC", "买入", "63,960"]],
      metrics: ["30D收益率", "胜率", "账户权益"],
    },
    Hyperliquid: {
      title: "链上永续交易员，仓位与成交实时追踪",
      description: "观察 Hyperliquid 活跃账户的方向、杠杆与清算风险",
      roles: ["全部", "巨鲸", "聪明钱", "机构"],
      rows: [["0xa8…41F2", "巨鲸", "+126.4%", "3.2x", "$31.6M", "BTC", "买入", "63,740"], ["Perp Quant", "机构", "+73.8%", "2.1x", "$18.3M", "ETH", "卖出", "3,201"], ["HYPE Hunter", "聪明钱", "+58.1%", "4.6x", "$7.9M", "HYPE", "买入", "41.72"], ["0x19…C07d", "巨鲸", "+44.9%", "1.8x", "$22.4M", "SOL", "买入", "147.2"]],
      metrics: ["30D收益率", "平均杠杆", "永续持仓"],
    },
    Polymarket: {
      title: "预测市场高手，观点与仓位一起验证",
      description: "跟踪高胜率账户参与的市场、买入概率与结算记录",
      roles: ["全部", "聪明钱", "KOL", "机构"],
      rows: [["Election Alpha", "聪明钱", "+91.2%", "74%", "$4.8M", "BTC", "买入", "63,910"], ["Macro Oracle", "机构", "+67.5%", "69%", "$12.1M", "ETH", "卖出", "3,176"], ["News Trader", "KOL", "+46.3%", "63%", "$1.6M", "SOL", "买入", "148.1"], ["0xPM…82aC", "聪明钱", "+38.8%", "66%", "$3.2M", "BTC", "卖出", "64,220"]],
      metrics: ["30D收益率", "预测胜率", "持仓规模"],
    },
  };
  const config = chainConfigs[tab];
  const [role, setRole] = useState("全部");
  const [search, setSearch] = useState("");
  useEffect(() => {
    setRole("全部");
    setSearch("");
  }, [tab]);
  const shown = config.rows.filter(
    (x) =>
      (role === "全部" || x[1] === role) &&
      x[0].toLowerCase().includes(search.toLowerCase()),
  );
  return (
    <div className="chain-full">
      <section className="chain-hero">
        <div>
          <small>{tab}</small>
          <h1>{config.title}</h1>
          <p>{config.description}</p>
          <button onClick={() => openOverlay("help", `${tab}使用教程`)}>
            查看教程
          </button>
          {chartTraders.length > 0 && <button className="secondary" onClick={() => go("market")}>查看已上K线 ({chartTraders.length})</button>}
        </div>
        <I.BezierCurve />
      </section>
      <div className="chain-filter">
        {config.roles.map((x) => (
          <button
            key={x}
            className={role === x ? "on" : ""}
            onClick={() => setRole(x)}
          >
            {x}
          </button>
        ))}
        <label>
          <I.MagnifyingGlass />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="搜索名称/标签/0x地址"
          />
        </label>
      </div>
      <div className="trader-cards">
        {shown.map((x, i) => (
          <article
            key={x[0]}
            className={chartTraders.some((item) => item.name === x[0] && item.market === tab) ? "on-chart" : ""}
          >
            <header>
              <i>{x[0].slice(0, 2)}</i>
              <span>
                <b>{x[0]}</b>
                <small>
                  {x[1]} · {tab}
                </small>
              </span>
              <button
                className={followedTraders.includes(`${tab}:${x[0]}`) ? "on" : ""}
                onClick={() =>
                  setFollowedTraders(
                    followedTraders.includes(`${tab}:${x[0]}`)
                      ? followedTraders.filter((n) => n !== `${tab}:${x[0]}`)
                      : [...followedTraders, `${tab}:${x[0]}`],
                  )
                }
              >
                {followedTraders.includes(`${tab}:${x[0]}`) ? "已关注" : "+ 关注"}
              </button>
            </header>
            <div className="trader-line" />
            <section>
              <span>
                {config.metrics[0]}<b>{x[2]}</b>
              </span>
              <span>
                {config.metrics[1]}<b>{x[3]}</b>
              </span>
              <span>
                {config.metrics[2]}<b>{x[4]}</b>
              </span>
            </section>
            <footer>
              <button
                onClick={() =>
                  openOverlay("trader", x[0], {
                    description: `${x[0]} 近30日收益 ${x[2]}，胜率 ${x[3]}`,
                  })
                }
              >
                查看详情
              </button>
              <button
                className={chartTraders.some((item) => item.name === x[0] && item.market === tab) ? "on" : ""}
                onClick={() => {
                  const exists = chartTraders.some((item) => item.name === x[0] && item.market === tab);
                  setChartTraders(exists
                    ? chartTraders.filter((item) => !(item.name === x[0] && item.market === tab))
                    : [...chartTraders, { name: x[0], market: tab, role: x[1], symbol: x[5], side: x[6], price: x[7] }]);
                  say(
                    exists
                      ? `${x[0]} 已从K线移除`
                      : `${x[0]} 已显示到 ${x[5]} K线`,
                  );
                }}
              >
                {chartTraders.some((item) => item.name === x[0] && item.market === tab) ? "已上K线" : "上K线"}
              </button>
            </footer>
          </article>
        ))}
      </div>
    </div>
  );
}

function DataPage({ tab, openOverlay }) {
  const [coin, setCoin] = useState("BTC");
  const [period, setPeriod] = useState("7天");
  const [hyperTab, setHyperTab] = useState("市场概览");
  const [hyperPeriod, setHyperPeriod] = useState("24H");
  if (tab === "Hyperliquid") {
    const hyperMetrics = [
      ["总持仓量", "$12.84B", "+4.21%"],
      ["24H 成交额", "$6.42B", "+8.73%"],
      ["资金费率", "0.0084%", "偏多"],
      ["清算金额", "$84.6M", "多单 58%"],
    ];
    const hyperViews = {
      市场概览: { label:"市场排行", sub:"按持仓量", heads:["市场","价格","持仓量","费率","24H流入"], rows:[["BTC", "$64,020.04", "$4.82B", "0.0081%", "+$182M"], ["ETH", "$3,172.22", "$2.41B", "0.0067%", "+$74M"], ["SOL", "$148.32", "$846M", "0.0112%", "-$21M"], ["HYPE", "$42.18", "$622M", "0.0141%", "+$38M"]]},
      持仓排行: { label:"账户持仓排行", sub:"按账户权益", heads:["账户","方向","仓位价值","杠杆","未实现盈亏"], rows:[["0xa8…41F2","BTC 多","$31.6M","3.2x","+$2.84M"], ["Perp Quant","ETH 空","$18.3M","2.1x","+$1.12M"], ["HYPE Hunter","HYPE 多","$7.9M","4.6x","-$0.42M"], ["0x19…C07d","SOL 多","$5.2M","1.8x","+$0.31M"]]},
      资金费率: { label:"资金费率排行", sub:"按绝对费率", heads:["市场","当前费率","预测费率","8H均值","拥挤方向"], rows:[["HYPE","0.0141%","0.0152%","0.0128%","多头"], ["SOL","0.0112%","0.0108%","0.0094%","多头"], ["BTC","0.0081%","0.0078%","0.0069%","中性"], ["ETH","0.0067%","0.0062%","0.0058%","中性"]]},
      巨鲸活动: { label:"巨鲸活动", sub:"最近24小时", heads:["时间","账户","动作","市场","金额"], rows:[["22:41","0xa8…41F2","加仓多单","BTC","+$4.8M"], ["21:18","0x19…C07d","部分止盈","SOL","-$1.2M"], ["19:52","Perp Quant","新开空单","ETH","$3.6M"], ["18:06","HYPE Hunter","提高杠杆","HYPE","+$2.1M"]]},
    };
    const hyperView = hyperViews[hyperTab];
    return (
      <div className="hyper-full">
        <header>
          <div>
            <small>Hyperliquid</small>
            <h1>链上永续合约数据中心</h1>
            <p>市场、持仓、资金费率与巨鲸活动实时概览</p>
          </div>
          <div>
            {["1H", "4H", "24H", "7D"].map((x) => (
              <button
                key={x}
                className={hyperPeriod === x ? "on" : ""}
                onClick={() => setHyperPeriod(x)}
              >
                {x}
              </button>
            ))}
          </div>
        </header>
        <nav>
          {["市场概览", "持仓排行", "资金费率", "巨鲸活动"].map((x) => (
            <button
              key={x}
              className={hyperTab === x ? "on" : ""}
              onClick={() => setHyperTab(x)}
            >
              {x}
            </button>
          ))}
        </nav>
        <section className="hyper-metrics">
          {hyperMetrics.map((x) => (
            <article key={x[0]}>
              <small>{x[0]} · {hyperPeriod}</small>
              <strong>{x[1]}</strong>
              <em>{x[2]}</em>
            </article>
          ))}
        </section>
        <div className="hyper-layout">
          <section>
            <header><b>{hyperTab}趋势</b><span>实时更新</span></header>
            <svg viewBox="0 0 800 260" preserveAspectRatio="none">
              <defs>
                <linearGradient id="hyperFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0" stopColor="#3b88ef" stopOpacity=".26" />
                  <stop offset="1" stopColor="#3b88ef" stopOpacity="0" />
                </linearGradient>
              </defs>
              <path d="M0 225 L70 214 L125 222 L185 172 L245 182 L310 130 L375 145 L435 96 L500 118 L560 72 L625 88 L690 46 L750 61 L800 24 L800 260 L0 260 Z" fill="url(#hyperFill)" />
              <polyline points="0,225 70,214 125,222 185,172 245,182 310,130 375,145 435,96 500,118 560,72 625,88 690,46 750,61 800,24" />
            </svg>
          </section>
          <aside>
            <header><b>{hyperView.label}</b><span>{hyperView.sub}</span></header>
            <div className="hyper-table-head">{hyperView.heads.map((head)=><span key={head}>{head}</span>)}</div>
            {hyperView.rows.map((x) => (
              <button
                key={x[0]}
                onClick={() => openOverlay("hyperMarket", `${x[0]} · ${hyperTab}`, {description:x.join(" · ")})}
              >
                {x.map((v) => <span key={v}>{v}</span>)}
              </button>
            ))}
          </aside>
        </div>
      </div>
    );
  }
  const reserves =
    coin === "BTC"
      ? [
          ["BTC总储备", "4.19M BTC", "≈ $267.9B"],
          [`${period}变化`, "+2.2K BTC", "买入 +2.8K / 卖出 -570"],
          ["持有实体", "366", "占供应量 10.31%"],
        ]
      : [
          ["ETH总储备", "12.8M ETH", "≈ $40.6B"],
          [`${period}变化`, "+84.2K ETH", "净增持 +0.66%"],
          ["持有实体", "284", "占供应量 10.58%"],
        ];
  return (
    <div className="data-full">
      <header>
        <div>
          <small>{tab}</small>
          <h1>
            {tab === "Hyperliquid" ? "Hyperliquid 数据中心" : "加密货币储备"}
          </h1>
        </div>
        <div>
          {["BTC", "ETH"].map((x) => (
            <button
              key={x}
              className={coin === x ? "on" : ""}
              onClick={() => setCoin(x)}
            >
              {x}
            </button>
          ))}
          {["7天", "30天", "1年"].map((x) => (
            <button
              key={x}
              className={period === x ? "on" : ""}
              onClick={() => setPeriod(x)}
            >
              {x}
            </button>
          ))}
        </div>
      </header>
      <section className="reserve-cards">
        {reserves.map((x) => (
          <article key={x[0]}>
            <small>{x[0]}</small>
            <strong>{x[1]}</strong>
            <span>{x[2]}</span>
          </article>
        ))}
      </section>
      <div className="reserve-layout">
        <section>
          <h3>{coin} 储备趋势</h3>
          <div className="reserve-graph">
            <svg viewBox="0 0 700 240" preserveAspectRatio="none">
              <polyline points="0,210 60,202 120,206 180,144 240,150 300,118 360,112 420,88 480,92 540,54 600,62 700,28" />
            </svg>
          </div>
        </section>
        <aside>
          <h3>近期活动</h3>
          {[
            ["MercadoLibre, Inc.", "-570"],
            ["Cardone Capital", "+2700"],
            ["Canaan Inc.", "+48"],
            ["Strategy", "+120"],
          ].map((x) => (
            <button
              key={x[0]}
              onClick={() =>
                openOverlay("reserveDetail", x[0], {
                  description: `${x[0]} 本期持仓变化 ${x[1]} ${coin}，数据已同步至储备趋势。`,
                })
              }
            >
              <span>
                <b>{x[0]}</b>
                <small>机构持仓变化</small>
              </span>
              <em className={x[1][0] === "-" ? "red" : "green"}>
                {x[1]} {coin}
              </em>
            </button>
          ))}
        </aside>
      </div>
    </div>
  );
}

function MorePage({ tab, go, say, openOverlay }) {
  const defaultNav = ["行情工作区", "常用策略", "数据看板"];
  const [customNav, setCustomNav] = useStoredState(
    "ai-trading-assistant-custom-nav",
    defaultNav,
  );
  const [navSaved, setNavSaved] = useState(true);
  const tools = {
    钱包: [
      ["地址簿", I.AddressBook],
      ["钱包监控", I.Eye],
      ["授权检测", I.ShieldCheck],
      ["Gas 追踪", I.Gauge],
      ["网络节点", I.ShareNetwork],
      ["资产快照", I.Camera],
    ],
    宏观: [
      ["经济日历", I.Calendar],
      ["全球指数", I.Globe],
      ["利率与汇率", I.Percent],
      ["美股行情", I.TrendUp],
      ["黄金原油", I.ChartLine],
      ["市场情绪", I.Gauge],
    ],
    自定义导航: [
      ["行情工作区", I.ChartBar],
      ["常用策略", I.Robot],
      ["数据看板", I.Database],
      ["快讯中心", I.Newspaper],
      ["资产总览", I.Wallet],
      ["链上追踪", I.BezierCurve],
    ],
    帮助中心: [
      ["新手教程", I.BookOpen],
      ["快捷键", I.Keyboard],
      ["联系客服", I.Headset],
      ["意见反馈", I.ChatCircleDots],
      ["检查更新", I.ArrowCircleUp],
      ["关于 AI交易助手", I.Info],
    ],
  }[tab];
  return (
    <div className="more-full">
      <header>
        <small>更多工具</small>
        <h1>{tab}</h1>
        <p>按使用场景组织的 AI交易助手 扩展工具。</p>
      </header>
      <div>
        {tools.map(([x, Icon], i) => (
          <button
            key={x}
            className={
              tab === "自定义导航" && !customNav.includes(x)
                ? "disabled-tool"
                : ""
            }
            onClick={() => {
              if (tab === "自定义导航") {
                setCustomNav(
                  customNav.includes(x)
                    ? customNav.filter((item) => item !== x)
                    : [...customNav, x],
                );
                setNavSaved(false);
                return;
              }
              openOverlay("tool", x, {
                description: `${x} 功能面板已打开。`,
              });
            }}
          >
            <Icon />
            <span>
              <b>{x}</b>
              <small>
                {tab === "自定义导航"
                  ? customNav.includes(x)
                    ? "已显示在常用导航"
                    : "已从常用导航隐藏"
                  : `进入${x}功能`}
              </small>
            </span>
            {tab === "自定义导航" ? (
              <i className={customNav.includes(x) ? "switch on" : "switch"} />
            ) : (
              <I.CaretRight />
            )}
          </button>
        ))}
      </div>
      {tab === "自定义导航" && (
        <footer>
          <button
            onClick={() => {
              setCustomNav(defaultNav);
              setNavSaved(false);
              say("已恢复默认导航");
            }}
          >
            恢复默认导航
          </button>
          <button
            className={navSaved ? "saved" : ""}
            onClick={() => {
              setNavSaved(true);
              say("当前导航配置已保存");
            }}
          >
            {navSaved ? "配置已保存" : "保存配置"}
          </button>
        </footer>
      )}
    </div>
  );
}

const stratSide = [
  ["我的策略", "交易笔记/标签关联/策略草稿"],
  ["智能套利", "低风险/稳健收益/随存随取"],
  ["全币种 DCA", "均摊成本/分批抄底/复利效应"],
  ["AI网格", "捕捉差价/可加杠杆/中短线"],
  ["指标策略", "独家信号/实时监测/自动下单"],
  ["跟单策略 · CEX", "捕捉信号/复制高手收益"],
  ["跟单策略 · DEX", "Hyperliquid 链上跟单"],
  ["主力追踪", "机构大单/巨鲸资金/盘口行为"],
  ["游资追踪", "题材轮动/短线资金/热度共振"],
];
function StrategyCategoryPanel({ category, openOverlay, say }) {
  const [risk, setRisk] = useState("全部风险");
  const [favorites, setFavorites] = useState([]);
  const configs = {
    0: {
      title: "策略广场",
      description: "按收益、风险和运行周期筛选社区公开策略模板。",
      items: [["趋势突破","BTC/USDT","中风险","+62.7%","72%"],["山寨轮动","SOL/USDT","中风险","+84.2%","68%"],["波动率回归","ETH/USDT","低风险","+31.8%","76%"]],
    },
    2: {
      title: "全币种 DCA",
      description: "设置定投币种、周期与单次金额，分批积累现货仓位。",
      items: [["BTC 长期积累","BTC/USDT","低风险","+18.4%","每周"],["ETH 生态定投","ETH/USDT","中风险","+24.1%","每天"],["主流币组合","BTC+ETH","低风险","+20.8%","每月"]],
    },
    3: {
      title: "AI 网格",
      description: "根据波动区间生成网格参数，测算后再进入本地创建。",
      items: [["BTC 震荡网格","BTC/USDT","中风险","1.68%","24格"],["ETH 宽幅网格","ETH/USDT","中风险","2.14%","32格"],["SOL 趋势网格","SOL/USDT","高风险","3.82%","18格"]],
    },
    4: {
      title: "指标策略",
      description: "使用指标信号监测行情、回测并形成模拟策略。",
      items: [["TD 序列反转","BTC/USDT","中风险","62.5%","48次"],["均线趋势","ETH/USDT","低风险","68.2%","36次"],["RSI 背离","SOL/USDT","高风险","57.8%","72次"]],
    },
    5: {
      title: "跟单策略 · CEX",
      description: "复制中心化交易所公开策略，设置独立金额与止损。",
      items: [["稳健趋势","Binance","低风险","+42.8%","71%"],["山寨轮动","OKX","中风险","+84.2%","68%"],["Meme 猎手","Bybit","高风险","+118.4%","54%"]],
    },
    6: {
      title: "跟单策略 · DEX",
      description: "追踪 Hyperliquid 链上公开仓位并创建本地跟单方案。",
      items: [["0x71…8A","Hyperliquid","中风险","+92.6%","74%"],["Smart Whale 08","Hyperliquid","高风险","+138.1%","61%"],["Macro Fund","Hyperliquid","低风险","+38.4%","79%"]],
    },
  }[category];
  const visible = configs.items.filter((item)=>risk === "全部风险" || item[2] === risk);
  return <div className="strategy-category-panel"><header><div><h3>{configs.title}</h3><p>{configs.description}</p></div><select value={risk} onChange={(e)=>setRisk(e.target.value)}><option>全部风险</option><option>低风险</option><option>中风险</option><option>高风险</option></select></header><div className="strategy-card-grid">{visible.map((item)=><article key={item[0]}><header><i>{item[0].slice(0,1)}</i><span><b>{item[0]}</b><small>{item[1]}</small></span><em>{item[2]}</em></header><div><span><small>{category===3?"预估7日":"历史表现"}</small><strong>{item[3]}</strong></span><span><small>{category===2?"执行频率":"胜率/参数"}</small><b>{item[4]}</b></span></div><p>参数可在下一步调整，创建前会展示费用、风险和模拟结果。</p><footer><button className={favorites.includes(item[0])?"on":""} onClick={()=>{setFavorites(favorites.includes(item[0])?favorites.filter((x)=>x!==item[0]):[...favorites,item[0]]);say(favorites.includes(item[0])?"已取消收藏":"已加入收藏")}}><I.Star weight={favorites.includes(item[0])?"fill":"regular"}/></button><button onClick={()=>category>=5||category===0?openOverlay("copyTrade",`查看 ${item[0]}`,{description:`${item[0]} · ${item[2]} · 历史表现 ${item[3]}`}):openOverlay("automationCreate",`创建 ${item[0]}`,{mode:configs.title,symbol:item[1],risk:item[2]})}>{category>=5||category===0?"查看方案":"使用模板"}</button></footer></article>)}</div>{!visible.length&&<div className="strategy-empty"><I.Funnel/><h3>暂无匹配策略</h3><button onClick={()=>setRisk("全部风险")}>清除筛选</button></div>}</div>;
}

function AutoEarnPanel({ openOverlay, say, favorites, setFavorites }) {
  const [filter, setFilter] = useState("精选");
  const [platform, setPlatform] = useState("全部平台");
  const [query, setQuery] = useState("");
  const rows = [
    ["XRP", "币安 ↔ 欧易OKX", "10.95%", "7.97%", "0.0100%", "5天"],
    ["PEPE", "欧易OKX ↔ 币安", "7.17%", "7.46%", "0.0087%", "7天"],
    ["PENDLE", "币安", "0.60%", "7.11%", "0.0007%", "80天"],
    ["LINK", "欧易OKX", "0.61%", "5.57%", "0.0007%", "78天"],
  ];
  const keyOf = (row) => `${row[0]}|${row[0]}/USDT ${row[1]} 永续`;
  const visible = rows
    .filter((row) => platform === "全部平台" || row[1].includes(platform))
    .filter((row) => row[0].toLowerCase().includes(query.toLowerCase()))
    .filter((row) => filter !== "仅看自选" || favorites.includes(keyOf(row)))
    .sort((a, b) => filter === "按收益率" ? parseFloat(b[2]) - parseFloat(a[2]) : 0);
  return (
    <section className="auto-earn-panel">
      <header>
        <div><small>投 U 自动赚 U</small><h3>稳健优选组合</h3><p>基于永续合约资金费率，每 8 小时结算；只创建本地模拟程序。</p></div>
        <div className="auto-earn-metrics"><span><b>8.43%</b><small>组合平均年化</small></span><span><b>4</b><small>可用组合</small></span></div>
      </header>
      <nav>
        {["精选", "仅看自选", "按收益率"].map((name) => <button className={filter === name ? "on" : ""} key={name} onClick={() => setFilter(name)}>{name}</button>)}
        <span />
        <input aria-label="自动赚币币种筛选" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="筛选币种" />
        <select aria-label="自动赚币平台筛选" value={platform} onChange={(event) => setPlatform(event.target.value)}><option>全部平台</option><option>币安</option><option>欧易OKX</option></select>
      </nav>
      <div className="auto-earn-grid">
        {visible.map((row, index) => {
          const key = keyOf(row);
          const saved = favorites.includes(key);
          return <article key={key}>
            <header><i>{row[0].slice(0, 2)}</i><span><b>{row[0]} 自动赚币</b><small>{row[1]} · 永续</small></span>{index === 0 && <em>7日年化最高</em>}</header>
            <div><span><small>当前年化</small><strong>{row[2]}</strong></span><span><small>7日年化</small><b>{row[3]}</b></span><span><small>当前费率</small><b>{row[4]}</b></span><span><small>预计回本</small><b>{row[5]}</b></span></div>
            <footer><button aria-label={`${saved ? "取消收藏" : "收藏"}${row[0]}自动赚币`} className={saved ? "on" : ""} onClick={() => { setFavorites(saved ? favorites.filter((item) => item !== key) : [...favorites, key]); say(saved ? `${row[0]} 已取消收藏` : `${row[0]} 已收藏`); }}><I.Star weight={saved ? "fill" : "regular"}/></button><button onClick={() => openOverlay("strategyCreate", "开始自动赚币", { strategy: { coin: row[0], type: "自动赚币", annualized: row[2] } })}>开始赚币</button></footer>
          </article>;
        })}
      </div>
      {!visible.length && <div className="arb-empty"><I.Star/><b>{filter === "仅看自选" ? "暂无收藏的自动赚币组合" : "当前筛选下暂无组合"}</b><button onClick={() => { setFilter("精选"); setPlatform("全部平台"); setQuery(""); }}>清除筛选</button></div>}
    </section>
  );
}

function ProfessionalArbitragePanel({ openOverlay, say }) {
  const seed = [{ id: "btc-basis", name: "BTC 期现基差", left: "BTC/USDT 币安 永续", right: "BTC/USDT 欧易OKX 现货", leftSide: "卖出", rightSide: "买入" }];
  const [combinations, setCombinations] = useStoredState("ai-trading-assistant-arb-combinations", seed);
  const [orders, setOrders] = useStoredState("ai-trading-assistant-professional-arb-orders", []);
  const [selectedId, setSelectedId] = useState(combinations[0]?.id || null);
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({ name: "", left: "BTC/USDT 币安 永续", right: "BTC/USDT 欧易OKX 现货", leftSide: "卖出", rightSide: "买入" });
  const [orderType, setOrderType] = useState("双边市价");
  const [amountMode, setAmountMode] = useState("同金额");
  const [amount, setAmount] = useState("100");
  const selected = combinations.find((item) => item.id === selectedId) || combinations[0];
  const saveCombination = () => {
    if (!form.name.trim()) return say("请输入组合名称");
    if (combinations.some((item) => item.name === form.name.trim())) return say("组合名称已存在");
    const record = { ...form, name: form.name.trim(), id: `${Date.now()}` };
    setCombinations([...combinations, record]);
    setSelectedId(record.id);
    setEditing(false);
    setForm({ ...form, name: "" });
    say("套利组合已保存到本机");
  };
  const simulateOrder = () => {
    if (!selected) return say("请先创建套利组合");
    if (Number(amount) <= 0) return say("请输入有效下单金额");
    const record = { id: Date.now(), name: selected.name, amount, orderType, amountMode, status: "已模拟", time: new Date().toLocaleTimeString("zh-CN", { hour12: false }) };
    setOrders([record, ...orders]);
    say("双腿模拟订单已写入本地记录");
  };
  return (
    <section className="professional-arb-panel">
      <aside>
        <header><div><small>套利组合</small><b>{combinations.length}/5</b></div><button onClick={() => setEditing(true)}><I.Plus/>新增组合</button></header>
        {combinations.map((item) => <button className={selected?.id === item.id ? "on" : ""} key={item.id} onClick={() => setSelectedId(item.id)}><span><b>{item.name}</b><small>{item.left.split(" ")[0]} ↔ {item.right.split(" ")[0]}</small></span><em>-0.16%</em></button>)}
        {!combinations.length && <div className="professional-empty"><I.ArrowsLeftRight/><b>暂无套利组合</b><small>先配置左右腿币对与方向</small></div>}
      </aside>
      <main>
        {editing ? <div className="arb-combination-form"><header><div><small>组合配置</small><h3>新增套利组合</h3></div><button aria-label="关闭组合配置" onClick={() => setEditing(false)}><I.X/></button></header><label>组合名称<input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} placeholder="例如 BTC期现套利"/></label><div className="arb-leg-grid"><fieldset><legend>左腿</legend><select aria-label="左腿币对" value={form.left} onChange={(event) => setForm({ ...form, left: event.target.value })}><option>BTC/USDT 币安 永续</option><option>ETH/USDT 币安 永续</option><option>SOL/USDT 欧易OKX 永续</option></select><select aria-label="左腿方向" value={form.leftSide} onChange={(event) => setForm({ ...form, leftSide: event.target.value })}><option>卖出</option><option>买入</option></select></fieldset><fieldset><legend>右腿</legend><select aria-label="右腿币对" value={form.right} onChange={(event) => setForm({ ...form, right: event.target.value })}><option>BTC/USDT 欧易OKX 现货</option><option>ETH/USDT 欧易OKX 现货</option><option>SOL/USDT 币安 现货</option></select><select aria-label="右腿方向" value={form.rightSide} onChange={(event) => setForm({ ...form, rightSide: event.target.value })}><option>买入</option><option>卖出</option></select></fieldset></div><footer><button onClick={() => setEditing(false)}>取消</button><button onClick={saveCombination}>保存组合</button></footer></div> : selected ? <>
          <header className="professional-head"><div><small>专业套利</small><h3>{selected.name}</h3><p>{selected.leftSide} {selected.left} · {selected.rightSide} {selected.right}</p></div><div><button onClick={() => openOverlay("alertCenter", "添加价差预警", { alertType: "价差预警" })}>价差预警</button><button className="danger-text" onClick={() => { const next = combinations.filter((item) => item.id !== selected.id); setCombinations(next); setSelectedId(next[0]?.id || null); say("套利组合已删除"); }}>删除组合</button></div></header>
          <div className="spread-workspace"><article><header><b>价差 K 线</b><span>普通版</span></header><div className="spread-chart" aria-label="价差K线图">{[42,58,51,67,48,72,64,79,55,69,61,75,66,82,73,88].map((height, index) => <i key={`${height}-${index}`} className={index % 3 === 0 ? "down" : ""} style={{ height: `${height}%` }}/>)}</div><footer><span>开仓价差率 <b>-0.16%</b></span><span>平仓价差率 <b>-0.09%</b></span><span>资金费差 <b>0.0100%</b></span></footer></article><aside><h4>双腿下单</h4><div className="arb-segments">{["双边市价", "左挂右市", "双边超价"].map((name) => <button className={orderType === name ? "on" : ""} key={name} onClick={() => setOrderType(name)}>{name}</button>)}</div><div className="arb-segments">{["同金额", "同数量"].map((name) => <button className={amountMode === name ? "on" : ""} key={name} onClick={() => setAmountMode(name)}>{name}</button>)}</div><label>单腿金额<div><input aria-label="专业套利下单金额" value={amount} onChange={(event) => setAmount(event.target.value)} inputMode="decimal"/><span>USDT</span></div></label><div className="arb-order-summary"><p><span>{selected.leftSide}</span><b>{selected.left}</b></p><p><span>{selected.rightSide}</span><b>{selected.right}</b></p></div><button onClick={() => openOverlay("basketPreview", "双腿订单预览", { description: "仅预览专业套利双腿参数，不会发送真实委托。", orders: [{ pair: selected.left, side: selected.leftSide, type: orderType, amount }, { pair: selected.right, side: selected.rightSide, type: orderType, amount }], estimatedTotal: `${(Number(amount || 0) * 2).toFixed(2)} USDT` })}>预览双腿</button><button className="primary" onClick={simulateOrder}>模拟双腿下单</button></aside></div>
          <div className="professional-orders"><header><b>本地模拟记录</b>{orders.length > 0 && <button onClick={() => { setOrders([]); say("专业套利模拟记录已清空"); }}>清空记录</button>}</header>{orders.length ? orders.map((item) => <div key={item.id}><span><b>{item.name}</b><small>{item.time} · {item.orderType} · {item.amountMode}</small></span><strong>{item.amount} USDT × 2</strong><em>{item.status}</em><button onClick={() => setOrders(orders.filter((order) => order.id !== item.id))}>删除</button></div>) : <p>暂无模拟订单，提交前可先预览双腿参数。</p>}</div>
        </> : <div className="strategy-empty"><I.ArrowsLeftRight/><h3>先创建一个套利组合</h3><button onClick={() => setEditing(true)}>新增组合</button></div>}
      </main>
    </section>
  );
}
function Strategy({
  tab,
  say,
  openOverlay,
  savedStrategies,
  setSavedStrategies,
  authorizedAccounts,
  strategyCategory: category,
  setStrategyCategory: setCategory,
}) {
  const [arbType, setArbType] = useState(tab);
  const [strategySearch, setStrategySearch] = useState("");
  const [arbPlatform, setArbPlatform] = useState("全部平台");
  const [arbContract, setArbContract] = useState("全部合约");
  const [arbFavorites, setArbFavorites] = useStoredState("ai-trading-assistant-arb-favorites", []);
  useEffect(() => {
    setCategory(1);
    setArbType(tab);
    setStrategySearch("");
    setArbPlatform("全部平台");
    setArbContract("全部合约");
  }, [tab]);
  const rows = [
    ["XRP", "XRP/USD 币安 ↔ 欧易OKX 永续", "10.95%", "0.0100%", "0.00%", "4823.24万", "5天", "7.97%"],
    ["PEPE", "PEPE/USDT 欧易OKX ↔ 币安 永续", "7.17%", "0.0087%", "0.00%", "1785.26万", "7天", "7.46%"],
    ["HBAR", "HBAR/USDT 币安 次季", "4.55%", "0.0055%", "0.00%", "2355.62万", "11天", "-3.62%"],
    ["XRP", "XRP/USDT 欧易OKX 永续", "1.82%", "0.0022%", "0.00%", "7428.33万", "27天", "3.14%"],
    ["BNB", "BNB/USDT 欧易OKX 当季", "0.73%", "0.0008%", "+0.06%", "3.30亿", "65天", "6.83%"],
    ["LINK", "LINK/USDT 欧易OKX 永续", "0.61%", "0.0007%", "0.00%", "1660.47万", "78天", "5.57%"],
    ["PENDLE", "PENDLE/USDT 币安 永续", "0.60%", "0.0007%", "0.00%", "1374.36万", "80天", "7.11%"],
  ];
  const favoriteKey = (row) => `${row[0]}|${row[1]}`;
  const visibleArbitrageRows = rows.filter((row, index) => {
    const matchesSearch = row[0].toLowerCase().includes(strategySearch.toLowerCase()) || row[1].toLowerCase().includes(strategySearch.toLowerCase());
    const matchesPlatform = arbPlatform === "全部平台" || row[1].includes(arbPlatform);
    const matchesContract = arbContract === "全部合约" || (arbContract === "永续" ? row[1].includes("永续") : row[1].includes("次季") || row[1].includes("当季"));
    const matchesType = arbType === "收藏"
      ? arbFavorites.includes(favoriteKey(row))
      : arbType === "正向套利"
        ? !row[7].startsWith("-")
        : arbType === "反向套利"
          ? row[7].startsWith("-") || index === 3
          : arbType === "跨所永续"
            ? row[1].includes("↔")
            : arbType === "永续-期货"
              ? row[1].includes("次季") || row[1].includes("当季")
              : arbType === "价差-期现"
                ? [1, 5, 6].includes(index)
                : true;
    return matchesSearch && matchesPlatform && matchesContract && matchesType;
  });
  const strategyHeading =
    category === 1 ? tab : stratSide[category][0];
  const channelDescriptions = {
    "自动赚币": "投 U 自动赚 U，程序根据资金费率执行本地模拟套利",
    "套利机会": "发现不同平台与合约之间的收益机会",
    "专业套利": "配置左右腿币对、方向与双腿订单参数",
    "我的套利": "管理已创建的套利组合与运行状态",
    "我的策略": "交易笔记、AI 分析与双向关联知识图谱",
  };
  return (
    <div className="strategy-full">
      <aside>
        {stratSide.map((x, i) => (
          <button
            key={x[0]}
            className={category === i ? "on" : ""}
            onClick={() => setCategory(i)}
          >
            <I.Robot />
            <span>
              <b>{x[0]}</b>
              <small>{x[1]}</small>
            </span>
            {i === 1 || i === 2 ? <em>HOT</em> : null}
          </button>
        ))}
      </aside>
      <main>
        <div className="strategy-channel-head">
          <h2>{strategyHeading}</h2>
          <span>
            {category !== 1
              ? stratSide[category][1]
              : channelDescriptions[tab]}
          </span>
        </div>
        {category === 1 && tab === "套利机会" && <div className="strategy-sub">
          {[
            tab,
            "正向套利",
            "反向套利",
            "跨所永续",
            "永续-期货",
            "价差-期现",
            "收藏",
          ].map((x) => (
            <button
              key={x}
              className={arbType === x ? "on" : ""}
              onClick={() => setArbType(x)}
            >
              {x}
            </button>
          ))}
          <input
            value={strategySearch}
            onChange={(e) => setStrategySearch(e.target.value)}
            placeholder="输入筛选币种"
          />
          <select aria-label="套利平台筛选" value={arbPlatform} onChange={(event) => setArbPlatform(event.target.value)}>
            <option>全部平台</option>
            <option>币安</option>
            <option>欧易OKX</option>
          </select>
          <select aria-label="套利合约筛选" value={arbContract} onChange={(event) => setArbContract(event.target.value)}>
            <option>全部合约</option>
            <option>永续</option>
            <option>期货</option>
          </select>
        </div>}
        {category === 0 ? (
          <StrategyNotebook say={say} setSavedStrategies={setSavedStrategies} />
        ) : category === 1 && tab === "我的套利" ? (
          savedStrategies.length ? (
            <div className="saved-strategies">
              {savedStrategies.map((s) => (
                <article key={s.id}>
                  <i>{s.coin.slice(0, 2)}</i>
                  <span>
                    <b>{s.name}</b>
                    <small>
                      {s.coin}/USDT · {s.type} · {s.amount} USDT
                    </small>
                  </span>
                  <em className={s.status === "已暂停" ? "paused" : ""}>
                    {s.status || "运行中"}
                  </em>
                  <button
                    onClick={() => {
                      const status =
                        s.status === "已暂停" ? "运行中" : "已暂停";
                      setSavedStrategies(
                        savedStrategies.map((item) =>
                          item.id === s.id ? { ...item, status } : item,
                        ),
                      );
                      say(`${s.name} ${status}`);
                    }}
                  >
                    {s.status === "已暂停" ? "恢复" : "暂停"}
                  </button>
                  <button
                    onClick={() =>
                      openOverlay("strategyCreate", "编辑策略", { strategy: s })
                    }
                  >
                    编辑
                  </button>
                  <button
                    className="danger-text"
                    onClick={() => {
                      setSavedStrategies(
                        savedStrategies.filter((item) => item.id !== s.id),
                      );
                      say(`${s.name} 已删除`);
                    }}
                  >
                    删除
                  </button>
                </article>
              ))}
            </div>
          ) : (
            <div className="strategy-empty">
              <I.Robot />
              <h3>暂无运行中的套利</h3>
              <button
                onClick={() =>
                  openOverlay("strategyCreate", "创建套利策略", {
                    strategy: { coin: "BTC", type: "正向套利" },
                  })
                }
              >
                发现套利机会
              </button>
            </div>
          )
        ) : category !== 1 ? (
          category === 7 || category === 8
            ? <CapitalTracker mode={category === 7 ? "main" : "hot"} say={say} setSavedStrategies={setSavedStrategies} />
            : <StrategyProductWorkbench category={category} openOverlay={openOverlay} say={say} authorizedAccounts={authorizedAccounts} />
        ) : tab === "自动赚币" ? (
          <AutoEarnPanel openOverlay={openOverlay} say={say} favorites={arbFavorites} setFavorites={setArbFavorites} />
        ) : tab === "专业套利" ? (
          <ProfessionalArbitragePanel openOverlay={openOverlay} say={say} />
        ) : (
          <div className="arb-table">
            <header>
              <span>币种</span>
              <span>费率组合</span>
              <span>当前年化</span>
              <span>当前费率</span>
              <span>价差率</span>
              <span>持仓价值($)</span>
              <span>预估回本</span>
              <span>7日年化</span>
              <span>7日费率走势</span>
              <span>操作</span>
            </header>
            {visibleArbitrageRows.map((r) => (
                <div key={favoriteKey(r)}>
                  <b>{r[0]}</b>
                  <span>
                    卖出 {r[1]}
                    <small>买入 {r[1]}</small>
                  </span>
                  <strong>{r[2]}</strong>
                  <em>{r[3]}</em>
                  <em>{r[4]}</em>
                  <span className="position-value">{r[5]}<small>--</small></span>
                  <span>{r[6]}</span>
                  <strong className={r[7][0] === "-" ? "loss" : ""}>
                    {r[7]}
                  </strong>
                  <i className="spark" />
                  <span className="arb-actions">
                    <button
                      aria-label={`${arbFavorites.includes(favoriteKey(r)) ? "取消收藏" : "收藏"}${r[0]}套利`}
                      className={arbFavorites.includes(favoriteKey(r)) ? "favorite on" : "favorite"}
                      onClick={() => {
                        const key = favoriteKey(r);
                        const exists = arbFavorites.includes(key);
                        setArbFavorites(exists ? arbFavorites.filter((item) => item !== key) : [...arbFavorites, key]);
                        say(exists ? `${r[0]} 套利已取消收藏` : `${r[0]} 套利已收藏`);
                      }}
                    >
                      <I.Star weight={arbFavorites.includes(favoriteKey(r)) ? "fill" : "regular"}/>
                    </button>
                    <button
                      onClick={() =>
                        openOverlay("strategyCreate", "创建套利策略", {
                          strategy: {
                            coin: r[0],
                            type: arbType === "收藏" ? "正向套利" : arbType,
                            annualized: r[2],
                          },
                        })
                      }
                    >
                      立即套利
                    </button>
                  </span>
                </div>
              ))}
            {!visibleArbitrageRows.length && (
              <div className="arb-empty">
                <I.Star />
                <b>{arbType === "收藏" ? "暂无收藏的套利机会" : "当前筛选下暂无套利机会"}</b>
                <button onClick={() => { setArbType(tab); setStrategySearch(""); setArbPlatform("全部平台"); setArbContract("全部合约"); }}>清除筛选</button>
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}

function Assets({ tab, openOverlay, assetGroups, setAssetGroups, say }) {
  const [assetGroup, setAssetGroup] = useState(0);
  const [currency, setCurrency] = useState("USDT");
  const [assetRange, setAssetRange] = useState("7天");
  const [assetMetric, setAssetMetric] = useState("资产走势");
  const [detailTab, setDetailTab] = useState("币种分布");
  const [hideSmallOverview, setHideSmallOverview] = useState(false);
  const assetGroupName = assetGroup < 3
    ? ["全部资产", "套利专用资产", "合约专用资产"][assetGroup]
    : assetGroups[assetGroup - 3]?.name || "全部资产";
  return (
    <div className="assets-full">
      <aside>
        <button
          className={assetGroup === 0 ? "on" : ""}
          onClick={() => setAssetGroup(0)}
        >
          <b>全部资产</b>
          <i>$</i>
        </button>
        <button
          className={assetGroup === 1 ? "on" : ""}
          onClick={() => setAssetGroup(1)}
        >
          <b>套利专用资产</b>
          <i>套</i>
        </button>
        <button
          className={assetGroup === 2 ? "on" : ""}
          onClick={() => setAssetGroup(2)}
        >
          <b>合约专用资产</b>
          <i>合</i>
        </button>
        {assetGroups.map((group, i) => (
          <div key={group.id} className="asset-group-row">
            <button
              className={assetGroup === i + 3 ? "on" : ""}
              onClick={() => setAssetGroup(i + 3)}
            >
              <b>{group.name}</b>
              <i>{group.name.slice(0, 1)}</i>
            </button>
            <button
              className="asset-group-delete"
              aria-label={`删除${group.name}`}
              onClick={() => {
                setAssetGroups(
                  assetGroups.filter((item) => item.id !== group.id),
                );
                setAssetGroup(0);
                say(`${group.name} 已删除`);
              }}
            >
              <I.X />
            </button>
          </div>
        ))}
        <button
          className="add"
          onClick={() =>
            openOverlay("addGroup", "添加资产组合", {
              description: "创建自定义资产组合并选择账户。",
            })
          }
        >
          + 添加组合
        </button>
      </aside>
      <main>
        {tab === "总览" ? (
          <>
            <div className="asset-cards">
              <article className="blue">
                <header>
                  {assetGroupName}{" "}
                  <button
                    onClick={() =>
                      setCurrency(currency === "USDT" ? "CNY" : "USDT")
                    }
                  >
                    {currency}⌄
                  </button>
                </header>
                <h2>
                  {currency === "USDT" ? "$" : "￥"} -- <I.Eye />
                </h2>
                <div>
                  <span>
                    今日盈亏<b>-- 0%</b>
                  </span>
                  <span>
                    历史盈亏<b>-- 0%</b>
                  </span>
                </div>
                <footer>
                  <b>正常</b>
                  <span>资产异动　账号状态　资产日报　流水明细</span>
                </footer>
              </article>
              <article>
                <header>
                  <button
                    onClick={() =>
                      setAssetMetric(
                        assetMetric === "资产走势" ? "盈亏走势" : "资产走势",
                      )
                    }
                  >
                    {assetMetric}⌄
                  </button>
                  <span className="asset-ranges">
                    {["7天", "30天", "3月", "半年"].map((x) => (
                      <button
                        key={x}
                        className={assetRange === x ? "on" : ""}
                        onClick={() => setAssetRange(x)}
                      >
                        {x}
                      </button>
                    ))}
                  </span>
                </header>
                <div className="asset-empty">
                  <I.ChartLine />
                  {assetRange}暂无{assetMetric}数据，选择其他时间
                </div>
              </article>
              <article>
                <header>
                  持有 0 币种
                  <button onClick={() => setDetailTab("币种分布")}>更多 ›</button>
                </header>
                <div className="donut-empty" />
              </article>
            </div>
            <div className="asset-detail">
              <nav>
                {["币种分布", "API账号分布", "盈亏日历", "流水", "风控"].map(
                  (x) => (
                    <button
                      key={x}
                      className={detailTab === x ? "on" : ""}
                      onClick={() => setDetailTab(x)}
                    >
                      {x}
                    </button>
                  ),
                )}
                <label>
                  <input
                    type="checkbox"
                    checked={hideSmallOverview}
                    onChange={(e) => setHideSmallOverview(e.target.checked)}
                  />
                  隐藏小额资产
                </label>
              </nav>
              <div>
                <I.Receipt />
                暂无{detailTab}
                {hideSmallOverview ? <small>已隐藏小额资产</small> : null}
              </div>
            </div>
          </>
        ) : (
          <AssetSection tab={tab} />
        )}
      </main>
    </div>
  );
}
function AssetSection({ tab }) {
  const [accountFilter, setAccountFilter] = useState("全部账户");
  const [hideSmall, setHideSmall] = useState(false);
  const [sectionFilter, setSectionFilter] = useState("全部");
  useEffect(() => {
    setAccountFilter("全部账户");
    setHideSmall(false);
    setSectionFilter("全部");
  }, [tab]);
  const configs = {
    币种分布: ["币种", "数量", "折合(USDT)", "今日盈亏", "持币价值走势"],
    API账号分布: ["平台/账号", "账户类型", "资产(USDT)", "状态", "更新时间"],
    盈亏日历: ["日期", "当日盈亏", "收益率", "累计盈亏", "备注"],
    流水: ["时间", "平台", "币种", "类型", "金额"],
    风控: ["检查项", "状态", "说明", "更新时间", "操作"],
  }[tab];
  const dataRows = {
    币种分布: [["BTC", "0.0521", "$3,426.14", "+$84.20", "震荡上行"], ["ETH", "0.8200", "$2,601.22", "+$42.18", "温和上行"], ["USDT", "5,000.00", "$5,000.00", "$0.00", "稳定"], ["SOL", "0.1800", "$26.70", "-$1.12", "高波动"]],
    API账号分布: [["币安主账户", "现货/合约", "$8,420.18", "正常", "刚刚"], ["OKX套利账户", "现货", "$2,481.20", "正常", "1分钟前"], ["Bybit观察账户", "只读", "$152.68", "待复核", "5分钟前"]],
    盈亏日历: [["07-22", "+$126.38", "+1.02%", "+$842.14", "BTC反弹"], ["07-21", "-$48.20", "-0.39%", "+$715.76", "手续费增加"], ["07-20", "+$82.16", "+0.67%", "+$763.96", "ETH上涨"], ["07-19", "+$15.42", "+0.13%", "+$681.80", "震荡"]],
    流水: [["22:41", "币安", "BTC", "现货买入", "+0.002 BTC"], ["21:18", "OKX", "USDT", "账户划转", "+500 USDT"], ["18:06", "币安", "ETH", "手续费", "-0.0002 ETH"], ["16:32", "Bybit", "USDT", "资金费率", "+1.82 USDT"]],
    风控: [["API权限", "正常", "未开启提现权限", "刚刚", "查看"], ["资产异动", "正常", "无异常变动", "1分钟前", "设置"], ["账号状态", "待复核", "1个只读账户延迟", "5分钟前", "详情"]],
  }[tab];
  let visibleRows = dataRows;
  if (["API账号分布", "流水"].includes(tab) && accountFilter !== "全部账户") visibleRows = visibleRows.filter((row)=>row.join(" ").includes(accountFilter.replace("账户", "")));
  if (tab === "币种分布" && hideSmall) visibleRows = visibleRows.filter((row)=>parseFloat(String(row[2]).replace(/[^\d.]/g,"")) >= 50);
  if (tab === "盈亏日历" && sectionFilter === "盈利日") visibleRows = visibleRows.filter((row)=>String(row[1]).startsWith("+"));
  if (tab === "盈亏日历" && sectionFilter === "亏损日") visibleRows = visibleRows.filter((row)=>String(row[1]).startsWith("-"));
  if (tab === "风控" && sectionFilter === "异常") visibleRows = visibleRows.filter((row)=>row[1] !== "正常");
  return (
    <div className="asset-section">
      <div className="channel-title">
        <h1>{tab}</h1>
        <div>
          {["API账号分布", "流水"].includes(tab) && ["全部账户", "币安账户", "OKX账户"].map((name)=><button key={name} className={accountFilter===name?"on":""} onClick={()=>setAccountFilter(name)}>{name}</button>)}
          {tab === "币种分布" && <button className={hideSmall ? "on" : ""} onClick={() => setHideSmall(!hideSmall)}>{hideSmall ? "已隐藏小额资产" : "隐藏小额资产"}</button>}
          {tab === "盈亏日历" && ["全部", "盈利日", "亏损日"].map((name)=><button key={name} className={sectionFilter===name?"on":""} onClick={()=>setSectionFilter(name)}>{name}</button>)}
          {tab === "风控" && ["全部", "异常"].map((name)=><button key={name} className={sectionFilter===name?"on":""} onClick={()=>setSectionFilter(name)}>{name}</button>)}
        </div>
      </div>
      <section className="asset-section-summary"><span><small>当前视图</small><b>{tab}</b></span><span><small>记录数</small><b>{visibleRows.length}</b></span><span><small>数据状态</small><b className="green">本地模拟已同步</b></span></section>
      {visibleRows.length ? <Table heads={configs} rows={visibleRows} /> : <div className="market-empty"><I.Funnel/><b>当前筛选下暂无记录</b><button onClick={()=>{setAccountFilter("全部账户");setSectionFilter("全部");setHideSmall(false)}}>清除筛选</button></div>}
    </div>
  );
}

function Auth({
  tab,
  say,
  openOverlay,
  authorizedAccounts,
  setAuthorizedAccounts,
}) {
  const [authSearch, setAuthSearch] = useState("");
  const [safetyExpanded, setSafetyExpanded] = useState("必要权限");
  const [revokeTarget, setRevokeTarget] = useState(null);
  const exchanges = [
    ["币安 Binance", "现货、杠杆、U本位合约"],
    ["欧易 OKX", "现货、永续、期权"],
    ["Bitget", "现货、合约"],
    ["Bybit", "现货、合约"],
    ["Gate", "现货、合约"],
  ];
  if (tab === "已授权账户")
    return (
      <div className="auth-list">
        <div className="channel-title">
          <h1>已授权账户</h1>
          <button
            className="solid"
            onClick={() => openOverlay("apiAuth", "添加 API 授权")}
          >
            + 添加授权
          </button>
        </div>
        {authorizedAccounts.length ? (
          <div className="authorized-list">
            {authorizedAccounts.map((account) => (
              <article key={account.id}>
                <i>{account.platform.slice(0, 1)}</i>
                <span>
                  <b>{account.alias}</b>
                  <small>{account.platform} · 读取/交易权限</small>
                </span>
                <em>{account.status}</em>
                <small>{account.checkedAt ? `刚刚检查 · ${account.checkedAt}` : account.createdAt}</small>
                <button
                  className={account.checkedAt ? "checked" : ""}
                  onClick={() => {
                    const checkedAt = new Date().toLocaleTimeString("zh-CN", {
                      hour: "2-digit",
                      minute: "2-digit",
                    });
                    setAuthorizedAccounts(
                      authorizedAccounts.map((item) =>
                        item.id === account.id
                          ? { ...item, status: "连接正常", checkedAt }
                          : item,
                      ),
                    );
                    say(`${account.alias} 连接正常`);
                  }}
                >
                  检查
                </button>
                <button
                  className="danger-text"
                  onClick={() => setRevokeTarget(account)}
                >
                  撤销
                </button>
              </article>
            ))}
            {revokeTarget && <div className="auth-revoke-confirm"><I.Warning/><span><b>确认撤销 {revokeTarget.alias}？</b><small>撤销后将停止同步该账户的资产、委托和策略状态。</small></span><button onClick={()=>setRevokeTarget(null)}>取消</button><button className="danger" onClick={()=>{setAuthorizedAccounts(authorizedAccounts.filter((item)=>item.id!==revokeTarget.id));say(`${revokeTarget.alias} 已撤销授权`);setRevokeTarget(null)}}>确认撤销</button></div>}
          </div>
        ) : (
          <div className="auth-empty">
            <I.Key />
            <h2>暂无授权平台</h2>
            <p>授权后即可统一查看资产并使用交易工具</p>
            <button
              className="solid"
              onClick={() => openOverlay("apiAuth", "添加 API 授权")}
            >
              立即添加授权
            </button>
          </div>
        )}
      </div>
    );
  if (tab === "安全说明")
    return (
      <div className="security-page">
        <I.ShieldCheck />
        <h1>API 授权安全说明</h1>
        <p>按最小权限原则管理交易所连接，演示环境不会把密钥写入本地存储。</p>
        <section className="security-accordions">
          {[
            ["必要权限", "建议只授予读取和交易权限，切勿开启提现或转账权限。"],
            ["信息边界", "当前复刻只保存平台、别名、状态和创建日期；API Key 与 Secret 仅用于当次界面校验。"],
            ["随时撤销", "可在本页或交易所后台撤销 API，连接会立即失效。"],
            ["IP 白名单", "如交易所支持，请将 API 绑定固定 IP 并定期检查登录与下单记录。"],
          ].map((x) => (
            <button
              key={x[0]}
              className={safetyExpanded === x[0] ? "on" : ""}
              onClick={() => setSafetyExpanded(safetyExpanded === x[0] ? "" : x[0])}
            >
              <span><b>{x[0]}</b><I.CaretDown /></span>
              {safetyExpanded === x[0] ? <p>{x[1]}</p> : null}
            </button>
          ))}
        </section>
        <button className="solid" onClick={() => openOverlay("apiAuth", "添加 API 授权")}>
          添加安全授权
        </button>
      </div>
    );
  return (
    <div className="auth-full">
      <section>
        <I.Link />
        <h1>连接您的交易所账户</h1>
        <p>通过 API 授权后，可在 AI交易助手 查看资产、快捷下单和运行策略。</p>
        <div className="security">
          <I.ShieldCheck />
          <span>
            <b>只授予读取和交易权限</b>
            <small>切勿开启提现/转账权限</small>
          </span>
        </div>
      </section>
      <main>
        <header>
          <h2>添加授权</h2>
          <input
            value={authSearch}
            onChange={(e) => setAuthSearch(e.target.value)}
            placeholder="搜索 可授权平台"
          />
        </header>
        {exchanges
          .filter((x) => x[0].toLowerCase().includes(authSearch.toLowerCase()))
          .map((x, i) => (
          <article key={x[0]}>
            <i>{x[0].slice(0, 1)}</i>
            <span>
              <b>{x[0]}</b>
              <small>{x[1]}</small>
            </span>
            <em>{i < 2 ? "推荐" : ""}</em>
            <button
              onClick={() =>
                openOverlay("apiAuth", "添加 API 授权", {
                  platform: x[0].split(" ")[0],
                })
              }
            >
              添加授权
            </button>
          </article>
        ))}
        {exchanges.filter((x) => x[0].toLowerCase().includes(authSearch.toLowerCase())).length === 0 ? (
          <div className="auth-no-result">未找到“{authSearch}”对应的平台</div>
        ) : null}
      </main>
    </div>
  );
}

function ModulePage({ page, tab, go, say, openOverlay }) {
  const [contextIndex, setContextIndex] = useState(0);
  const [filterOn, setFilterOn] = useState(false);
  const [sortDesc, setSortDesc] = useState(true);
  const [selectedRow, setSelectedRow] = useState(null);
  const data = {
    flash: {
      side: ["全部快讯", "只看重要", "事件日历", "我的关注"],
      title: "实时快讯",
      rows: news,
    },
    chain: {
      side: ["关注", "巨鲸", "聪明钱", "KOL", "机构"],
      title: "聪明钱追踪",
      rows: [
        ["18:02", "0x71…8A 增持 1,840 ETH", "巨鲸", "30D胜率 91%"],
        ["17:46", "Smart Whale 08 新开 BTC 多单", "聪明钱", "收益 +84%"],
        ["16:58", "Macro Fund 转入 1.2 亿 USDT", "机构", "余额 $480M"],
      ],
    },
    data: {
      side: ["加密货币储备", "Hyperliquid", "数据来源"],
      title: "储备数据",
      rows: [
        ["Bitcoin (BTC)", "4.19M BTC", "总储备", "$267.9B"],
        ["Ethereum (ETH)", "12.8M ETH", "总储备", "$40.6B"],
        ["7天 BTC 变化", "+2.2K BTC", "净买入", "366 实体"],
      ],
    },
    more: {
      side: ["钱包", "宏观", "自定义导航", "帮助中心"],
      title: "更多工具",
      rows: [
        ["钱包", "地址和资产管理", "工具", "打开"],
        ["宏观", "全球市场与经济数据", "数据", "打开"],
        ["自定义导航", "整理常用功能入口", "设置", "管理"],
      ],
    },
  }[page];
  const channelRows =
    page === "flash"
      ? news.map((x, i) => [x[0], `${tab}｜${x[1]}`, tab, x[3]])
      : page === "chain"
        ? [
            [
              tab === "Hyperliquid" ? "Hyperliquid Whale" : "0x71…8A",
              `${tab} 最新大额活动`,
              tab,
              "30D胜率 91%",
            ],
            ["Smart Whale 08", `${tab} 新开 BTC 多单`, "聪明钱", "收益 +84%"],
            ["Macro Fund", `${tab} 资金转移 1.2 亿 USDT`, "机构", "余额 $480M"],
          ]
        : page === "data"
          ? tab === "Hyperliquid"
            ? [
                ["总持仓", "$12.8B", "Hyperliquid", "+4.2%"],
                ["24H成交额", "$6.4B", "永续合约", "+8.7%"],
                ["巨鲸活动", "128次", "过去24H", "实时"],
              ]
            : data.rows
          : page === "more"
            ? [
                [tab, `${tab}功能与相关工具`, "功能", "打开"],
                ["常用入口", `${tab}常用操作`, "快捷方式", "管理"],
                ["使用帮助", `了解如何使用${tab}`, "帮助", "查看"],
              ]
            : data.rows;
  const channelTitle =
    page === "flash"
      ? `${tab}快讯`
      : page === "chain"
        ? `${tab}追踪`
        : page === "data"
          ? `${tab}数据`
          : page === "more"
            ? tab
            : data.title;
  const visibleRows = (filterOn ? channelRows.slice(0, 2) : channelRows)
    .slice()
    .sort((a, b) => (sortDesc ? 0 : String(a[0]).localeCompare(String(b[0]))));
  return (
    <div className="module">
      <aside className="context">
        <h3>{META[page].title}</h3>
        {data.side.map((x, i) => (
          <button
            key={x}
            className={contextIndex === i ? "on" : ""}
            onClick={() => setContextIndex(i)}
          >
            {x}
            <I.CaretRight />
          </button>
        ))}
      </aside>
      <section className="module-main">
        <div className="module-head">
          <div>
            <small>{tab}</small>
            <h1>{channelTitle}</h1>
            <p>AI交易助手 实时数据与功能工作台</p>
          </div>
          <div>
            <button
              className={filterOn ? "on" : ""}
              onClick={() => setFilterOn(!filterOn)}
            >
              <I.Funnel />
              筛选
            </button>
            <button onClick={() => setSortDesc(!sortDesc)}>
              <I.ArrowsDownUp />
              排序
            </button>
            <button
              className="solid"
              onClick={() => openOverlay("create", `新建${channelTitle}`)}
            >
              <I.Plus />
              新建
            </button>
          </div>
        </div>
        <div className="module-table">
          <header>
            <span>名称 / 时间</span>
            <span>内容</span>
            <span>类型 / 状态</span>
            <span>指标</span>
            <span />
          </header>
          {visibleRows.map((r, i) => (
            <button
              key={`${r[0]}-${r[1]}`}
              className={selectedRow === i ? "selected" : ""}
              onClick={() => setSelectedRow(i)}
            >
              <span>
                <i>{i + 1}</i>
                {r[0]}
              </span>
              <b>{r[1]}</b>
              <em>{r[2]}</em>
              <strong>{r[3]}</strong>
              <I.CaretRight />
            </button>
          ))}
        </div>
      </section>
      <aside className="inspector">
        <h3>{tab}详情</h3>
        {selectedRow === null ? (
          <>
            <small>选择一项查看完整数据、来源和相关操作。</small>
            <div className="empty-inspect">
              <I.CursorClick />
              <p>选择一条记录</p>
            </div>
          </>
        ) : (
          <div className="inspect-detail">
            <b>{visibleRows[selectedRow]?.[1]}</b>
            <p>类型：{visibleRows[selectedRow]?.[2]}</p>
            <p>指标：{visibleRows[selectedRow]?.[3]}</p>
            <button onClick={() => say("已加入关注")}>加入关注</button>
            <button onClick={() => setSelectedRow(null)}>关闭详情</button>
          </div>
        )}
      </aside>
    </div>
  );
}

const RT = [
  ["depth", "订单表与最新成交", I.ListNumbers],
  ["news", "最新资讯", I.Newspaper],
  ["funds", "资金流向", I.Money],
  ["analysis", "技术分析", I.TrendUp],
  ["feature", "特色数据", I.ChartBar],
  ["etf", "ETF数据", I.Bank],
  ["ai", "Ace Agent", I.Robot],
];
function RightRail({ page, drawer, setDrawer, openOverlay, sidebarMode, setSidebarMode, openAI, say, marketSideTab, setMarketSideTab, marketSideOpen, setMarketSideOpen, marketOrderOpen, setMarketOrderOpen }) {
  const layoutOpen = drawer === "sidebarLayout";
  const chooseLayout = (mode) => {
    setSidebarMode(mode);
    setDrawer(null);
    say(mode === "professional" ? "已切换专业侧栏" : "已切换经典侧栏");
  };
  const chooseMarketPanel = (id) => {
    if (marketSideOpen && marketSideTab === id) setMarketSideOpen(false);
    else {
      setMarketSideTab(id);
      setMarketSideOpen(true);
    }
  };
  return (
    <aside className="right-rail">
      {RT.map(([id, n, Icon]) => (
        <button
          key={id}
          aria-label={n}
          title={n}
          className={page === "market" ? (marketSideOpen && marketSideTab === id ? "on" : "") : (drawer === id ? "on" : "")}
          onClick={() => page === "market" ? chooseMarketPanel(id) : setDrawer(drawer === id ? null : id)}
        >
          <Icon />
          {id === "tasks" && <em>3</em>}
        </button>
      ))}
      <button
        aria-label="下单面板"
        title="下单面板"
        className={page === "market" ? (marketOrderOpen ? "on" : "") : (drawer === "trade" ? "on" : "")}
        onClick={() => page === "market" ? (setMarketSideOpen(true), setMarketOrderOpen(!marketOrderOpen)) : setDrawer(drawer === "trade" ? null : "trade")}
      >
        <I.ArrowsLeftRight />
      </button>
      <div />
      <button
        aria-label="侧栏布局"
        title="侧栏布局"
        className={layoutOpen ? "on" : ""}
        onClick={() => setDrawer(layoutOpen ? null : "sidebarLayout")}
      >
        <I.SquaresFour />
      </button>
      {layoutOpen && (
        <section className="sidebar-layout-popover" aria-label="侧栏布局选择">
          <b>侧栏布局</b>
          <div>
            <button className={sidebarMode === "classic" ? "on" : ""} onClick={() => chooseLayout("classic")}>
              <span><i className="radio" />经典侧栏</span>
              <em className="layout-preview classic"><i/><i/><i/><i/></em>
            </button>
            <button className={sidebarMode === "professional" ? "on" : ""} onClick={() => chooseLayout("professional")}>
              <span><i className="radio" />专业侧栏</span>
              <em className="layout-preview professional"><i/><i/><i/><i/></em>
            </button>
          </div>
        </section>
      )}
      <button aria-label="联系客服" title="联系客服" onClick={() => openOverlay("help", "在线客服与帮助中心")}>
        <I.Headset />
      </button>
      <button aria-label="AI智能分析" title="AI智能分析" onClick={openAI}>
        <I.Robot />
      </button>
    </aside>
  );
}
function UtilityDrawer({ type, close, go, say, watch, setWatch, marketSymbol = "BTC", prefill, openOverlay, openDrawer, authorizedAccounts = [], sidebarMode = "professional", embedded = false }) {
  if (type === "sidebarLayout") return null;
  const title = type === "layout" ? "组件列表" : type === "trade" ? "下单面板" : type === "info" ? "币种简况" : RT.find((x) => x[0] === type)?.[1];
  const [tradeSide, setTradeSide] = useState("买入");
  const [tradeOrderType, setTradeOrderType] = useState("限价");
  const [agentPrompt, setAgentPrompt] = useState("");
  const [agentResult, setAgentResult] = useState("");
  const [agentMode, setAgentMode] = useState("Agent");
  const [agentBatch, setAgentBatch] = useState(0);
  const [selectedAgentCard, setSelectedAgentCard] = useState(null);
  const [orderPanelTab, setOrderPanelTab] = useState("下单");
  const [orderTool, setOrderTool] = useState(null);
  const [tradeForm, setTradeForm] = useState({ price: "", quantity: "" });
  const [simulatedOrders, setSimulatedOrders] = useStoredState("ai-trading-assistant-quick-orders", []);
  const quote = quoteFor(marketSymbol);
  const marketPrice = quote.price;
  const estimatedTradeValue = (tradeOrderType === "市价" ? marketPrice : Number(tradeForm.price)) * Number(tradeForm.quantity || 0);
  useEffect(() => {
    if (!prefill || type !== "trade") return;
    setTradeSide(prefill.side || "买入");
    setTradeOrderType("限价");
    setTradeForm((current) => ({ ...current, price: prefill.price || "" }));
  }, [prefill, type]);
  const agentCards = [
    ["山寨轮动", "追踪BTC资金外溢到山寨币的轮动规律，在山寨季初期布局高弹性标的。", "90%", "SOL/USDT", "4小时", "中风险", "9次触发"],
    ["Meme币狙击", "监控社交媒体热度和链上巨鲸动向，快速捕捉Meme币的早期上涨机会。", "86%", "PEPE/USDT", "1小时", "高风险", "10次触发"],
    ["宏观事件", "追踪美联储利率决议、CPI数据等宏观事件，在数据公布前后进行方向性交易。", "82%", "BTC/USDT", "1日", "中风险", "6次触发"],
    ["突破回踩", "识别关键阻力突破后的回踩确认，结合成交量判断趋势延续概率。", "88%", "ETH/USDT", "4小时", "中风险", "8次触发"],
  ];
  const shownAgentCards = agentCards
    .slice(agentBatch % 2, agentBatch % 2 + 3);
  const professionalTabs = [
    ["depth", "盘口"],
    ["funds", "资金"],
    ["news", "消息"],
    ["analysis", "分析"],
  ];
  const instrumentTitle = `${marketSymbol}/USDT`;
  const isWatched = watch.includes(marketSymbol);
  return (
    <aside className={`${embedded ? "market-side-embedded" : "drawer"} ${type === "ai" ? "ai-drawer" : ""} ${sidebarMode === "professional" ? "professional-drawer" : "classic-drawer"}`}>
      <header>
        <span><small>{instrumentTitle}</small><b>{title}</b></span>
        {type === "ai" ? (
          <div className="agent-modes">
            {["Agent", "Chat"].map((x) => (
              <button
                key={x}
                className={agentMode === x ? "on" : ""}
                onClick={() => setAgentMode(x)}
              >
                {x}
              </button>
            ))}
          </div>
        ) : null}
        <button aria-label="关闭工具面板" onClick={close}>
          <I.X />
        </button>
      </header>
      {type !== "ai" && type !== "trade" && sidebarMode === "professional" && (
        <section className="professional-instrument">
          <div className="professional-quote">
            <span><i>{marketSymbol.slice(0, 1)}</i><b>{instrumentTitle}</b></span>
            <strong>{formatPrice(marketPrice, quote.decimals)} <em>{quote.change}</em></strong>
          </div>
          <div className="professional-actions">
            <button onClick={() => openOverlay("alertCenter", "预警中心", { symbol: instrumentTitle, price: String(marketPrice) })}>加预警</button>
            <button onClick={() => openDrawer("feature")}>主力</button>
            <button className={isWatched ? "on" : ""} onClick={() => { setWatch(isWatched ? watch.filter((coin) => coin !== marketSymbol) : [...watch, marketSymbol]); say(isWatched ? `${marketSymbol} 已移出自选` : `${marketSymbol} 已加入自选`); }}>{isWatched ? "已自选" : "加自选"}</button>
            <button onClick={() => openDrawer("info")}>简况</button>
          </div>
          <nav>{professionalTabs.map(([id, label]) => <button key={id} className={type === id ? "on" : ""} onClick={() => openDrawer(id)}>{label}</button>)}</nav>
        </section>
      )}
      {type === "ai" ? (
        <div className="agent-shell">
          <div className="ai-orb">
            <I.Sparkle />
          </div>
          <h2>{agentMode === "Agent" ? "用一句话，让 AI 帮你交易" : "和 Ace 聊聊当前市场"}</h2>
          <p>你的私有交易 Agent，描述你的买卖逻辑，AI 24 小时盯盘并生成执行草稿。无需编程，无需量化背景。</p>
          <button
            className="agent-create"
            onClick={() => { close(); go("strategy"); }}
          >
            创建我的策略
          </button>
          <div className="agent-card-head">
            <span>试试这些策略：</span>
            <button onClick={() => setAgentBatch(agentBatch + 1)}>↻ 换一批</button>
          </div>
          <div className="agent-cards">
            {shownAgentCards.map((card) => (
              <button
                key={card[0]}
                className={selectedAgentCard === card[0] ? "on" : ""}
                onClick={() => {
                  setSelectedAgentCard(card[0]);
                  setAgentPrompt(card[1]);
                }}
              >
                <b>{card[0]}</b>
                <p>{card[1]}</p>
                <span>AI预测未来胜率</span>
                <strong>{card[2]}</strong>
                <i className="agent-spark" />
                <footer>{card.slice(3).map((x) => <em key={x}>{x}</em>)}</footer>
              </button>
            ))}
          </div>
          <div className="agent-prompt">
            <textarea
              value={agentPrompt}
              onChange={(e) => setAgentPrompt(e.target.value)}
              placeholder="问行情、分析K线或描述一个策略…"
            />
            <button
              aria-label="提交 Ace Agent 问题"
              onClick={() => {
                if (!agentPrompt.trim()) return say("请先描述策略或分析问题");
                setAgentResult(
                  `已理解：${agentPrompt}。${marketSymbol} 短线保持震荡，${formatPrice(marketPrice * 0.994, quote.decimals)} 为首要支撑，${formatPrice(marketPrice * 1.006, quote.decimals)} 上方确认突破后再提高仓位。`,
                );
                say("Ace Agent 已生成分析");
              }}
            >
              ↑
            </button>
          </div>
          {agentResult && (
            <div className="agent-result">
              <b>Ace Agent</b>
              <p>{agentResult}</p>
              <button
                onClick={() => {
                  close();
                  go("strategy");
                }}
              >
                打开策略页
              </button>
            </div>
          )}
        </div>
      ) : type === "trade" ? (
        <div className="professional-order-panel">
          <nav className="professional-order-tabs">
            {["下单", "抢新开盘", "特色"].map((name) => <button key={name} className={orderPanelTab === name ? "on" : ""} onClick={() => { setOrderPanelTab(name); setOrderTool(null); }}>{name}</button>)}
            <button aria-label="下单设置" onClick={() => openOverlay("settings", "下单设置")}><I.Gear/></button>
          </nav>
          {orderPanelTab === "下单" ? (authorizedAccounts.length ? <>
          <h2>{marketSymbol}/USDT <small>已关联 {authorizedAccounts.length} 个本地授权记录</small></h2>
          <div className="quick-trade">
            <button
              className={tradeSide === "买入" ? "on buy" : ""}
              onClick={() => setTradeSide("买入")}
            >
              买入
            </button>
            <button
              className={tradeSide === "卖出" ? "on sell" : ""}
              onClick={() => setTradeSide("卖出")}
            >
              卖出
            </button>
            <div className="quick-order-types">
              {["限价", "市价"].map((name) => (
                <button
                  key={name}
                  className={tradeOrderType === name ? "on" : ""}
                  onClick={() => {
                    setTradeOrderType(name);
                    if (name === "市价") setTradeForm({ ...tradeForm, price: "" });
                  }}
                >
                  {name}
                </button>
              ))}
            </div>
            <input
              aria-label="快捷交易价格"
              value={tradeForm.price}
              onChange={(e) =>
                setTradeForm({ ...tradeForm, price: e.target.value })
              }
              placeholder={tradeOrderType === "市价" ? `市价 ≈ ${marketPrice}` : "价格 USDT"}
              disabled={tradeOrderType === "市价"}
            />
            <input
              aria-label="快捷交易数量"
              value={tradeForm.quantity}
              onChange={(e) =>
                setTradeForm({ ...tradeForm, quantity: e.target.value })
              }
              placeholder={`数量 ${marketSymbol}`}
            />
            <div className="quick-percentages">
              {[25, 50, 75, 100].map((percent) => (
                <button
                  key={percent}
                  onClick={() => setTradeForm({ ...tradeForm, quantity: (0.01 * percent / 100).toFixed(4) })}
                >
                  {percent}%
                </button>
              ))}
            </div>
            <output>
              预估金额
              <b>{Number.isFinite(estimatedTradeValue) ? estimatedTradeValue.toFixed(2) : "0.00"} USDT</b>
            </output>
            <button
              className="drawer-primary"
              onClick={() => {
                if (
                  (tradeOrderType === "限价" && Number(tradeForm.price) <= 0) ||
                  Number(tradeForm.quantity) <= 0
                )
                  return say("请输入有效价格和数量");
                const orderPrice = tradeOrderType === "市价" ? marketPrice.toFixed(2) : tradeForm.price;
                setSimulatedOrders([
                  {
                    id: Date.now(),
                    side: tradeSide,
                    type: tradeOrderType,
                    price: orderPrice,
                    quantity: tradeForm.quantity,
                    symbol: marketSymbol,
                    status: tradeOrderType === "市价" ? "模拟成交" : "等待成交",
                    createdAt: new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
                  },
                  ...simulatedOrders,
                ]);
                setTradeForm({ price: "", quantity: "" });
                say("模拟订单已加入委托列表");
              }}
            >
              {tradeSide}模拟下单
            </button>
          </div>
          <div className="sim-orders">
            <header>
              <b>本地模拟委托</b>
              <span>
                <small>{simulatedOrders.length} 笔</small>
                {simulatedOrders.length > 0 && (
                  <button onClick={() => { setSimulatedOrders([]); say("本地模拟委托已清空"); }}>全部清空</button>
                )}
              </span>
            </header>
            {simulatedOrders.length ? (
              simulatedOrders.map((order) => (
                <article key={order.id}>
                  <em className={order.side === "买入" ? "buy" : "sell"}>
                    {order.side}
                  </em>
                  <span><b>{order.quantity} {order.symbol || "BTC"}</b><small>{order.type || "限价"} · {order.createdAt || "本地"}</small></span>
                  <span><b>{order.price}</b><small>{order.status || "等待成交"}</small></span>
                  <button
                    onClick={() => {
                      if (order.status === "等待成交") {
                        setSimulatedOrders(simulatedOrders.map((item) => item.id === order.id ? { ...item, status: "已撤销", canceledAt: new Date().toLocaleTimeString("zh-CN") } : item));
                        say("模拟委托已撤销并归入历史");
                      } else {
                        setSimulatedOrders(simulatedOrders.filter((item) => item.id !== order.id));
                        say("模拟记录已删除");
                      }
                    }}
                  >
                    {order.status === "等待成交" ? "撤单" : "删除"}
                  </button>
                </article>
              ))
            ) : (
              <p>暂无模拟委托</p>
            )}
          </div>
          </> : <div className="order-auth-hub">
            <span className="auth-badge">未授权</span>
            <h3>行情来了，多账户一键跟上</h3>
            <p>授权 API 后，可统一管理多个交易所账号，按比例同步下单。当前复刻不会保存或发送真实密钥。</p>
            <div className="order-auth-tools">
              {[
                ["抢新开盘", "开盘抢先", "新币上线前预设条件，开盘触发高频抢单", I.RocketLaunch],
                ["多账户下单", "多号同步", "授权多个 API 后，一键同步下单与分仓", I.UsersThree],
                ["三键下单", "短线提速", "买多、卖空、平仓聚合操作，减少切换成本", I.Lightning],
                ["智能拆单", "降低滑点", "大额订单拆小随机执行，减少对盘口冲击", I.Stack],
              ].map(([name, badge, desc, Icon]) => <button key={name} className={orderTool === name ? "on" : ""} onClick={() => setOrderTool(name)}><Icon/><span><em>{badge}</em><b>{name}</b><small>{desc}</small></span></button>)}
            </div>
            {orderTool && <div className="order-tool-preview"><b>{orderTool}</b><p>{orderTool === "抢新开盘" ? "设置开盘时间、价格保护和最大重试次数；授权后才可进入确认。" : orderTool === "多账户下单" ? "创建账户分组并设置跟单/分仓比例；提交前逐账户预览。" : orderTool === "三键下单" ? "配置买多、卖空、平仓三键数量和二次确认。" : "配置总量、单笔随机范围、间隔与价格保护。"}</p><button onClick={() => setOrderPanelTab(orderTool === "抢新开盘" ? "抢新开盘" : "特色")}>查看配置</button></div>}
            <button className="drawer-primary" onClick={() => openOverlay("apiAuth", "添加 API 授权")}>已有账户，立即授权</button>
            <button className="auth-manage-link" onClick={() => { close(); go("auth"); }}>查看授权管理</button>
          </div>) : orderPanelTab === "抢新开盘" ? <div className="first-open-panel">
            <I.RocketLaunch/>
            <h3>抢新开盘</h3>
            <p>新币上线前预设开盘时间、最大价格和重试规则。这里只保存本地草稿，不会自动向交易所发送委托。</p>
            <label>交易对<input value={`${marketSymbol}/USDT`} readOnly/></label>
            <label>开盘时间<input type="datetime-local"/></label>
            <label>最高可接受价格<input inputMode="decimal" placeholder={`参考 ${formatPrice(marketPrice, quote.decimals)}`}/></label>
            <label>重试次数<select defaultValue="20"><option>10</option><option>20</option><option>50</option></select></label>
            <button className="drawer-primary" onClick={() => authorizedAccounts.length ? say("抢新开盘草稿已保存，提交前仍需人工确认") : openOverlay("apiAuth", "授权后使用抢新开盘")}>{authorizedAccounts.length ? "保存本地草稿" : "授权后继续"}</button>
          </div> : <div className="featured-order-tools">
            <h3>特色交易工具</h3>
            <p>专业侧栏内统一配置，所有动作先生成本地预览。</p>
            {["多账户下单", "三键下单", "智能拆单", "画线下单"].map((name) => <button key={name} className={orderTool === name ? "on" : ""} onClick={() => setOrderTool(name)}><span><b>{name}</b><small>{name === "多账户下单" ? "跟单 / 分仓 / 跨所预览" : name === "三键下单" ? "买多 / 卖空 / 平仓" : name === "智能拆单" ? "TWAP / VWAP / 随机拆分" : "委托线 / 持仓线 / 拖动改单"}</small></span><I.CaretRight/></button>)}
            {orderTool && <div className="order-tool-config"><b>{orderTool}配置</b><label>模式<select><option>本地模拟</option><option disabled>真实账户（未启用）</option></select></label><label>风险确认<select><option>每次提交前确认</option><option>仅保存草稿</option></select></label><button onClick={() => authorizedAccounts.length ? say(`${orderTool}配置已保存`) : openOverlay("apiAuth", `授权后使用${orderTool}`)}>{authorizedAccounts.length ? "保存配置" : "授权后继续"}</button></div>}
          </div>}
        </div>
      ) : (
        <RailPanel
          type={type}
          say={say}
          go={go}
          watch={watch}
          setWatch={setWatch}
          symbol={marketSymbol}
        />
      )}
    </aside>
  );
}
function RailPanel({ type, say, go, watch, setWatch, symbol = "BTC" }) {
  const quote = quoteFor(symbol);
  const tick = quote.decimals > 2 ? 0.0001 : 0.01;
  const [active, setActive] = useState(0);
  const [enabled, setEnabled] = useStoredState(
    "ai-trading-assistant-rail-layout",
    [0, 1, 2, 3],
  );
  const [layoutSaved, setLayoutSaved] = useState(true);
  const [selectedPrice, setSelectedPrice] = useState("");
  const [selectedEtf, setSelectedEtf] = useState(null);
  const [assistantQuestion, setAssistantQuestion] = useState("");
  const [assistantAnswer, setAssistantAnswer] = useState("");
  const [selectedNews, setSelectedNews] = useState(null);
  if (type === "layout") {
    const modules = [
      "盘口",
      "最新成交",
      "资金流",
      "主力挂单",
      "合约数据",
      "新闻快讯",
    ];
    return (
      <div className="rail-panel">
        <p className="drawer-note">管理行情页右侧组件</p>
        {modules.map((x, i) => (
          <button
            key={x}
            className={enabled.includes(i) ? "enabled" : ""}
            onClick={() => {
              setEnabled(
                enabled.includes(i)
                  ? enabled.filter((n) => n !== i)
                  : [...enabled, i],
              );
              setLayoutSaved(false);
            }}
          >
            <I.DotsSixVertical />
            <span>{x}</span>
            <i className={enabled.includes(i) ? "switch on" : "switch"} />
          </button>
        ))}
        <button
          className={layoutSaved ? "drawer-primary saved" : "drawer-primary"}
          onClick={() => {
            setLayoutSaved(true);
            say("组件布局已保存");
          }}
        >
          {layoutSaved ? "布局已保存" : "保存布局"}
        </button>
      </div>
    );
  }
  if (type === "assistant")
    return (
      <div className="rail-panel rail-assistant">
        <div className="assistant-intro"><I.ChatTeardropDots/><span><b>AI 行情助手</b><small>结合当前 K 线、盘口与资金数据回答</small></span></div>
        <div className="rail-tabs">
          {["行情问答", "指标帮助", "功能导航"].map((name, index) => (
            <button key={name} className={active === index ? "on" : ""} onClick={() => { setActive(index); setAssistantAnswer(""); }}>{name}</button>
          ))}
        </div>
        <div className="assistant-suggestions">
          {(active === 0 ? [`${symbol} 当前支撑位？`, "主力资金方向如何？", "现在波动风险高吗？"] : active === 1 ? ["MACD 金叉怎么判断？", "如何添加主力大单？", "解释资金费率指标"] : ["怎么创建价格预警？", "打开自定义指标", "管理我的自选"]).map((question) => (
            <button key={question} onClick={() => setAssistantQuestion(question)}>{question}</button>
          ))}
        </div>
        <textarea value={assistantQuestion} onChange={(event) => setAssistantQuestion(event.target.value)} placeholder="输入你的问题…" />
        <button className="drawer-primary" onClick={() => {
          if (!assistantQuestion.trim()) return say("请输入问题");
          setAssistantAnswer(active === 0 ? `${symbol} 短线支撑关注 ${formatPrice(quote.price * 0.994, quote.decimals)}；${formatPrice(quote.price * 1.006, quote.decimals)} 上方放量才确认突破。` : active === 1 ? "已结合当前 5 分钟图说明指标含义，可在顶部“指标”菜单切换显示。" : "已找到对应入口，可从行情工具栏、底部工作台或右侧组件直接打开。");
          say("AI助手已生成回答");
        }}>发送问题</button>
        {assistantAnswer && <div className="assistant-answer"><b>AI助手</b><p>{assistantAnswer}</p>{active === 2 && <button onClick={() => go(assistantQuestion.includes("指标") ? "market" : "market")}>前往行情工作区</button>}</div>}
      </div>
    );
  if (type === "analysis") {
    const analysisPeriods = ["5分", "15分", "1时", "4时"];
    const scores = [[36,"卖出"],[42,"中性偏空"],[58,"中性偏多"],[64,"买入"]];
    const current = scores[active] || scores[0];
    return (
      <div className="rail-panel rail-analysis">
        <div className="rail-tabs">{analysisPeriods.map((name,index)=><button key={name} className={active===index?"on":""} onClick={()=>setActive(index)}>{name}</button>)}</div>
        <div className="technical-gauge"><small>综合技术评分</small><strong>{current[0]}</strong><b>{current[1]}</b></div>
        {["移动平均线","震荡指标","趋势强度","成交量"].map((name,index)=><p className="rail-row" key={name}><span>{name}</span><b className={index===0?"red":index===3?"green":""}>{index===0?"强力卖出":index===1?"中性":index===2?"偏弱":"放量"}</b></p>)}
        <div className="analysis-levels"><span>支撑<b>{formatPrice(quote.price * 0.994, quote.decimals)}</b></span><span>阻力<b>{formatPrice(quote.price * 1.006, quote.decimals)}</b></span></div>
        <button className="drawer-primary" onClick={()=>go("market")}>在 K 线查看指标</button>
      </div>
    );
  }
  if (type === "depth") {
    const sellRows = [[formatPrice(quote.price + tick * 5, quote.decimals),"0.18900","12.10K"],[formatPrice(quote.price + tick * 4, quote.decimals),"0.00018","11.52"],[formatPrice(quote.price + tick * 2, quote.decimals),"0.05122","3.279K"]];
    const buyRows = [[formatPrice(quote.price - tick, quote.decimals),"5.46979","350.176K"],[formatPrice(quote.price - tick * 2, quote.decimals),"0.33251","21.287K"],[formatPrice(quote.price - tick * 3, quote.decimals),"4.85931","311.093K"]];
    const trades = [[formatPrice(quote.price - tick, quote.decimals),"0.04210","19:14:22"],[formatPrice(quote.price, quote.decimals),"0.00100","19:14:21"],[formatPrice(quote.price - tick * 3, quote.decimals),"0.00932","19:14:18"]];
    return (
      <div className="rail-panel rail-depth">
        <div className="rail-tabs">{["盘口","最新成交"].map((name,index)=><button key={name} className={active===index?"on":""} onClick={()=>setActive(index)}>{name}</button>)}</div>
        {active===0?<><div className="depth-ratio"><span>委比 <b>+56.75%</b></span><span>委差 <b>+23.30996</b></span></div><div className="mini-order-head"><b>价格</b><b>数量({symbol})</b><b>委托额</b></div>{sellRows.map((row)=><button className="mini-order sell" key={row[0]} onClick={()=>{setSelectedPrice(row[0]);say(`已定位卖盘 ${row[0]}`)}}>{row.map(value=><span key={value}>{value}</span>)}</button>)}<strong className="mid-price">{formatPrice(quote.price, quote.decimals)}</strong>{buyRows.map((row)=><button className="mini-order buy" key={row[0]} onClick={()=>{setSelectedPrice(row[0]);say(`已定位买盘 ${row[0]}`)}}>{row.map(value=><span key={value}>{value}</span>)}</button>)}</>:<><div className="mini-order-head"><b>价格</b><b>数量({symbol})</b><b>成交时间</b></div>{trades.map((row,index)=><button className={`mini-order ${index%2?"buy":"sell"}`} key={row[2]} onClick={()=>{setSelectedPrice(row[0]);say(`已选中 ${row[2]} 成交`)}}>{row.map(value=><span key={value}>{value}</span>)}</button>)}</>}
        {selectedPrice && <div className="rail-selection"><small>已选价格</small><b>{selectedPrice} USDT</b></div>}
      </div>
    );
  }
  if (type === "info")
    return (
      <div className="rail-panel coin-info">
        <div className="coin-identity">
          <i>{symbol.slice(0, 1)}</i>
          <span>
            <b>{symbol}</b>
            <small>{symbol} · 数字资产</small>
          </span>
          <button
            className={watch.includes(symbol) ? "on" : ""}
            onClick={() => {
              const exists = watch.includes(symbol);
              setWatch(
                exists
                  ? watch.filter((coin) => coin !== symbol)
                  : [...watch, symbol],
              );
              say(exists ? `${symbol} 已移出自选` : `${symbol} 已加入自选`);
            }}
          >
            <I.Star weight={watch.includes(symbol) ? "fill" : "regular"} />
            {watch.includes(symbol) ? "已自选" : "自选"}
          </button>
        </div>
        {[
          ["市值", "$1.28万亿"],
          ["流通量", "19.72M BTC"],
          ["最大供应量", "21M BTC"],
          ["市值排名", "#1"],
          ["24H成交额", "$21.8亿"],
        ].map((x) => (
          <p key={x[0]}>
            <span>{x[0]}</span>
            <b>{x[1]}</b>
          </p>
        ))}
        <button
          className="drawer-primary"
          onClick={() => {
            go("news");
          }}
        >
          查看币种资料
        </button>
      </div>
    );
  if (type === "feature") {
    const featureTabs = ["主力挂单", "合约", "链上"];
    const featureRows = active === 0
      ? [[formatPrice(quote.price * 1.006, quote.decimals),"卖墙","$12.4M"],[formatPrice(quote.price * 0.997, quote.decimals),"买墙","$9.1M"],[formatPrice(quote.price * 0.992, quote.decimals),"买墙","$14.8M"]]
      : active === 1
        ? [["全网持仓","$19.4B","+2.8%"],["24H爆仓","$182M","多单 58%"],["资金费率","0.0079%","偏多"]]
        : [["交易所净流入",`${quote.inflow} ${symbol}`,"流出"],["巨鲸地址活跃","286","+12%"],["稳定币增发","$420M","24H"]];
    return (
      <div className="rail-panel rail-feature">
        <div className="rail-tabs">{featureTabs.map((name,index)=><button key={name} className={active===index?"on":""} onClick={()=>{setActive(index);setSelectedPrice("")}}>{name}</button>)}</div>
        <div className="feature-hero"><small>{featureTabs[active]}</small><strong>{active===0?"主力看空":active===1?"多空分歧":"链上流出"}</strong><span>{active===0?"挂单差 -$43.56M":active===1?"多空比 1.62":"24H 净流出 1,248 BTC"}</span></div>
        {featureRows.map((row)=><button className={selectedPrice===row[0]?"rail-order selected":"rail-order"} key={row[0]} onClick={()=>setSelectedPrice(row[0])}><b>{row[0]}</b><em>{row[1]}</em><span>{row[2]}</span></button>)}
        <button className="drawer-primary" onClick={()=>go(active===2?"chain":"data")}>打开完整数据</button>
      </div>
    );
  }
  if (type === "news") {
    const newsTabs = ["快讯", "要闻", "自选相关"];
    const allNews = active === 0
      ? [["2分钟前",`${symbol} 触及 ${formatPrice(quote.price, quote.decimals)} USDT，短线成交量放大`,`${symbol} ${quote.change}`],["8分钟前","美联储官员重申将依据数据决定利率路径","宏观"],["15分钟前","现货 BTC ETF 单日净流入 2.84 亿美元","ETF"]]
      : active === 1
        ? [["专题","市场等待通胀数据，风险资产波动升温","宏观观察"],["研究",`从交易所储备看本轮 ${symbol} 抛压`,"链上数据"],["复盘","主力挂单与价格背离的三个信号","交易研究"]]
        : [[symbol,`${symbol} 关键支撑附近出现大额承接`,"当前标的"],["ETH","ETH 资金费率回到中性区间","自选"]];
    return (
      <div className="rail-panel rail-news">
        <div className="rail-tabs">{newsTabs.map((name,index)=><button key={name} className={active===index?"on":""} onClick={()=>{setActive(index);setSelectedNews(null)}}>{name}</button>)}</div>
        {allNews.map((item)=><button className={selectedNews?.[1]===item[1]?"rail-news-item selected":"rail-news-item"} key={item[1]} onClick={()=>setSelectedNews(item)}><small>{item[0]} · {item[2]}</small><b>{item[1]}</b></button>)}
        {selectedNews && <div className="news-preview"><small>{selectedNews[0]} · {selectedNews[2]}</small><h3>{selectedNews[1]}</h3><p>已结合当前行情整理关键信息；打开对应页面可查看完整时间线、来源与关联标的。</p></div>}
        <button className="drawer-primary" onClick={()=>go(active===0?"flash":"news")}>查看全部{newsTabs[active]}</button>
      </div>
    );
  }
  if (type === "funds")
    return (
      <div className="rail-panel">
        <div className="rail-tabs">
          {["5分钟", "1小时", "24小时"].map((x, i) => (
            <button
              key={x}
              className={active === i ? "on" : ""}
              onClick={() => setActive(i)}
            >
              {x}
            </button>
          ))}
        </div>
        <div className="flow-summary">
          <small>主力净流入</small>
          <strong className={active === 0 ? "red" : "green"}>
            {active === 0 ? "-$70万" : active === 1 ? "+$420万" : "+$2,860万"}
          </strong>
          <div>
            <i style={{ width: "58%" }} />
          </div>
          <span>流入 $1.42亿　流出 $1.13亿</span>
        </div>
        <h4>资金流明细</h4>
        {[
          ["超大单", "+$820万"],
          ["大单", "+$1,240万"],
          ["中单", "-$560万"],
          ["小单", "-$300万"],
        ].map((x) => (
          <p key={x[0]} className="rail-row">
            <span>{x[0]}</span>
            <b>{x[1]}</b>
          </p>
        ))}
      </div>
    );
  if (type === "flow")
    return (
      <div className="rail-panel">
        <p className="drawer-note">{symbol} 主力24H挂单</p>
        <div className="flow-summary">
          <small>主力方向</small>
          <strong className="red">主力看空</strong>
          <span>多空比 1.62　挂单差 $43.56亿</span>
        </div>
        {[
          [formatPrice(quote.price * 1.006, quote.decimals), "卖墙", "$12.4M"],
          [formatPrice(quote.price * 1.003, quote.decimals), "卖墙", "$8.7M"],
          [formatPrice(quote.price * 0.997, quote.decimals), "买墙", "$9.1M"],
          [formatPrice(quote.price * 0.992, quote.decimals), "买墙", "$14.8M"],
        ].map((x, i) => (
          <button
            key={x[0]}
            className={
              selectedPrice === x[0] ? "rail-order selected" : "rail-order"
            }
            onClick={() => {
              setSelectedPrice(x[0]);
              say(`已定位到价格 ${x[0]}`);
            }}
          >
            <b>{x[0]}</b>
            <em className={i < 2 ? "sell" : "buy"}>{x[1]}</em>
            <span>{x[2]}</span>
          </button>
        ))}
        {selectedPrice && (
          <div className="rail-selection">
            <small>图表十字线已定位</small>
            <b>{selectedPrice} USDT</b>
          </div>
        )}
      </div>
    );
  if (type === "chart")
    return (
      <div className="rail-panel">
        <div className="rail-tabs">
          {["价格", "持仓量", "资金费率"].map((x, i) => (
            <button
              key={x}
              className={active === i ? "on" : ""}
              onClick={() => setActive(i)}
            >
              {x}
            </button>
          ))}
        </div>
        <div className="mini-chart">
          <svg viewBox="0 0 280 140" preserveAspectRatio="none">
            <polyline
              points={
                active === 0
                  ? "0,110 30,95 55,100 80,62 110,75 145,48 180,62 210,34 245,42 280,20"
                  : "0,85 35,92 70,60 105,66 140,38 175,58 210,40 245,66 280,45"
              }
            />
          </svg>
        </div>
        <p className="rail-row">
          <span>当前</span>
          <b>
            {active === 0 ? formatPrice(quote.price, quote.decimals) : active === 1 ? "$82.6亿" : "0.0081%"}
          </b>
        </p>
        <button
          className="drawer-primary"
          onClick={() => {
            go("data");
          }}
        >
          打开数据中心
        </button>
      </div>
    );
  return (
    <div className="rail-panel">
      <p className="drawer-note">美国现货 BTC ETF</p>
      <div className="flow-summary">
        <small>今日净流入</small>
        <strong className="green">+$284.6M</strong>
        <span>总资产净值 $128.4B</span>
      </div>
      {[
        ["IBIT", "+$182.4M"],
        ["FBTC", "+$68.2M"],
        ["ARKB", "+$24.7M"],
        ["GBTC", "-$12.1M"],
      ].map((x, i) => (
        <button
          key={x[0]}
          className={
            selectedEtf?.[0] === x[0] ? "rail-order selected" : "rail-order"
          }
          onClick={() => setSelectedEtf(x)}
        >
          <b>{x[0]}</b>
          <span className={x[1][0] === "-" ? "red" : "green"}>{x[1]}</span>
          <I.CaretRight />
        </button>
      ))}
      {selectedEtf && (
        <div className="etf-detail">
          <small>ETF 资金详情</small>
          <h3>{selectedEtf[0]}</h3>
          <p>
            今日净流入 <b>{selectedEtf[1]}</b>
          </p>
          <p>连续净流入 4 日 · 资产占比 42.6%</p>
        </div>
      )}
    </div>
  );
}

function NotificationCenterPanel({ close, say, go }) {
  const initialItems = [
    { id: 1, type: "价格", title: "BTC 价格触达 64,000", detail: "BTC/USDT 在币安永续触达预警价 64,000，当前价 64,020.04。", time: "1分钟前", read: false },
    { id: 2, type: "策略", title: "主力挂单发生变化", detail: "64,400 附近卖墙增加 820 万美元，主力挂单差转为 -1,240 万美元。", time: "3分钟前", read: false },
    { id: 3, type: "宏观", title: "美国 CPI 将在 20:30 公布", detail: "市场预计同比 2.8%，发布前后可能出现流动性收缩和滑点扩大。", time: "18分钟前", read: true },
    { id: 4, type: "系统", title: "行情线路已切换至线路3", detail: "当前线路延迟 42ms，数据订阅与本地工作区均保持正常。", time: "1小时前", read: true },
  ];
  const [items, setItems] = useStoredState("ai-trading-assistant-notifications", initialItems);
  const [filter, setFilter] = useState("全部");
  const [selected, setSelected] = useState(null);
  const visible = filter === "全部" ? items : items.filter((item) => item.type === filter);
  const openItem = (item) => {
    setItems(items.map((current) => current.id === item.id ? { ...current, read: true } : current));
    setSelected(item);
  };
  return (
    <div className="notification-center-panel">
      <nav>{["全部", "价格", "策略", "宏观", "系统"].map((name) => <button className={filter === name ? "on" : ""} key={name} onClick={() => { setFilter(name); setSelected(null); }}>{name}</button>)}<span /> <button onClick={() => { setItems(items.map((item) => ({ ...item, read: true }))); say("通知已全部标记为已读"); }}>全部已读</button></nav>
      <div className="notification-layout">
        <section>{visible.map((item) => <button className={item.read ? "read" : ""} key={item.id} onClick={() => openItem(item)}><i /><span><small>{item.type} · {item.time}</small><b>{item.title}</b><em>{item.detail}</em></span><I.CaretRight /></button>)}{!visible.length && <div className="utility-empty"><I.BellSlash/><b>当前分类暂无通知</b></div>}</section>
        <aside>{selected ? <><small>{selected.type}通知</small><h3>{selected.title}</h3><p>{selected.detail}</p><div className="detail-facts"><span>触发时间<b>{selected.time}</b></span><span>状态<b>已读</b></span></div><button onClick={() => { close(); go(["价格", "策略"].includes(selected.type) ? "market" : "flash"); }}>查看关联内容</button></> : <><I.CursorClick/><b>选择通知查看详情</b><small>{items.filter((item) => !item.read).length} 条未读</small></>}</aside>
      </div>
    </div>
  );
}

function MessageCenterPanel({ say }) {
  const [tab, setTab] = useState("消息通知");
  const [selected, setSelected] = useState(null);
  const data = {
    "消息通知": [
      ["系统消息", "数据服务运行正常", "全部行情订阅已恢复，当前延迟 42ms。", "刚刚"],
      ["策略提醒", "套利费率已更新", "XRP 正向套利预测年化更新为 10.95%。", "12分钟前"],
      ["版本更新", "AI交易助手 2.16.10", "当前版本已完成专业行情工作区升级。", "昨天"],
    ],
    "账户活动": [
      ["登录活动", "桌面端会话保持在线", "设备：Mac · 新加坡线路 · 本地演示账户。", "18分钟前"],
      ["授权检查", "API 权限检查完成", "未发现提现或转账权限；演示密钥未持久化。", "2小时前"],
      ["工作区", "图表布局已自动保存", "保存 2 个图表标签和当前指标配置。", "昨天"],
    ],
  };
  return (
    <div className="message-center-panel">
      <nav>{Object.keys(data).map((name) => <button className={tab === name ? "on" : ""} key={name} onClick={() => { setTab(name); setSelected(null); }}>{name}</button>)}</nav>
      <section>{data[tab].map((item) => <button className={selected?.[1] === item[1] ? "on" : ""} key={item[1]} onClick={() => setSelected(item)}><I.EnvelopeSimple/><span><small>{item[0]} · {item[3]}</small><b>{item[1]}</b><em>{item[2]}</em></span><I.CaretRight/></button>)}</section>
      {selected && <aside><button aria-label="关闭消息详情" onClick={() => setSelected(null)}><I.X/></button><small>{selected[0]}</small><h3>{selected[1]}</h3><p>{selected[2]}</p><button onClick={async () => { try { await navigator.clipboard.writeText(`${selected[1]}\n${selected[2]}`); say("消息内容已复制"); } catch { say("无法访问剪贴板，请手动复制"); } }}>复制内容</button></aside>}
    </div>
  );
}

function SystemSettingsPanel({ prefs, setPrefs, close, say }) {
  const sections = ["通用", "K线设置", "下单设置", "预警", "快讯弹窗", "策略通知", "市场异动", "消息中心", "Webhook"];
  const [section, setSection] = useState("通用");
  const settingDefaults = {
    theme: "浅色", scale: "100%", redUp: prefs.redUp ?? false, minimize: true, autoUpdate: true,
    candle: "K线图", realtimePrice: true, countdown: true, grid: true, costLine: true, depthBars: prefs.showDepthBars ?? true,
    orderConfirm: true, priceCheck: true, quickOrder: false, cancelConfirm: true,
    alertEnabled: true, alertSound: "AI交易助手预警", alertVolume: "70", alertLoop: false,
    flashPopup: true, flashImportant: true, flashSound: false,
    strategyRunning: true, strategyError: true, strategyProfit: false,
    movementRise: "5", movementFall: "5", movementVolume: true,
    messageNotice: true, accountActivity: true,
  };
  const [settings, setSettings] = useStoredState("ai-trading-assistant-system-settings", settingDefaults);
  const [webhook, setWebhook] = useState("");
  const [webhooks, setWebhooks] = useStoredState("ai-trading-assistant-webhooks", []);
  const toggle = (key) => setSettings({ ...settings, [key]: !settings[key] });
  const resetSection = () => {
    const keys = {
      "通用": ["theme", "scale", "redUp", "minimize", "autoUpdate"],
      "K线设置": ["candle", "realtimePrice", "countdown", "grid", "costLine", "depthBars"],
      "下单设置": ["orderConfirm", "priceCheck", "quickOrder", "cancelConfirm"],
      "预警": ["alertEnabled", "alertSound", "alertVolume", "alertLoop"],
      "快讯弹窗": ["flashPopup", "flashImportant", "flashSound"],
      "策略通知": ["strategyRunning", "strategyError", "strategyProfit"],
      "市场异动": ["movementRise", "movementFall", "movementVolume"],
      "消息中心": ["messageNotice", "accountActivity"],
      "Webhook": [],
    }[section];
    setSettings({ ...settings, ...Object.fromEntries(keys.map((key) => [key, settingDefaults[key]])) });
    if (section === "Webhook") setWebhooks([]);
    say(`${section}已恢复默认`);
  };
  const switchRow = (key, title, description) => <button className="setting-switch-row" onClick={() => toggle(key)}><span><b>{title}</b><small>{description}</small></span><i className={settings[key] ? "switch on" : "switch"}/></button>;
  let content;
  if (section === "通用") content = <><div className="setting-field"><span><b>主题</b><small>切换应用整体外观</small></span><select value={settings.theme} onChange={(event) => setSettings({ ...settings, theme: event.target.value })}><option>浅色</option><option>深色</option><option>跟随系统</option></select></div><div className="setting-field"><span><b>软件缩放</b><small>修改后刷新工作区生效</small></span><select value={settings.scale} onChange={(event) => setSettings({ ...settings, scale: event.target.value })}><option>90%</option><option>100%</option><option>110%</option><option>125%</option></select></div>{switchRow("redUp", "红涨绿跌", "关闭时使用绿涨红跌")}{switchRow("minimize", "关闭时最小化至托盘", "保持策略和提醒在本地运行")}{switchRow("autoUpdate", "自动检查更新", "启动时检查版本与资源")}</>;
  else if (section === "K线设置") content = <><div className="setting-field"><span><b>K线样式</b><small>应用于所有图表窗口</small></span><select value={settings.candle} onChange={(event) => setSettings({ ...settings, candle: event.target.value })}><option>K线图</option><option>K线图 (HLC)</option><option>美国线</option><option>收盘价线</option><option>平均K线</option></select></div>{switchRow("realtimePrice", "实时价格线", "显示价格线和价格标签")}{switchRow("countdown", "K线结束倒计时", "在实时价格旁显示倒计时")}{switchRow("grid", "水平与垂直辅助线", "保持图表坐标网格")}{switchRow("costLine", "持仓成本线", "授权账户后显示平均成本")}{switchRow("depthBars", "盘口深度背景条", "在买卖档位后显示累计委托强度")}</>;
  else if (section === "下单设置") content = <>{switchRow("orderConfirm", "下单二次确认", "提交前再次核对方向、价格和数量")}{switchRow("priceCheck", "下单价格检查", "超出盘口合理范围时阻止提交")}{switchRow("quickOrder", "闪电下单", "一键生成市价单，默认关闭")}{switchRow("cancelConfirm", "撤单二次确认", "批量撤单前显示账户与订单范围")}<div className="settings-warning"><I.ShieldWarning/>当前服务仅保存本地偏好，不发送真实订单。</div></>;
  else if (section === "预警") content = <>{switchRow("alertEnabled", "预警推送", "接收价格、指标和链上预警")}<div className="setting-field"><span><b>预警铃声</b><small>选择本地提示音</small></span><select value={settings.alertSound} onChange={(event) => setSettings({ ...settings, alertSound: event.target.value })}><option>AI交易助手预警</option><option>上涨铃声</option><option>下跌铃声 1</option><option>平缓铃声</option></select></div><label className="setting-range">铃声音量 <input type="range" min="0" max="100" value={settings.alertVolume} onChange={(event) => setSettings({ ...settings, alertVolume: event.target.value })}/><output>{settings.alertVolume}%</output></label>{switchRow("alertLoop", "循环播放", "直到手动关闭预警")}</>;
  else if (section === "快讯弹窗") content = <>{switchRow("flashPopup", "显示快讯弹窗", "在桌面右上角展示重要快讯")}{switchRow("flashImportant", "只弹出重要快讯", "过滤普通资讯与重复事件")}{switchRow("flashSound", "快讯声音", "重要事件出现时播放提示音")}</>;
  else if (section === "策略通知") content = <>{switchRow("strategyRunning", "运行状态", "策略启动、暂停与恢复")}{switchRow("strategyError", "异常与风控", "下单失败、断网或触发风险限制")}{switchRow("strategyProfit", "收益里程碑", "达到阶段收益时提醒")}</>;
  else if (section === "市场异动") content = <><label className="setting-number">上涨异动阈值<input value={settings.movementRise} onChange={(event) => setSettings({ ...settings, movementRise: event.target.value })} inputMode="decimal"/><span>% / 5分钟</span></label><label className="setting-number">下跌异动阈值<input value={settings.movementFall} onChange={(event) => setSettings({ ...settings, movementFall: event.target.value })} inputMode="decimal"/><span>% / 5分钟</span></label>{switchRow("movementVolume", "成交量异动", "成交量超过过去 20 根均值的 2 倍")}</>;
  else if (section === "消息中心") content = <>{switchRow("messageNotice", "消息通知", "产品、系统与版本消息")}{switchRow("accountActivity", "账户活动", "登录、授权检查和工作区变化")}</>;
  else content = <><p className="setting-intro">Webhook 只保存在本机，用于模拟预警转发配置，不会主动发送请求。</p><div className="webhook-add"><input value={webhook} onChange={(event) => setWebhook(event.target.value)} placeholder="https://example.com/webhook"/><button onClick={() => { if (!/^https:\/\//.test(webhook)) return say("请输入 https:// 开头的 Webhook 地址"); if (!webhooks.includes(webhook)) setWebhooks([...webhooks, webhook]); setWebhook(""); say("Webhook 地址已保存到本机"); }}>添加</button></div>{webhooks.map((url) => <div className="webhook-row" key={url}><I.Link/><span>{url}</span><button onClick={() => setWebhooks(webhooks.filter((item) => item !== url))}>删除</button></div>)}{!webhooks.length && <div className="utility-empty"><I.WebhooksLogo/><b>暂无 Webhook 地址</b></div>}</>;
  return <div className="system-settings-panel"><aside>{sections.map((name) => <button className={section === name ? "on" : ""} key={name} onClick={() => setSection(name)}>{name}<I.CaretRight/></button>)}</aside><main><header><div><small>系统设置</small><h3>{section}</h3></div><button onClick={resetSection}>恢复默认</button></header><section>{content}</section><footer><button onClick={close}>取消</button><button className="overlay-primary" onClick={() => { setPrefs({ ...prefs, desktop: settings.alertEnabled, sound: settings.flashSound, auto: settings.autoUpdate, redUp: settings.redUp, showDepthBars: settings.depthBars }); say("系统设置已保存"); close(); }}>保存设置</button></footer></main></div>;
}

function AlertCenterPanel({ model, close, say }) {
  const alertTypes = ["价格预警", "指标预警", "价差预警", "资金费率", "链上预警"];
  const defaultAlerts = [
    { id: 1, type: "价格预警", symbol: "BTC/USDT", condition: "上涨至", threshold: "66,120", frequency: "仅一次", ways: ["PC通知"], remark: "突破首要阻力", enabled: true, createdAt: "07-29 16:40" },
    { id: 2, type: "资金费率", symbol: "ETH/USDT", condition: "上涨至", threshold: "0.030%", frequency: "每5分钟一次", ways: ["PC通知", "Webhook"], remark: "拥挤风险", enabled: true, createdAt: "07-29 14:18" },
  ];
  const [alerts, setAlerts] = useStoredState("ai-trading-assistant-alerts", defaultAlerts);
  const [history, setHistory] = useStoredState("ai-trading-assistant-alert-history", [
    { id: 101, time: "07-28 21:14", symbol: "BTC/USDT", type: "价格预警", condition: "下跌至 63,800", result: "已触发" },
    { id: 102, time: "07-27 08:00", symbol: "SOL/USDT", type: "指标预警", condition: "RSI 超卖", result: "已触发" },
  ]);
  const [tab, setTab] = useState(model.initialTab === "历史" ? "历史预警" : "我的预警");
  const [filter, setFilter] = useState("全部类型");
  const [query, setQuery] = useState("");
  const [editingId, setEditingId] = useState(null);
  const [formOpen, setFormOpen] = useState(Boolean(model.initialTab === "信号"));
  const emptyForm = {
    type: model.initialTab === "信号" ? "指标预警" : "价格预警",
    symbol: model.symbol || "BTC/USDT",
    condition: model.initialTab === "信号" ? "买入信号" : "上涨至",
    threshold: model.price || "65,000",
    period: "5分钟",
    frequency: "仅一次",
    pc: true,
    webhook: false,
    remark: "",
  };
  const [form, setForm] = useState(emptyForm);
  const resetForm = () => { setForm(emptyForm); setEditingId(null); setFormOpen(false); };
  const visible = alerts.filter((item) => (filter === "全部类型" || item.type === filter) && item.symbol.toLowerCase().includes(query.toLowerCase()));
  const saveAlert = () => {
    if (!form.symbol.trim()) return say("请选择交易对");
    if (!form.threshold.trim()) return say("条件值必须填写");
    if (!form.pc && !form.webhook) return say("请至少选择一种预警方式");
    const record = {
      id: editingId || Date.now(),
      type: form.type,
      symbol: form.symbol.toUpperCase(),
      condition: form.condition,
      threshold: form.threshold,
      frequency: form.frequency,
      ways: [form.pc ? "PC通知" : null, form.webhook ? "Webhook" : null].filter(Boolean),
      remark: form.remark,
      enabled: editingId
        ? alerts.find((item) => item.id === editingId)?.enabled ?? true
        : true,
      createdAt: new Date().toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }),
    };
    setAlerts(editingId ? alerts.map((item) => item.id === editingId ? record : item) : [record, ...alerts]);
    say(editingId ? "预警已更新" : "预警已添加");
    resetForm();
  };
  const editAlert = (item) => {
    setEditingId(item.id);
    setForm({ type: item.type, symbol: item.symbol, condition: item.condition, threshold: item.threshold, period: "5分钟", frequency: item.frequency, pc: item.ways.includes("PC通知"), webhook: item.ways.includes("Webhook"), remark: item.remark || "" });
    setFormOpen(true);
  };
  const archiveAlert = (item) => {
    setAlerts(alerts.filter((current) => current.id !== item.id));
    setHistory([{ id: Date.now(), time: "刚刚", symbol: item.symbol, type: item.type, condition: `${item.condition} ${item.threshold}`, result: "已删除" }, ...history]);
    say("预警已移入历史记录");
  };
  return (
    <div className="alert-center-panel">
      <nav>
        {["我的预警", "历史预警"].map((name) => <button className={tab === name ? "on" : ""} key={name} onClick={() => { setTab(name); setFormOpen(false); }}>{name}</button>)}
        <span />
        <button onClick={() => close()}>关闭</button>
        {tab === "我的预警" && <button className="primary" onClick={() => { setForm(emptyForm); setEditingId(null); setFormOpen(true); }}>添加预警</button>}
      </nav>
      {tab === "我的预警" ? (
        <div className="alert-workspace">
          <aside>
            <button className={filter === "全部类型" ? "on" : ""} onClick={() => setFilter("全部类型")}><I.ListBullets/>全部类型<em>{alerts.length}</em></button>
            {alertTypes.map((name) => <button className={filter === name ? "on" : ""} key={name} onClick={() => setFilter(name)}><I.BellRinging/>{name}<em>{alerts.filter((item) => item.type === name).length}</em></button>)}
          </aside>
          <main>
            <header><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索交易对"/><span>共 {visible.length} 条 · 最多保存 20 条本地预警</span></header>
            <div className="alert-table">
              <header>{["交易对", "类型", "触发条件", "频率", "通知", "状态", "操作"].map((name) => <b key={name}>{name}</b>)}</header>
              {visible.map((item) => <div key={item.id}><strong>{item.symbol}</strong><span>{item.type}</span><span>{item.condition} {item.threshold}</span><span>{item.frequency}</span><span>{item.ways.join(" + ")}</span><button className="alert-status" onClick={() => setAlerts(alerts.map((current) => current.id === item.id ? { ...current, enabled: !current.enabled } : current))}><i className={item.enabled ? "switch on" : "switch"}/>{item.enabled ? "运行中" : "已暂停"}</button><span className="alert-row-actions"><button onClick={() => editAlert(item)}>编辑</button><button onClick={() => archiveAlert(item)}>删除</button></span></div>)}
              {!visible.length && <div className="alert-empty"><I.BellSlash/><b>暂无匹配预警</b><button onClick={() => { setFilter("全部类型"); setQuery(""); }}>清除筛选</button></div>}
            </div>
          </main>
          {formOpen && <aside className="alert-editor"><header><div><small>{editingId ? "编辑预警" : "添加预警"}</small><h3>{form.type}</h3></div><button aria-label="关闭预警编辑" onClick={resetForm}><I.X/></button></header><label>预警类型<select value={form.type} onChange={(event) => setForm({ ...form, type: event.target.value, condition: event.target.value === "指标预警" ? "买入信号" : "上涨至" })}>{alertTypes.map((name) => <option key={name}>{name}</option>)}</select></label><label>交易对<input value={form.symbol} onChange={(event) => setForm({ ...form, symbol: event.target.value })}/></label>{form.type === "指标预警" && <label>周期<select value={form.period} onChange={(event) => setForm({ ...form, period: event.target.value })}><option>1分钟</option><option>5分钟</option><option>15分钟</option><option>1小时</option><option>4小时</option></select></label>}<label>触发条件<select value={form.condition} onChange={(event) => setForm({ ...form, condition: event.target.value })}>{(form.type === "指标预警" ? ["买入信号", "卖出信号", "金叉", "死叉"] : form.type === "链上预警" ? ["转入金额高于", "转出金额高于", "巨鲸地址交易"] : ["上涨至", "下跌至", "涨幅达到", "跌幅达到"]).map((name) => <option key={name}>{name}</option>)}</select></label><label>条件值<input value={form.threshold} onChange={(event) => setForm({ ...form, threshold: event.target.value })} placeholder="请输入阈值"/></label><label>预警频率<select value={form.frequency} onChange={(event) => setForm({ ...form, frequency: event.target.value })}><option>仅一次</option><option>持续</option><option>每5分钟一次</option><option>每日一次</option></select></label><div className="alert-way"><b>预警方式</b><button className={form.pc ? "on" : ""} onClick={() => setForm({ ...form, pc: !form.pc })}><I.Desktop/>PC通知</button><button className={form.webhook ? "on" : ""} onClick={() => setForm({ ...form, webhook: !form.webhook })}><I.WebhooksLogo/>Webhook</button></div><label>备注<input value={form.remark} maxLength={30} onChange={(event) => setForm({ ...form, remark: event.target.value })} placeholder="选填，最多30字"/></label><footer><button onClick={resetForm}>取消</button><button className="primary" onClick={saveAlert}>{editingId ? "保存修改" : "确认添加"}</button></footer></aside>}
        </div>
      ) : (
        <div className="alert-history"><header>{["触发时间", "交易对", "类型", "触发条件", "结果", "操作"].map((name) => <b key={name}>{name}</b>)}</header>{history.map((item) => <div key={item.id}><time>{item.time}</time><strong>{item.symbol}</strong><span>{item.type}</span><span>{item.condition}</span><em>{item.result}</em><button onClick={() => { setTab("我的预警"); setForm({ ...emptyForm, type: item.type, symbol: item.symbol, condition: item.condition.split(" ")[0], threshold: item.condition.split(" ").slice(1).join(" ") || emptyForm.threshold }); setFormOpen(true); }}>重新添加</button></div>)}<footer>* 仅显示近3个月的本地记录</footer></div>
      )}
    </div>
  );
}

function ActionOverlay({
  model,
  close,
  say,
  go,
  prefs,
  setPrefs,
  watch,
  setWatch,
  savedStrategies,
  setSavedStrategies,
  assetGroups,
  setAssetGroups,
  authorizedAccounts,
  setAuthorizedAccounts,
}) {
  const [value, setValue] = useState("");
  const [choice, setChoice] = useState(prefs.currency);
  const [step, setStep] = useState(1);
  const [strategyForm, setStrategyForm] = useState({
    id: model.strategy?.id,
    name:
      model.strategy?.name ||
      `${model.strategy?.coin || "BTC"} ${model.strategy?.type || "正向套利"}`,
    coin: model.strategy?.coin || "BTC",
    type: model.strategy?.type || "正向套利",
    annualized: model.strategy?.annualized || "--",
    amount: model.strategy?.amount || "1000",
    risk: model.strategy?.risk || "稳健",
    platform: model.strategy?.platform || "币安 + OKX",
  });
  const [groupForm, setGroupForm] = useState({
    name: "",
    type: "自定义组合",
    account: "全部账户",
  });
  const [authForm, setAuthForm] = useState({
    platform: model.platform || "币安",
    alias: model.platform ? `${model.platform} 主账户` : "",
    apiKey: "",
    apiSecret: "",
    read: true,
    trade: true,
  });
  const [helpTopic, setHelpTopic] = useState("");
  const [layoutName, setLayoutName] = useState("BTC 主交易布局");
  const [layoutPreset, setLayoutPreset] = useState("单图专业版");
  const [layoutSync, setLayoutSync] = useState(true);
  const done = (message) => {
    say(message);
    close();
  };
  const simpleDescription = model.description || "该功能已接入本地交互演示。";
  const strategyCoins = [...new Set(["BTC", "ETH", "SOL", "XRP", "PEPE", "HBAR", "BNB", "LINK", "PENDLE", strategyForm.coin])];
  const strategyTypes = [...new Set(["自动赚币", "正向套利", "反向套利", "跨所永续", "永续-期货", "价差-期现", strategyForm.type])];
  return (
    <div className="overlay-backdrop" onMouseDown={close}>
      <section
        className="action-overlay"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <header>
          <b>{model.title}</b>
          <button aria-label="关闭" onClick={close}>
            <I.X />
          </button>
        </header>
        {model.type === "notifications" ? (
          <NotificationCenterPanel close={close} say={say} go={go} />
        ) : model.type === "messages" ? (
          <MessageCenterPanel say={say} />
        ) : model.type === "alertCenter" ? (
          <AlertCenterPanel model={model} close={close} say={say} />
        ) : model.type === "currency" ? (
          <div className="choice-grid">
            {["USD", "CNY", "USDT", "BTC"].map((x) => (
              <button
                key={x}
                className={choice === x ? "on" : ""}
                onClick={() => setChoice(x)}
              >
                {x}
              </button>
            ))}
            <button
              className="overlay-primary"
              onClick={() => {
                setPrefs({ ...prefs, currency: choice });
                done(`计价单位已切换为 ${choice}`);
              }}
            >
              确认
            </button>
          </div>
        ) : model.type === "profile" ? (
          <div className="profile-panel">
            <I.UserCircle />
            <h3>60716203</h3>
            <p>AI交易助手服务账户</p>
            <button
              onClick={() => {
                close();
                go("assets");
              }}
            >
              我的资产
            </button>
            <button
              onClick={() => {
                close();
                go("auth");
              }}
            >
              API 授权
            </button>
            <button onClick={() => done("已退出演示账户")}>退出登录</button>
          </div>
        ) : model.type === "settings" ? (
          <SystemSettingsPanel prefs={prefs} setPrefs={setPrefs} close={close} say={say} />
        ) : model.type === "create" && model.title.includes("图表布局") ? (
          <div className="layout-create-panel">
            <p>新布局会保存当前图表、指标与工作台组合，可随时从布局列表恢复。</p>
            <label>布局名称<input value={layoutName} onChange={(e)=>setLayoutName(e.target.value)} /></label>
            <div className="layout-presets">
              {["单图专业版", "双图对比", "四图监控"].map((name)=><button key={name} className={layoutPreset===name?"on":""} onClick={()=>setLayoutPreset(name)}><I.ChartLine/><b>{name}</b><small>{name==="单图专业版"?"K线 + 盘口 + 工作台":name==="双图对比"?"两个币种并排":"四个周期同步观察"}</small></button>)}
            </div>
            <button className="layout-sync" onClick={()=>setLayoutSync(!layoutSync)}><span><b>同步当前指标与周期</b><small>保存 MA、Volume、5分及工作台状态</small></span><i className={layoutSync?"switch on":"switch"}/></button>
            <footer className="feature-actions"><button onClick={close}>取消</button><button className="overlay-primary" onClick={()=>{if(!layoutName.trim())return say("请输入布局名称");localStorage.setItem("ai-trading-assistant-chart-layout",JSON.stringify({name:layoutName.trim(),preset:layoutPreset,sync:layoutSync}));done(`图表布局“${layoutName.trim()}”已保存`);}}>创建布局</button></footer>
          </div>
        ) : model.type === "create" ? (
          <div className="create-grid">
            {[
              ["添加自选", "market", I.Star],
              ["创建策略", "strategy", I.Robot],
              ["添加授权", "auth", I.Key],
              ["添加资产组合", "assets", I.Wallet],
            ].map(([n, p, Icon]) => (
              <button
                key={n}
                onClick={() => {
                  close();
                  go(p);
                }}
              >
                <Icon />
                <b>{n}</b>
                <I.CaretRight />
              </button>
            ))}
          </div>
        ) : model.type === "strategyCreate" ? (
          <div className="wizard">
            <div className="wizard-steps">
              {["基础信息", "运行参数", "确认创建"].map((name, index) => (
                <span key={name} className={step >= index + 1 ? "on" : ""}>
                  <i>{index + 1}</i>
                  {name}
                </span>
              ))}
            </div>
            {step === 1 ? (
              <div className="wizard-form">
                <label>策略名称</label>
                <input
                  value={strategyForm.name}
                  onChange={(e) =>
                    setStrategyForm({ ...strategyForm, name: e.target.value })
                  }
                />
                <label>币种</label>
                <select
                  value={strategyForm.coin}
                  onChange={(e) =>
                    setStrategyForm({ ...strategyForm, coin: e.target.value })
                  }
                >
                  {strategyCoins.map(
                    (coin) => (
                      <option key={coin}>{coin}</option>
                    ),
                  )}
                </select>
                <label>套利类型</label>
                <select
                  value={strategyForm.type}
                  onChange={(e) =>
                    setStrategyForm({ ...strategyForm, type: e.target.value })
                  }
                >
                  {strategyTypes.map((type) => (
                    <option key={type}>{type}</option>
                  ))}
                </select>
              </div>
            ) : step === 2 ? (
              <div className="wizard-form">
                <label>投入金额（USDT）</label>
                <input
                  type="number"
                  min="10"
                  value={strategyForm.amount}
                  onChange={(e) =>
                    setStrategyForm({ ...strategyForm, amount: e.target.value })
                  }
                />
                <label>平台组合</label>
                <select
                  value={strategyForm.platform}
                  onChange={(e) =>
                    setStrategyForm({
                      ...strategyForm,
                      platform: e.target.value,
                    })
                  }
                >
                  {["币安 + OKX", "币安 + Bybit", "OKX + Bitget"].map(
                    (platform) => (
                      <option key={platform}>{platform}</option>
                    ),
                  )}
                </select>
                <label>风险偏好</label>
                <div className="choice-row">
                  {["稳健", "均衡", "进取"].map((risk) => (
                    <button
                      key={risk}
                      className={strategyForm.risk === risk ? "on" : ""}
                      onClick={() => setStrategyForm({ ...strategyForm, risk })}
                    >
                      {risk}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <div className="wizard-review">
                <h3>{strategyForm.name}</h3>
                <p>
                  <span>交易组合</span>
                  <b>
                    {strategyForm.coin}/USDT · {strategyForm.type}
                  </b>
                </p>
                <p>
                  <span>平台</span>
                  <b>{strategyForm.platform}</b>
                </p>
                <p>
                  <span>投入金额</span>
                  <b>{strategyForm.amount} USDT</b>
                </p>
                <p>
                  <span>风险偏好</span>
                  <b>{strategyForm.risk}</b>
                </p>
                <small>
                  创建后会出现在“我的套利”，本演示不会提交真实订单。
                </small>
              </div>
            )}
            <div className="wizard-actions">
              <button
                onClick={() => (step === 1 ? close() : setStep(step - 1))}
              >
                {step === 1 ? "取消" : "上一步"}
              </button>
              <button
                className="overlay-primary"
                onClick={() => {
                  if (step === 1 && !strategyForm.name.trim())
                    return say("请填写策略名称");
                  if (step === 2 && Number(strategyForm.amount) < 10)
                    return say("投入金额不能低于 10 USDT");
                  if (step < 3) return setStep(step + 1);
                  const record = {
                    ...strategyForm,
                    id: strategyForm.id || Date.now(),
                  };
                  setSavedStrategies(
                    strategyForm.id
                      ? savedStrategies.map((item) =>
                          item.id === strategyForm.id ? record : item,
                        )
                      : [...savedStrategies, record],
                  );
                  done(strategyForm.id ? "策略已更新" : "策略已创建");
                }}
              >
                {step < 3
                  ? "下一步"
                  : strategyForm.id
                    ? "保存修改"
                    : "确认创建"}
              </button>
            </div>
          </div>
        ) : model.type === "addGroup" ? (
          <div className="wizard">
            <div className="wizard-steps">
              {["组合信息", "关联账户", "确认"].map((name, index) => (
                <span key={name} className={step >= index + 1 ? "on" : ""}>
                  <i>{index + 1}</i>
                  {name}
                </span>
              ))}
            </div>
            {step === 1 ? (
              <div className="wizard-form">
                <label>组合名称</label>
                <input
                  value={groupForm.name}
                  onChange={(e) =>
                    setGroupForm({ ...groupForm, name: e.target.value })
                  }
                  placeholder="例如 核心资产"
                />
                <label>组合类型</label>
                <select
                  value={groupForm.type}
                  onChange={(e) =>
                    setGroupForm({ ...groupForm, type: e.target.value })
                  }
                >
                  {["自定义组合", "现货组合", "合约组合", "策略专用"].map(
                    (type) => (
                      <option key={type}>{type}</option>
                    ),
                  )}
                </select>
              </div>
            ) : step === 2 ? (
              <div className="wizard-form">
                <label>关联账户</label>
                <div className="choice-row vertical">
                  {["全部账户", "币安账户", "OKX账户"].map((account) => (
                    <button
                      key={account}
                      className={groupForm.account === account ? "on" : ""}
                      onClick={() => setGroupForm({ ...groupForm, account })}
                    >
                      {account}
                      <small>资产将按此范围归集展示</small>
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <div className="wizard-review">
                <h3>{groupForm.name}</h3>
                <p>
                  <span>类型</span>
                  <b>{groupForm.type}</b>
                </p>
                <p>
                  <span>账户范围</span>
                  <b>{groupForm.account}</b>
                </p>
              </div>
            )}
            <div className="wizard-actions">
              <button
                onClick={() => (step === 1 ? close() : setStep(step - 1))}
              >
                {step === 1 ? "取消" : "上一步"}
              </button>
              <button
                className="overlay-primary"
                onClick={() => {
                  if (step === 1 && !groupForm.name.trim())
                    return say("请填写组合名称");
                  if (step < 3) return setStep(step + 1);
                  setAssetGroups([
                    ...assetGroups,
                    { ...groupForm, id: Date.now() },
                  ]);
                  done(`${groupForm.name} 已创建`);
                }}
              >
                {step < 3 ? "下一步" : "创建组合"}
              </button>
            </div>
          </div>
        ) : model.type === "apiAuth" ? (
          <div className="wizard">
            <div className="wizard-steps">
              {["选择平台", "API 信息", "安全确认"].map((name, index) => (
                <span key={name} className={step >= index + 1 ? "on" : ""}>
                  <i>{index + 1}</i>
                  {name}
                </span>
              ))}
            </div>
            {step === 1 ? (
              <div className="wizard-form">
                <label>交易平台</label>
                <select
                  value={authForm.platform}
                  onChange={(e) =>
                    setAuthForm({ ...authForm, platform: e.target.value })
                  }
                >
                  {["币安", "OKX", "Bitget", "Bybit", "Gate"].map(
                    (platform) => (
                      <option key={platform}>{platform}</option>
                    ),
                  )}
                </select>
                <label>账户别名</label>
                <input
                  value={authForm.alias}
                  onChange={(e) =>
                    setAuthForm({ ...authForm, alias: e.target.value })
                  }
                  placeholder="例如 币安主账户"
                />
              </div>
            ) : step === 2 ? (
              <div className="wizard-form">
                <label>API Key</label>
                <input
                  type="password"
                  value={authForm.apiKey}
                  onChange={(e) =>
                    setAuthForm({ ...authForm, apiKey: e.target.value })
                  }
                  placeholder="演示信息不会保存"
                />
                <label>Secret Key</label>
                <input
                  type="password"
                  value={authForm.apiSecret}
                  onChange={(e) =>
                    setAuthForm({ ...authForm, apiSecret: e.target.value })
                  }
                  placeholder="演示信息不会保存"
                />
                <div className="permission-row">
                  <button
                    onClick={() =>
                      setAuthForm({ ...authForm, read: !authForm.read })
                    }
                  >
                    <i className={authForm.read ? "switch on" : "switch"} />
                    读取权限
                  </button>
                  <button
                    onClick={() =>
                      setAuthForm({ ...authForm, trade: !authForm.trade })
                    }
                  >
                    <i className={authForm.trade ? "switch on" : "switch"} />
                    交易权限
                  </button>
                </div>
              </div>
            ) : (
              <div className="wizard-review security-review">
                <I.ShieldCheck />
                <h3>确认安全权限</h3>
                <p>
                  <span>平台</span>
                  <b>{authForm.platform}</b>
                </p>
                <p>
                  <span>账户</span>
                  <b>{authForm.alias}</b>
                </p>
                <p>
                  <span>权限</span>
                  <b>
                    {authForm.read ? "读取" : ""}
                    {authForm.trade ? "、交易" : ""}
                  </b>
                </p>
                <small>
                  请确保交易所 API
                  未开启提现或转账权限。密钥不会写入本地演示数据。
                </small>
              </div>
            )}
            <div className="wizard-actions">
              <button
                onClick={() => (step === 1 ? close() : setStep(step - 1))}
              >
                {step === 1 ? "取消" : "上一步"}
              </button>
              <button
                className="overlay-primary"
                onClick={() => {
                  if (step === 1 && !authForm.alias.trim())
                    return say("请填写账户别名");
                  if (step === 2 && (!authForm.apiKey || !authForm.apiSecret))
                    return say("请填写 API Key 和 Secret Key");
                  if (step === 2 && !authForm.read)
                    return say("至少需要开启读取权限");
                  if (step < 3) return setStep(step + 1);
                  setAuthorizedAccounts([
                    ...authorizedAccounts,
                    {
                      id: Date.now(),
                      platform: authForm.platform,
                      alias: authForm.alias,
                      status: "正常",
                      createdAt: new Date().toLocaleDateString("zh-CN"),
                    },
                  ]);
                  done(`${authForm.alias} 已授权`);
                }}
              >
                {step < 3 ? "下一步" : "完成授权"}
              </button>
            </div>
          </div>
        ) : model.type === "addWatch" ? (
          <div className="overlay-form">
            <div className="watch-chips">
              {watch.map((x) => (
                <button
                  key={x}
                  onClick={() => setWatch(watch.filter((n) => n !== x))}
                >
                  {x} <I.X />
                </button>
              ))}
            </div>
            <label>名称</label>
            <input
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder={"例如 BTC/USDT"}
            />
            <button
              className="overlay-primary"
              onClick={() => {
                if (!value.trim()) return say("请填写名称");
                const symbol = value.toUpperCase().split("/")[0];
                if (!coins.some((x) => x[0] === symbol))
                  return say("演示列表暂不包含该币种");
                if (!watch.includes(symbol)) setWatch([...watch, symbol]);
                done(`${value} 已添加`);
              }}
            >
              确认添加
            </button>
          </div>
        ) : FEATURE_OVERLAY_TYPES.includes(model.type) ? (
          <FeatureOverlayPanel model={model} close={close} say={say} go={go} />
        ) : model.type === "help" ? (
          <div className="help-browser">
            <aside>
              {["新手使用指南","行情与图表教程","策略工具教程","API授权安全说明"].map((x) => (
                <button className={helpTopic === x ? "on" : ""} key={x} onClick={() => setHelpTopic(x)}>
                  <I.BookOpen /><span><b>{x}</b><small>{helpTopic === x ? "正在阅读" : "查看教程"}</small></span><I.CaretRight />
                </button>
              ))}
            </aside>
            <section>
              {helpTopic ? <><small>帮助中心 / {helpTopic}</small><h3>{helpTopic}</h3><p>{helpTopic === "新手使用指南" ? "从左侧选择业务页面，使用顶部频道切换场景；行情页中可展开自选、图表工具和底部策略工作台。" : helpTopic === "行情与图表教程" ? "使用周期、指标和绘图工具完成行情观察；多窗、复盘、显示设置会保留当前工作区状态。" : helpTopic === "策略工具教程" ? "先完成参数测算和风险确认，再进入本地模拟创建；真实连接仍需要独立授权与二次确认。" : "API 仅建议开启读取和交易权限，禁止提现与转账权限；密钥不会持久化到演示数据。"}</p><div className="help-checklist">{["阅读功能说明","完成一次本地模拟","检查结果与风险提示"].map((x,i)=><label key={x}><input type="checkbox"/>{i+1}. {x}</label>)}</div><button className="overlay-primary" onClick={()=>{close();go(helpTopic.includes("策略")?"strategy":helpTopic.includes("API")?"auth":"market")}}>进入对应页面</button></> : <div className="utility-empty"><I.BookOpen/><b>选择左侧教程开始阅读</b><small>{model.title}</small></div>}
            </section>
          </div>
        ) : (
          <div className="result-panel">
            <I.Sparkle />
            <p>{simpleDescription}</p>
            <div className="result-cards">
              <span>趋势：中性偏强</span>
              <span>支撑：63,600</span>
              <span>压力：64,400</span>
            </div>
            <button
              onClick={() => {
                close();
                go("market");
              }}
            >
              打开完整行情
            </button>
            <button className="overlay-primary" onClick={close}>
              知道了
            </button>
          </div>
        )}
      </section>
    </div>
  );
}
function Ticker({ symbol = "BTC" }) {
  const quote = quoteFor(symbol);
  return (
    <footer className="ticker">
      <b>体验中</b>
      <span>手续费 0%</span>
      <span>
        恐惧&贪婪指数 <strong>-7.41%</strong>　25
      </span>
      <span>
        {symbol}/USDT 币安 <em>{quote.change}</em>　{formatPrice(quote.price, quote.decimals)}
      </span>
      <span>
        主力24H挂单 <strong>43.56亿美元</strong>
      </span>
      <div />
      <span>
        <I.WifiHigh /> 线路3：优
      </span>
      <time>SGT 07/18 19:14:27</time>
    </footer>
  );
}

createRoot(document.getElementById("root")).render(<App />);
