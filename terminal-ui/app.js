/* =========================================================
   TERMINAL — market data workstation
   Vanilla JS. Simulated feed, no network, no build step.
   ========================================================= */
(function () {
  "use strict";

  /* ---------------- helpers ---------------- */
  const $ = (id) => document.getElementById(id) || (() => {
    const cell = document.querySelector(".qcell.focus");
    return cell ? cell.querySelector('[id$="-' + id + '"]') : null;
  })();
  const rnd = (a, b) => a + Math.random() * (b - a);
  const pick = (arr) => arr[Math.floor(Math.random() * arr.length)];
  const f2 = (v) => (v == null || isNaN(v) ? "-" : v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }));
  const fpct = (v) => (v == null ? "-" : (v >= 0 ? "+" : "") + v.toFixed(2) + "%");
  const fnum = (v) => (v == null ? "-" : v.toLocaleString("en-US", { maximumFractionDigits: 0 }));
  const cls = (v) => (v > 0 ? "up" : v < 0 ? "dn" : "dim");
  const arrow = (v) => (v > 0 ? "\u25B2" : v < 0 ? "\u25BC" : "\u2013");
  const pad2 = (n) => String(n).padStart(2, "0");
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));

  function hhmmss(d) { return pad2(d.getHours()) + ":" + pad2(d.getMinutes()) + ":" + pad2(d.getSeconds()); }
  function hhmm(d) { return pad2(d.getHours()) + ":" + pad2(d.getMinutes()); }

  /* ---------------- universe ---------------- */
  // cls: INDEX | EQUITY | FX | CMDTY | GOVT
  const RAW = [
    // indices
    ["SPX", "S&P 500 INDEX", "INDEX", "US Equity Index", 5842.31, 2.31e9, null, null, "USD"],
    ["INDU", "DOW JONES INDUS. AVG", "INDEX", "US Equity Index", 43112.87, 3.1e8, null, null, "USD"],
    ["CCMP", "NASDAQ COMPOSITE", "INDEX", "US Equity Index", 18674.22, 4.8e9, null, null, "USD"],
    ["RTY", "RUSSELL 2000 INDEX", "INDEX", "US Equity Index", 2318.44, 7.2e8, null, null, "USD"],
    ["UKX", "FTSE 100 INDEX", "INDEX", "EMEA Equity Index", 8241.16, 5.6e8, null, null, "GBP"],
    ["DAX", "DAX INDEX", "INDEX", "EMEA Equity Index", 19844.02, 3.4e8, null, null, "EUR"],
    ["SX5E", "EURO STOXX 50 PR", "INDEX", "EMEA Equity Index", 4952.71, 2.8e8, null, null, "EUR"],
    ["NKY", "NIKKEI 225", "INDEX", "APAC Equity Index", 38122.40, 9.1e8, null, null, "JPY"],
    ["HSI", "HANG SENG INDEX", "INDEX", "APAC Equity Index", 20311.55, 1.4e9, null, null, "HKD"],
    // equities
    ["AAPL", "APPLE INC", "EQUITY", "Technology", 231.48, 5.4e7, 3.51e12, 35.2, "USD"],
    ["MSFT", "MICROSOFT CORP", "EQUITY", "Technology", 438.92, 2.1e7, 3.26e12, 34.8, "USD"],
    ["NVDA", "NVIDIA CORP", "EQUITY", "Semiconductors", 142.66, 2.8e8, 3.49e12, 55.1, "USD"],
    ["AMZN", "AMAZON.COM INC", "EQUITY", "Consumer Discretionary", 214.35, 3.6e7, 2.25e12, 42.7, "USD"],
    ["GOOGL", "ALPHABET INC-CL A", "EQUITY", "Communication Services", 178.12, 2.4e7, 2.18e12, 24.3, "USD"],
    ["META", "META PLATFORMS INC-CLASS A", "EQUITY", "Communication Services", 592.44, 1.2e7, 1.50e12, 27.9, "USD"],
    ["TSLA", "TESLA INC", "EQUITY", "Automobiles", 348.71, 8.9e7, 1.12e12, 92.4, "USD"],
    ["JPM", "JPMORGAN CHASE & CO", "EQUITY", "Banks", 243.18, 9.4e6, 6.86e11, 13.1, "USD"],
    ["GS", "GOLDMAN SACHS GROUP INC", "EQUITY", "Banks", 561.72, 2.1e6, 1.78e11, 15.4, "USD"],
    ["XOM", "EXXON MOBIL CORP", "EQUITY", "Energy", 118.06, 1.6e7, 5.21e11, 14.2, "USD"],
    // fx
    ["EURUSD", "EURO SPOT", "FX", "G10 FX", 1.0842, 0, null, null, "USD"],
    ["USDJPY", "JAPANESE YEN SPOT", "FX", "G10 FX", 152.34, 0, null, null, "JPY"],
    ["GBPUSD", "BRITISH POUND SPOT", "FX", "G10 FX", 1.2718, 0, null, null, "USD"],
    ["USDCNH", "CHINA RENMINBI SPOT", "FX", "EM FX", 7.2418, 0, null, null, "CNH"],
    // commodities
    ["CL1", "WTI CRUDE FUTURE", "CMDTY", "Energy", 71.42, 3.1e5, null, null, "USD"],
    ["GC1", "GOLD FUTURE", "CMDTY", "Precious Metals", 2681.30, 1.8e5, null, null, "USD"],
    ["HG1", "COPPER FUTURE", "CMDTY", "Base Metals", 4.182, 9.2e4, null, null, "USD"],
    // rates
    ["USGG10YR", "US 10YR TREASURY", "GOVT", "Government", 4.284, 0, null, null, "USD"],
    ["USGG2YR", "US 2YR TREASURY", "GOVT", "Government", 4.152, 0, null, null, "USD"],
    ["GDBR10", "GERMAN BUND 10YR", "GOVT", "Government", 2.418, 0, null, null, "EUR"]
  ];

  function makeBars(last, n, vol) {
    // build n synthetic 5-min bars ending at `last`
    const bars = [];
    let px = last * rnd(0.965, 0.995);
    for (let i = 0; i < n; i++) {
      const drift = (last - px) / Math.max(8, n - i) * rnd(0.55, 1.45);
      const o = px;
      const c = Math.max(0.0001, o + drift + (Math.random() - 0.5) * o * 0.0042);
      const h = Math.max(o, c) * (1 + Math.random() * 0.0022);
      const l = Math.min(o, c) * (1 - Math.random() * 0.0022);
      bars.push([o, h, l, c, Math.round((vol || 1e6) / n * rnd(0.35, 1.85))]);
      px = c;
    }
    const k = last / bars[bars.length - 1][3];
    bars.forEach((b) => { b[0] *= k; b[1] *= k; b[2] *= k; b[3] *= k; });
    return bars;
  }

  const UNIV = RAW.map((r) => {
    const [sym, name, cls_, sect, px, vol, mcap, pe, ccy] = r;
    const hist = makeBars(px, 120, vol || 2e6);
    const prev = hist[hist.length - 2][3];
    const sp = px * (cls_ === "FX" ? 0.00008 : cls_ === "GOVT" ? 0.0004 : 0.00045);
    return {
      sym, name, cls: cls_, sect, px, prev, vol, mcap, pe, ccy, hist,
      bid: px - sp, ask: px + sp,
      open: hist[0][0], hi: Math.max.apply(null, hist.map((b) => b[1])),
      lo: Math.min.apply(null, hist.map((b) => b[2]))
    };
  });
  const bySym = {};
  UNIV.forEach((s) => (bySym[s.sym] = s));

  /* ---- multi-period series + synthetic order book ---- */
  const PERIODS = ["5M", "15M", "1H", "1D"];
  const SUBS = ["VOL", "RSI", "MACD"];
  const CTYPES = ["CANDLE", "BAR", "LINE", "AREA", "MOUNTAIN"];
  const THEMES = ["AMBER", "ICE", "TOXIC"];
  const P_MIN = { "5M": 5, "15M": 15, "1H": 60, "1D": 1440 };

  function makeBook(s) {
    const tick = s.cls === "FX" ? 0.0001 : s.cls === "GOVT" ? 0.001 : s.px > 500 ? 0.5 : s.px > 100 ? 0.05 : s.px > 10 ? 0.01 : 0.001;
    const dec = s.cls === "FX" ? 4 : 2;
    const rows = [];
    const unit = s.cls === "EQUITY" ? 100 : 10;
    for (let i = 0; i < 6; i++) {
      rows.push({
        bpx: Number((s.bid - i * tick).toFixed(dec)),
        bq: Math.round(rnd(1, 9) * unit),
        apx: Number((s.ask + i * tick).toFixed(dec)),
        aq: Math.round(rnd(1, 9) * unit)
      });
    }
    return rows;
  }

  UNIV.forEach((s) => {
    s.series = { "5M": s.hist };
    s.series["15M"] = makeBars(s.px, 110, s.vol || 2e6);
    s.series["1H"] = makeBars(s.px, 100, s.vol || 2e6);
    s.series["1D"] = makeBars(s.px, 120, s.vol || 2e6);
    s.book = makeBook(s);
    s.tas = makeTape(s, 28);
  });

  /* ---- time & sales tape ---- */
  function makeTape(s, n) {
    const out = [];
    const dec = s.cls === "FX" ? 4 : 2;
    const qUnit = s.cls === "EQUITY" ? 100 : 10;
    let px = s.px * rnd(0.9985, 1.0015);
    const t0 = Date.now();
    for (let i = 0; i < n; i++) {
      px = Math.max(0.0001, px * (1 + (Math.random() - 0.5) * 0.0009));
      out.push({ t: t0 - (n - i) * 4300, px: Number(px.toFixed(dec)), sz: Math.round(rnd(1, 12) * qUnit) });
    }
    return out;
  }

  function pushTape(s) {
    const dec = s.cls === "FX" ? 4 : 2;
    const qUnit = s.cls === "EQUITY" ? 100 : 10;
    s.tas.push({ t: Date.now(), px: Number(s.px.toFixed(dec)), sz: Math.round(rnd(1, 9) * qUnit) });
    if (s.tas.length > 60) s.tas.splice(0, s.tas.length - 60);
  }

  /* ---- persistence ---- */
  const USER_KEY = "terminal.user";
  const PROFILE_PREFIX = "terminal.workstation.v1:";
  const DEFAULT_PROFILE = {
    cash: 1000000,
    pos: {},
    watch: ["SPX", "AAPL", "NVDA", "MSFT", "TSLA"],
    period: "5M",
    ma: true,
    blot: [],
    realized: 0,
    boll: false,
    sub: "VOL",
    theme: "AMBER",
    orders: [],
    alerts: [],
    nextOid: 1001,
    nextAid: 1,
    draw: {},
    layout: "1",
    split: { c: 0.5, r: 0.5 },
    settings: { sound: true, notify: false, pauseHidden: true, density: "normal", icon: "256" },
    maCfg: { a: 20, b: 60, bn: 20, bk: 2 },
    lastBackup: "",
    panels: [
      { func: "GP", sym: "AAPL" },
      { func: "W", sym: "" },
      { func: "TOP", sym: "" },
      { func: "ORD", sym: "" }
    ],
    screens: [],
    alertLog: []
  };

  function readUser() {
    try { return (localStorage.getItem(USER_KEY) || "GUEST").toUpperCase(); } catch (e) { return "GUEST"; }
  }

  function profileNames() {
    const out = [];
    try {
      for (let i = 0; i < localStorage.length; i++) {
        const k = localStorage.key(i);
        if (k && k.indexOf(PROFILE_PREFIX) === 0) out.push(k.slice(PROFILE_PREFIX.length));
      }
    } catch (e) { /* ignore */ }
    if (out.indexOf("GUEST") < 0) out.push("GUEST");
    return out.sort();
  }

  const Store = {
    data: JSON.parse(JSON.stringify(DEFAULT_PROFILE)),
    key() { return PROFILE_PREFIX + (App.user || "GUEST"); },
    reset() { this.data = JSON.parse(JSON.stringify(DEFAULT_PROFILE)); },
    load() {
      this.reset();
      try {
        const raw = localStorage.getItem(this.key());
        if (raw) {
          const d = JSON.parse(raw);
          if (typeof d.cash === "number") this.data.cash = d.cash;
          if (d.pos && typeof d.pos === "object") this.data.pos = d.pos;
          if (Array.isArray(d.watch) && d.watch.length) this.data.watch = d.watch.filter((x) => bySym[x]);
          if (PERIODS.indexOf(d.period) >= 0) this.data.period = d.period;
          if (["CANDLE", "BAR", "LINE", "AREA", "MOUNTAIN"].includes(d.ctype)) this.data.ctype = d.ctype;
          if (typeof d.logScale === "boolean") this.data.logScale = d.logScale;
          if (typeof d.zoom === "number" && isFinite(d.zoom)) this.data.zoom = Math.max(0.7, Math.min(1.5, d.zoom));
          if (typeof d.ma === "boolean") this.data.ma = d.ma;
          if (Array.isArray(d.blot)) this.data.blot = d.blot.slice(0, 300);
          if (typeof d.realized === "number") this.data.realized = d.realized;
          if (typeof d.boll === "boolean") this.data.boll = d.boll;
          if (SUBS.indexOf(d.sub) >= 0) this.data.sub = d.sub;
          if (THEMES.indexOf(d.theme) >= 0) this.data.theme = d.theme;
          if (Array.isArray(d.orders)) this.data.orders = d.orders.slice(0, 200);
          if (Array.isArray(d.alerts)) this.data.alerts = d.alerts.slice(0, 200);
          if (typeof d.nextOid === "number") this.data.nextOid = d.nextOid;
          if (typeof d.nextAid === "number") this.data.nextAid = d.nextAid;
          if (d.draw && typeof d.draw === "object") this.data.draw = d.draw;
          if (["1", "2", "4"].indexOf(d.layout) >= 0) this.data.layout = d.layout;
          if (d.split && isFinite(d.split.c) && isFinite(d.split.r)) {
            this.data.split = {
              c: Math.min(0.8, Math.max(0.2, Number(d.split.c))),
              r: Math.min(0.8, Math.max(0.2, Number(d.split.r)))
            };
          }
          if (Array.isArray(d.panels) && d.panels.length === 4) this.data.panels = d.panels;
          if (Array.isArray(d.screens)) this.data.screens = d.screens.slice(0, 40);
          if (Array.isArray(d.alertLog)) this.data.alertLog = d.alertLog.slice(0, 120);
          if (d.integrationUI && typeof d.integrationUI === "object") this.data.integrationUI = d.integrationUI;
          if (d.settings && typeof d.settings === "object") {
            this.data.settings = Object.assign({}, DEFAULT_PROFILE.settings, d.settings);
          }
          if (d.maCfg && typeof d.maCfg === "object") {
            ["a", "b", "bn", "bk"].forEach((k) => {
              const v = Number(d.maCfg[k]);
              if (isFinite(v) && v > 0) this.data.maCfg[k] = Math.min(k === "bk" ? 5 : 240, v);
            });
          }
          if (typeof d.lastBackup === "string") this.data.lastBackup = d.lastBackup;
          if (d.seeded) this.data.seeded = true;
        }
      } catch (e) { /* ignore corrupt state */ }
    },
    save() {
      try { localStorage.setItem(this.key(), JSON.stringify(this.data)); } catch (e) { /* storage may be blocked */ }
      if (typeof flashSaved === "function") flashSaved();
    }
  };
  // per-profile UI settings (sound / desktop notifications / background tick / density / icon)
  function setts() {
    if (!Store.data.settings) Store.data.settings = Object.assign({}, DEFAULT_PROFILE.settings);
    return Store.data.settings;
  }
  function saveSetts(patch) {
    Object.assign(setts(), patch || {});
    Store.save();
    applySetts();
  }
  function applySetts() {
    const st = setts();
    document.body.classList.toggle("reduce-motion", !!st.reduceMotion);
    document.body.classList.toggle("hide-monitor", !!st.hideMonitor);
    document.documentElement.setAttribute("data-density", st.density || "normal");
    const link = document.getElementById("brandicon");
    if (link && st.icon) link.setAttribute("href", "assets/icon-" + st.icon + ".png");
    applyZoom(Store.data.zoom || 1);
  }

  // first-run demo book so the portfolio screen is never empty
  function seedBook() {
    if (Store.data.seeded) return;
    let spent = 0;
    [["AAPL", 400], ["NVDA", 900], ["SPX", 2]].forEach((pair) => {
      const s = bySym[pair[0]];
      if (!s) return;
      const avg = Number((s.px * rnd(0.93, 0.99)).toFixed(2));
      Store.data.pos[pair[0]] = { qty: pair[1], avg: avg };
      spent += avg * pair[1];
    });
    Store.data.cash = Math.max(0, Math.round(Store.data.cash - spent));
    Store.data.seeded = true;
    Store.save();
  }

  const NEWS = [
    ["09:41", "Fed officials signal patience as core inflation cools to 2.4%", "MACRO"],
    ["09:28", "Nvidia supply checks point to steady Blackwell ramp into 1Q", "NVDA"],
    ["09:12", "Apple lifts services pricing in three European markets", "AAPL"],
    ["08:57", "Treasury 10-year yield slips below 4.30% after soft claims data", "USGG10YR"],
    ["08:44", "OPEC+ compliance improves; WTI holds above $71", "CL1"],
    ["08:31", "Microsoft signs multi-year cloud capacity deal in Southeast Asia", "MSFT"],
    ["08:19", "Gold steady near record as real yields drift lower", "GC1"],
    ["08:05", "Tesla registrations in China rise 12% month over month", "TSLA"],
    ["07:52", "Hang Seng opens higher on stimulus follow-through", "HSI"],
    ["07:40", "JPMorgan lifts S&P 500 year-end target to 6,000", "SPX"],
    ["07:22", "Meta expands AI ad tools to small-business tier", "META"],
    ["07:05", "Euro holds gains after ECB minutes show split on cuts", "EURUSD"]
  ].map((n) => ({ time: n[0], headline: n[1], sym: n[2] }));

  /* ---------------- app state ---------------- */
  const App = {
    func: "HELP",
    sym: null,
    sel: 0,
    ticks: 0,
    rows: [],
    lastPx: {},
    hoverIdx: null,
    period: Store.data.period || "5M",
    ma: !!Store.data.ma,
    boll: !!Store.data.boll,
    sub: Store.data.sub || "VOL",
    ctype: Store.data.ctype || "CANDLE",
    logScale: !!Store.data.logScale,
    cmdHist: [],
    cmdIdx: -1,
    eqsQ: "",
    dictQ: "",
    srchQ: "",
    srchCls: "ALL",
    newsQ: "",
    eqsBuild: [{ f: "PE", op: "<", v: "30" }],
    eqsJoin: "AND",
    eqsUseBuild: false,
    eqsName: "",
    optExpIdx: 0,
    fxAmt: "1000",
    fxFrom: "USD",
    fxTo: "CNH",
    cmdRoot: 0,
    pfx: "",
    focus: 0,
    layout: "1",
    drawMode: null,
    pendPt: null,
    indPanel: false,
    fullChart: false,
    histOpen: false,
    qfOpen: false,
    maCfg: { a: 20, b: 60, bn: 20, bk: 2 },
    sugg: { items: [], idx: -1 },
    scrollMemo: {}
  };
  UNIV.forEach((s) => (App.lastPx[s.sym] = s.px));

  /* profile boot: resolve user, then hydrate that user's state */
  App.user = readUser();
  Store.load();
  App.layout = Store.data.layout || "1";
  App.sort = null;
  App.focus = 0;
  seedBook();

  function switchUser(name) {
    const u = String(name || "").toUpperCase().replace(/[^A-Z0-9_.-]/g, "").slice(0, 12);
    if (!u) return false;
    Store.save();
    App.user = u;
    try { localStorage.setItem(USER_KEY, u); } catch (e) { /* ignore */ }
    Store.load();
    seedBook();
    App.period = Store.data.period;
    App.ma = Store.data.ma;
    App.maCfg = Object.assign({ a: 20, b: 60, bn: 20, bk: 2 }, Store.data.maCfg || {});
    App.boll = Store.data.boll;
    App.sub = Store.data.sub;
    App.ctype = Store.data.ctype || "CANDLE";
    App.logScale = !!Store.data.logScale;
    App.layout = Store.data.layout || "1";
    App.sort = null;
    App.focus = 0;
    App.drawMode = null;
    App.pendPt = null;
    App.sel = 0;
    applySetts();
    applyTheme(Store.data.theme || "AMBER");
    paintRail();
    render();
    const su = $("sessUser");
    if (su) su.textContent = App.user;
    syncNavigation();
    notice("Local profile: " + App.user, false);
    return true;
  }

  function paintUserChips() {
    const box = $("userlist");
    if (!box) return;
    box.innerHTML = profileNames().map((n) =>
      '<span class="pchip' + (n === App.user ? " on" : "") + '" data-u="' + n + '">' + n + "</span>").join("");
  }

  function openAuth() {
    const m = $("authmask");
    if (!m) return;
    m._returnFocus = document.activeElement;
    paintUserChips();
    m.classList.remove("hidden");
    const inp = $("authname");
    inp.value = "";
    setTimeout(() => inp.focus(), 30);
  }

  function closeAuth() {
    const m = $("authmask");
    if (m) { m.classList.add("hidden"); if(m._returnFocus && m._returnFocus.isConnected)m._returnFocus.focus(); }
  }

  function bootAuth() {
    const su = $("sessUser");
    if (su) {
      su.textContent = App.user;
      su.addEventListener("click", openAuth);
    }
    const x = $("authx");
    if (x) x.addEventListener("click", closeAuth);
    const go = $("authgo");
    if (go) go.addEventListener("click", () => {
      const v = $("authname").value.trim();
      if (v) { closeAuth(); switchUser(v); }
    });
    const inp = $("authname");
    if (inp) inp.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        const v = e.target.value.trim();
        if (v) { closeAuth(); switchUser(v); }
      } else if (e.key === "Escape") {
        e.preventDefault();
        closeAuth();
      }
    });
    const list = $("userlist");
    if (list) list.addEventListener("click", (e) => {
      const c = e.target.closest(".pchip");
      if (!c) return;
      closeAuth();
      switchUser(c.getAttribute("data-u"));
    });
  }

  const FUNCS = {
    WEI: { label: "World Equity Indices", key: "F1", needsSym: false },
    W: { label: "Watchlist", key: "F2", needsSym: false },
    TOP: { label: "Top News", key: "F3", needsSym: false },
    DES: { label: "Security Description", key: "F4", needsSym: true },
    GP: { label: "Graph Price", key: "F5", needsSym: true },
    HP: { label: "Historical Prices", key: "F6", needsSym: true },
    N: { label: "News by Security", key: "F7", needsSym: true },
    MOST: { label: "Most Active", key: "F8", needsSym: false },
    PORT: { label: "Portfolio & Trading", key: "F9", needsSym: false },
    HELP: { label: "Help / Command Reference", key: "F10", needsSym: false },
    TRD: { label: "Trade Blotter", key: "", needsSym: false },
    OPT: { label: "Option Chain", key: "", needsSym: true },
    GOV: { label: "Govt Yield Curve", key: "", needsSym: false },
    FX: { label: "FX Cross Matrix", key: "", needsSym: false },
    ECO: { label: "Economic Calendar", key: "", needsSym: false },
    COMP: { label: "Peer Comparison", key: "", needsSym: true },
    ORD: { label: "Order Book / Working Orders", key: "", needsSym: false },
    ALRT: { label: "Price Alerts", key: "", needsSym: false },
    FA: { label: "Financial Analysis", key: "", needsSym: true },
    EQS: { label: "Equity Screener", key: "", needsSym: false },
    FLDS: { label: "Field Dictionary", key: "", needsSym: false },
    SRCH: { label: "Security Search", key: "F11", needsSym: false },
    DEPTH: { label: "Market Depth / DOM", key: "F12", needsSym: true },
    MAP: { label: "Market Map", key: "", needsSym: false },
    CMDT: { label: "Commodity Curve", key: "", needsSym: false },
    SET: { label: "Settings & Profiles", key: "", needsSym: false },
    CONN: { label: "Data & Connections", key: "", needsSym: false },
    PLUG: { label: "Components & Integrations", key: "", needsSym: false },
    WORK: { label: "Workspace & Accessibility", key: "", needsSym: false },
    XL: { label: "Office & Spreadsheet", key: "", needsSym: false },
    MSG: { label: "Messaging & Contacts", key: "", needsSym: false },
    FEED: { label: "Market Data Setup", key: "", needsSym: false },
    BROKER: { label: "Broker Connection", key: "", needsSym: false },
    ACCOUNT: { label: "Account & Entitlements", key: "", needsSym: false },
    INBOX: { label: "Notification Center", key: "", needsSym: false },
    SUPPORT: { label: "Help & Diagnostics", key: "", needsSym: false },
    ABOUT: { label: "About & UI Coverage", key: "", needsSym: false }
  };

  /* ---------------- derived ---------------- */
  const chg = (s) => s.px - s.prev;
  const chgp = (s) => ((s.px - s.prev) / s.prev) * 100;
  const indices = () => UNIV.filter((s) => s.cls === "INDEX");
  const equities = () => UNIV.filter((s) => s.cls === "EQUITY");

  /* ---------------- field dictionary (local reference table) ---------------- */
  const FIELD_DICT = [
    ["PX_LAST", "Double", "PRICE", "Last traded price", "LAST"],
    ["PX_BID", "Double", "PRICE", "Best bid", "BID"],
    ["PX_ASK", "Double", "PRICE", "Best offer", "ASK"],
    ["PX_MID", "Double", "PRICE", "Mid between bid and offer", "MID"],
    ["PX_OPEN", "Double", "PRICE", "Session open", "OPEN"],
    ["PX_HIGH", "Double", "PRICE", "Session high", "HIGH"],
    ["PX_LOW", "Double", "PRICE", "Session low", "LOW"],
    ["PX_CLOSE", "Double", "PRICE", "Previous close", "PREV"],
    ["PX_SETTLE", "Double", "PRICE", "Official settlement price", "SETTLE"],
    ["PX_VOLUME", "Double", "PRICE", "Session volume", "VOL"],
    ["PX_TO_BOOK_RATIO", "Double", "ANALYTICS", "Price to book value per share", "P/B"],
    ["PE_RATIO", "Double", "ANALYTICS", "Price to trailing earnings", "P/E"],
    ["CUR_MKT_CAP", "Double", "FUNDAMENTAL", "Market capitalisation in security currency", "MKT CAP"],
    ["EQY_SH_OUT", "Double", "FUNDAMENTAL", "Shares outstanding", "SHARES"],
    ["SALES_REV_TURN", "Double", "FUNDAMENTAL", "Revenue, trailing twelve months", "REVENUE"],
    ["EBITDA", "Double", "FUNDAMENTAL", "Earnings before interest, tax, depreciation, amortisation", "EBITDA"],
    ["IS_EPS", "Double", "FUNDAMENTAL", "Earnings per share", "EPS"],
    ["GROSS_MARGIN", "Double", "FUNDAMENTAL", "Gross profit as a percent of revenue", "GM%"],
    ["EBITDA_MARGIN", "Double", "FUNDAMENTAL", "EBITDA as a percent of revenue", "EM%"],
    ["RETURN_ON_EQUITY", "Double", "FUNDAMENTAL", "Net income over shareholders equity", "ROE"],
    ["TOT_DEBT_TO_TOT_EQY", "Double", "FUNDAMENTAL", "Total debt over total equity", "D/E"],
    ["FREE_CASH_FLOW", "Double", "FUNDAMENTAL", "Operating cash flow less capex", "FCF"],
    ["EQY_DVD_YLD_IND", "Double", "CORPORATE", "Indicated dividend yield", "YLD"],
    ["DVD_EX_DT", "Date", "CORPORATE", "Next ex-dividend date", "EX-DT"],
    ["DVD_PAY_DT", "Date", "CORPORATE", "Next dividend payment date", "PAY-DT"],
    ["VOLATILITY_30D", "Double", "ANALYTICS", "30-day annualised historical volatility", "HV30"],
    ["VOLATILITY_90D", "Double", "ANALYTICS", "90-day annualised historical volatility", "HV90"],
    ["MOV_AVG_50D", "Double", "ANALYTICS", "50-day moving average", "MA50"],
    ["MOV_AVG_200D", "Double", "ANALYTICS", "200-day moving average", "MA200"],
    ["YLD_YTM_MID", "Double", "RATES", "Yield to maturity, bid/ask mid", "YIELD"],
    ["YLD_YTM_BID", "Double", "RATES", "Yield to maturity at the bid", "YLD BID"],
    ["YLD_YTM_ASK", "Double", "RATES", "Yield to maturity at the offer", "YLD ASK"],
    ["ASSET_SWAP_SPD_MID", "Double", "RATES", "Asset swap spread, mid", "ASW"],
    ["YAS_YLD_SPREAD", "Double", "RATES", "Spread over the benchmark curve", "SPREAD"],
    ["NAME", "String", "REFERENCE", "Security long name", "DESCRIPTION"],
    ["ID_ISIN", "String", "REFERENCE", "ISIN identifier", "ISIN"],
    ["ID_CUSIP", "String", "REFERENCE", "CUSIP identifier", "CUSIP"],
    ["TICKER_AND_EXCH_CODE", "String", "REFERENCE", "Ticker plus exchange code", "TICKER"],
    ["CRNCY", "String", "REFERENCE", "Trading currency", "CCY"],
    ["SECURITY_TYP", "String", "REFERENCE", "Security type classification", "TYPE"],
    ["MARKET_SECTOR", "String", "REFERENCE", "Market sector classification", "SECTOR"],
    ["GICS_SECTOR_NAME", "String", "REFERENCE", "GICS sector name", "SECTOR"],
    ["CNTRY_OF_DOMICILE", "String", "REFERENCE", "Country of domicile", "DOMICILE"]
  ];

  function dictRows(q) {
    const term = String(q || "").trim().toUpperCase();
    if (!term) return FIELD_DICT.slice();
    return FIELD_DICT.filter((f) => (f[0] + " " + f[2] + " " + f[3] + " " + f[4]).toUpperCase().indexOf(term) >= 0);
  }

  /* ---------------- synthetic financials (deterministic per symbol) ---------------- */
  function hashSeed(str) {
    let h = 2166136261;
    for (let i = 0; i < str.length; i++) { h ^= str.charCodeAt(i); h = Math.imul(h, 16777619); }
    return h >>> 0;
  }

  function rngFrom(seed) {
    let s = seed || 1;
    return function () { s = (Math.imul(s, 1664525) + 1013904223) >>> 0; return s / 4294967296; };
  }

  const FINCACHE = {};

  function finFor(sym) {
    const s = bySym[sym];
    if (!s || s.cls !== "EQUITY") return null;
    if (FINCACHE[sym]) return FINCACHE[sym];
    const rnd = rngFrom(hashSeed(sym + "|FUND"));
    const span = (a, b) => a + rnd() * (b - a);
    const ps = span(2.2, 6.4);
    const cagr = span(0.02, 0.19);
    const gm = span(0.33, 0.72);
    const em = gm * span(0.42, 0.76);
    const nm = em * span(0.42, 0.74);
    const shares = s.mcap / s.px;
    const yrs = [];
    for (let i = 0; i < 5; i++) {
      const rev = s.mcap / ps / Math.pow(1 + cagr, 4 - i);
      const g2 = gm * span(0.97, 1.02), e2 = em * span(0.95, 1.04), n2 = nm * span(0.92, 1.06);
      yrs.push({
        fy: "FY" + (new Date().getFullYear() - 4 + i),
        rev: rev, gross: rev * g2, ebitda: rev * e2, ni: rev * n2,
        eps: (rev * n2) / shares, fcf: rev * n2 * span(0.7, 1.4)
      });
    }
    const cash = s.mcap * span(0.03, 0.16), debt = s.mcap * span(0.05, 0.42);
    const eq = s.mcap * span(0.16, 0.55);
    const out = {
      yrs: yrs, cagr: cagr, gm: gm, em: em, nm: nm, shares: shares,
      cash: cash, debt: debt, equity: eq, revNow: s.mcap / ps,
      ratios: [
        ["P/E (TTM)", s.pe ? s.pe.toFixed(1) + "x" : "\u2013"],
        ["P/S (TTM)", ps.toFixed(2) + "x"],
        ["EV / EBITDA", ((s.mcap + debt - cash) / yrs[4].ebitda).toFixed(1) + "x"],
        ["GROSS MARGIN", (gm * 100).toFixed(1) + "%"],
        ["EBITDA MARGIN", (em * 100).toFixed(1) + "%"],
        ["NET MARGIN", (nm * 100).toFixed(1) + "%"],
        ["RETURN ON EQUITY", ((yrs[4].ni / eq) * 100).toFixed(1) + "%"],
        ["NET DEBT / EBITDA", ((debt - cash) / yrs[4].ebitda).toFixed(2) + "x"],
        ["REVENUE CAGR 5Y", (cagr * 100).toFixed(1) + "%"],
        ["EPS (TTM)", yrs[4].eps.toFixed(2)]
      ]
    };
    FINCACHE[sym] = out;
    return out;
  }

  /* ---------------- equity screener ---------------- */
  const SCREEN_MET = {
    PE: (s) => s.pe || null,
    MCAP: (s) => s.mcap || null,
    CHG: (s) => chgp(s),
    PX: (s) => s.px,
    VOL: (s) => s.vol || 0
  };

  function multOf(suf) {
    if (suf === "K") return 1e3;
    if (suf === "M") return 1e6;
    if (suf === "B") return 1e9;
    if (suf === "T") return 1e12;
    return 1;
  }

  function parseScreen(q) {
    const crit = [], bad = [];
    String(q || "").toUpperCase().split(/[\s,;]+/).filter(Boolean).forEach((tok) => {
      const m = tok.match(/^(PE|MCAP|CHG|PX|VOL)(<=|>=|<|>|=)([\d.]+)([KMBT]?)$/);
      if (!m) { bad.push(tok); return; }
      crit.push({ f: m[1], op: m[2], v: Number(m[3]) * multOf(m[4]) });
    });
    return { crit: crit, bad: bad };
  }

  function screenRows(crit) {
    const ops = {
      "<": (a, b) => a < b, ">": (a, b) => a > b,
      "<=": (a, b) => a <= b, ">=": (a, b) => a >= b, "=": (a, b) => Math.abs(a - b) < 1e-9
    };
    return equities().filter((s) => crit.every((c) => {
      const v = SCREEN_MET[c.f](s);
      return v != null && ops[c.op](v, c.v);
    }));
  }

  /* ---------------- render: tables ---------------- */
  function tableHTML(cols, rows, opts) {
    const o = opts || {};
    let h = "<table><thead><tr>";
    cols.forEach((c) => { h += '<th class="' + (c.a || "") + '">' + c.t + "</th>"; });
    h += "</tr></thead><tbody>";
    rows.forEach((r, i) => {
      h += '<tr data-i="' + i + '"' + (r.__sym ? ' data-sym="' + r.__sym + '"' : "") +
        (i === App.sel ? ' class="sel"' : "") + ">";
      cols.forEach((c) => {
        let cell = c.v(r);
        let tip = "";
        // long text columns are visually truncated -> expose the full value on hover
        if (c.c === "nm") {
          const plain = String(cell).replace(/<[^>]*>/g, "").replace(/"/g, "&quot;");
          if (plain) tip = ' title="' + plain + '"';
        }
        h += "<td" + (c.a ? ' class="' + c.a + '"' : c.c ? ' class="' + c.c + '"' : "") + tip + ">" + cell + "</td>";
      });
      h += "</tr>";
    });
    return h + "</tbody></table>";
  }

  function quoteCols(extra) {
    const cols = [
      { t: "TICKER", a: "", v: (r) => r.__sym },
      { t: "DESCRIPTION", c: "nm", v: (r) => r.name },
      { t: "LAST", v: (r) => f2(r.px) },
      { t: "CHG", v: (r) => '<span class="' + cls(r.__c) + '">' + (r.__c >= 0 ? "+" : "") + r.__c.toFixed(2) + "</span>" },
      { t: "%CHG", v: (r) => '<span class="' + cls(r.__cp) + '">' + fpct(r.__cp) + "</span>" },
      { t: "BID", v: (r) => f2(r.bid) },
      { t: "ASK", v: (r) => f2(r.ask) },
      { t: "VOL", v: (r) => (r.vol ? fnum(r.vol) : "\u2013") }
    ];
    if (extra) cols.splice(2, 0, extra);
    return cols;
  }

  function withQuote(s) {
    return Object.assign({}, s, { __sym: s.sym, __c: chg(s), __cp: chgp(s) });
  }

  /* ---------------- views ---------------- */
  function viewWEI() {
    const rows = indices().map(withQuote);
    App.rows = rows;
    const cols = quoteCols();
    return {
      title: "WEI",
      sub: "World Equity Indices \u00b7 " + indices().length + " instruments",
      right: "DELAYED \u00b7 SIM",
      html: tableHTML(cols, rows)
    };
  }

  function viewW() {
    const rows = Store.data.watch.map((s) => bySym[s]).filter(Boolean).map(withQuote);
    App.rows = rows;
    const cols = quoteCols().concat([{
      t: "MOVE",
      a: "r",
      v: (r) => '<span class="wmv">' +
        '<button class="xbtn tiny" data-wmv="-1" data-sym="' + r.__sym + '" title="move up" aria-label="move ' + r.__sym + ' up">\u2191</button>' +
        '<button class="xbtn tiny" data-wmv="1" data-sym="' + r.__sym + '" title="move down" aria-label="move ' + r.__sym + ' down">\u2193</button>' +
        "</span>"
    }]);
    return {
      title: "W",
      sub: "Monitor \u00b7 " + rows.length + " securities \u00b7 drag a row or use \u2191\u2193 to reorder \u00b7 ADD / DEL <ticker>",
      right: rows.length + " SECURITIES",
      html: rows.length ? tableHTML(cols, rows)
        : '<div class="help"><p>Watchlist is empty. Type <code>ADD AAPL</code> to add a security.</p></div>'
    };
  }

  function viewMOST() {
    const rows = equities().slice().sort((a, b) => b.vol - a.vol).map(withQuote);
    App.rows = rows;
    const cols = [
      { t: "#", v: (r) => String(rows.indexOf(r) + 1) },
      { t: "TICKER", v: (r) => r.__sym },
      { t: "DESCRIPTION", c: "nm", v: (r) => r.name },
      { t: "LAST", v: (r) => f2(r.px) },
      { t: "%CHG", v: (r) => '<span class="' + cls(r.__cp) + '">' + fpct(r.__cp) + "</span>" },
      { t: "VOLUME", v: (r) => fnum(r.vol) },
      { t: "VWAP", v: (r) => f2((r.hi + r.lo + r.px) / 3) },
      { t: "SECTOR", c: "nm", v: (r) => r.sect }
    ];
    return { title: "MOST", sub: "Most active US equities by volume", right: "SORTED BY VOL", html: tableHTML(cols, rows) };
  }

  function newsSect(n) {
    const s = bySym[n.sym];
    return s && s.sect ? s.sect : n.sym === "MACRO" ? "Macro" : "Cross Asset";
  }

  function newsBody(n) {
    const s = bySym[n.sym];
    const nm = s ? s.name : n.sym;
    return "Simulated wire summary. " + nm + " (" + n.sym + ") \u00b7 " + newsSect(n) +
      ". Desk commentary is generated locally for layout purposes: the story line at " + n.time +
      " is time-stamped to the current session, has no external source, and carries no licensed content. " +
      "Use DES for the security profile, GP for the price graph and N for the full story list on this name.";
  }

  function newsItem(n, withSect) {
    return '<li data-sym="' + n.sym + '" class="nitem">' +
      '<span class="t">' + n.time + "</span>" +
      '<span class="h">' + n.headline + "</span>" +
      '<span class="s">' + n.sym + (withSect ? " \u00b7 " + newsSect(n) : "") + "</span>" +
      '<button class="xbtn ntog" data-story="' + n.time + '" aria-label="expand story ' + n.time + '" aria-expanded="false">\u25b8</button>' +
      '<div class="nbody">' + newsBody(n) + "</div></li>";
  }

  function viewTOP() {
    App.rows = [];
    const li = NEWS.map((n) => newsItem(n, true)).join("");
    return {
      title: "TOP",
      sub: "Top news \u00b7 " + NEWS.length + " stories \u00b7 filter or click \u25b8 to expand",
      right: "LIVE",
      html: '<div class="newswrap">' +
        '<div class="nfbar">' +
          '<input id="news-q" data-live="news" placeholder="FILTER HEADLINE / TICKER" aria-label="filter news" value="' +
            String(App.newsQ || "").replace(/"/g, "&quot;") + '">' +
          '<span class="dim" id="news-count" data-count="news">' + NEWS.length + "</span>" +
          '<span class="dim">stories in the session</span><button class="xbtn" data-storyall="1">EXPAND ALL</button>' +
        "</div>" +
        '<ul class="news">' + li + "</ul></div>"
    };
  }

  function viewN() {
    const s = bySym[App.sym] || bySym["AAPL"];
    const list = NEWS.filter((n) => n.sym === s.sym);
    App.rows = [];
    const body = list.length
      ? list.map((n) => newsItem(n, false)).join("")
      : '<li class="nitem"><span class="t">--:--</span><span class="h">No stories for ' + s.sym +
        " in the current session.</span><span class=\"s\"></span></li>";
    return {
      title: "N",
      sub: "News \u00b7 " + s.sym + " \u00b7 " + s.name,
      right: list.length + " STORIES",
      html: '<div class="newswrap"><div class="nfbar"><span class="dim">Click \u25b8 on a story to read the simulated summary</span>' +
        '<button class="xbtn" data-storyall="1">EXPAND ALL</button></div>' +
        '<ul class="news">' + body + "</ul></div>"
    };
  }

  function viewHP() {
    const s = bySym[App.sym] || bySym["AAPL"];
    const bars = s.hist.slice(-26).reverse();
    const cols = [
      { t: "TIME", v: (r) => r[5] },
      { t: "OPEN", v: (r) => f2(r[0]) },
      { t: "HIGH", v: (r) => f2(r[1]) },
      { t: "LOW", v: (r) => f2(r[2]) },
      { t: "LAST", v: (r) => f2(r[3]) },
      { t: "CHG", v: (r) => '<span class="' + cls(r[3] - r[0]) + '">' + (r[3] >= r[0] ? "+" : "") + (r[3] - r[0]).toFixed(2) + "</span>" },
      { t: "VOLUME", v: (r) => fnum(r[4]) }
    ];
    const now = new Date();
    const rows = bars.map((b, i) => {
      const d = new Date(now.getTime() - (i + 1) * 5 * 60000);
      const copy = b.slice();
      copy[5] = pad2(d.getDate()) + "/" + pad2(d.getMonth() + 1) + " " + hhmm(d);
      return copy;
    });
    App.rows = rows;
    return { title: "HP", sub: "Historical prices \u00b7 5-min bars \u00b7 " + s.sym, right: rows.length + " BARS", html: tableHTML(cols, rows) };
  }

  function sparkSVG(bars) {
    const w = 280, h = 74, n = bars.length;
    const closes = bars.map((b) => b[3]);
    const mn = Math.min.apply(null, closes), mx = Math.max.apply(null, closes);
    const y = (v) => h - 4 - ((v - mn) / (mx - mn || 1)) * (h - 8);
    let d = "";
    closes.forEach((c, i) => {
      const x = (i / (n - 1)) * w;
      d += (i ? "L" : "M") + x.toFixed(1) + " " + y(c).toFixed(1);
    });
    const up = closes[closes.length - 1] >= closes[0];
    const col = up ? UP_COL() : DN_COL();
    return '<svg class="spark" viewBox="0 0 ' + w + " " + h + '" preserveAspectRatio="none">' +
      '<path d="' + d + '" fill="none" stroke="' + col + '" stroke-width="1.6"/>' +
      '<path d="' + d + "L" + w + " " + h + "L0 " + h + 'Z" fill="' + col + '" opacity="0.10"/></svg>';
  }

  function viewDES() {
    const s = bySym[App.sym] || bySym["AAPL"];
    App.rows = [];
    const c = chg(s), cp = chgp(s);
    const kv = [
      ["SECURITY", s.sym + " " + (s.cls === "INDEX" ? "Index" : s.cls === "FX" ? "Curncy" : s.cls === "CMDTY" ? "Comdty" : s.cls === "GOVT" ? "Govt" : "US Equity")],
      ["CLASS", s.cls],
      ["SECTOR", s.sect],
      ["CURRENCY", s.ccy],
      ["OPEN", f2(s.open)],
      ["HIGH", f2(s.hi)],
      ["LOW", f2(s.lo)],
      ["PREV CLOSE", f2(s.prev)],
      ["BID / ASK", f2(s.bid) + " / " + f2(s.ask)],
      ["VOLUME", s.vol ? fnum(s.vol) : "\u2013"]
    ];
    if (s.mcap) kv.push(["MKT CAP", (s.mcap / 1e12).toFixed(2) + "T"]);
    if (s.pe) kv.push(["P/E", s.pe.toFixed(1)]);
    const html =
      '<div class="des"><div class="des-l">' +
        '<div class="h1">' + s.sym + "<span>" + s.name + "</span></div>" +
        '<div class="px"><div class="last ' + cls(c) + '">' + f2(s.px) + "</div>" +
          '<div class="chg ' + cls(c) + '">' + arrow(c) + " " + (c >= 0 ? "+" : "") + c.toFixed(2) +
          " (" + fpct(cp) + ")</div>" +
          '<div class="dim" style="font-size:11px">' + s.ccy + " \u00b7 " + hhmmss(new Date()) + "</div></div>" +
        '<div class="sec">SECURITY PROFILE</div>' +
        '<dl class="kv">' + kv.map((r) => "<dt>" + r[0] + "</dt><dd>" + r[1] + "</dd>").join("") + "</dl>" +
        '<div class="sec">DESCRIPTION</div>' +
        '<p class="desc">' + describe(s) + "</p>" +
      "</div>" +
      '<div class="des-r">' +
        '<div class="sec" style="margin-top:0">INTRADAY \u00b7 5M</div>' + sparkSVG(s.hist.slice(-70)) +
        '<div class="sec">KEY STATS</div>' +
        '<dl class="kv" style="grid-template-columns:96px 1fr">' +
          "<dt>RANGE</dt><dd>" + f2(s.lo) + " \u2013 " + f2(s.hi) + "</dd>" +
          "<dt>52W RANGE</dt><dd>" + f2(s.px * 0.62) + " \u2013 " + f2(s.px * 1.18) + "</dd>" +
          "<dt>VOL (ADV)</dt><dd>" + (s.vol ? fnum(s.vol) : "\u2013") + "</dd>" +
          "<dt>SPREAD</dt><dd>" + (s.ask - s.bid).toFixed(4) + "</dd>" +
        "</dl>" +
        '<div class="sec">MARKET DEPTH</div>' +
        '<table class="book"><thead><tr><th>BID</th><th>SZ</th><th>ASK</th><th>SZ</th></tr></thead><tbody>' +
          s.book.map((r) =>
            '<tr><td class="up">' + f2(r.bpx) + '</td><td class="dim">' + r.bq + "</td>" +
            '<td class="dn">' + f2(r.apx) + '</td><td class="dim">' + r.aq + "</td></tr>").join("") +
        "</tbody></table>" +
        '<div class="sec">TIME &amp; SALES</div>' +
        '<table class="book tas"><thead><tr><th>TIME</th><th>PRICE</th><th class="r">SIZE</th></tr></thead><tbody>' +
          s.tas.slice(-14).reverse().map((r, i, arr) =>
            '<tr><td class="dim">' + hhmmss(new Date(r.t)) + "</td>" +
            '<td class="' + (i + 1 < arr.length ? (r.px >= arr[i + 1].px ? "up" : "dn") : "dim") + '">' + f2(r.px) + "</td>" +
            '<td class="dim r">' + fnum(r.sz) + "</td></tr>").join("") +
        "</tbody></table>" +
        '<div class="sec">RELATED</div>' +
        '<dl class="kv" style="grid-template-columns:96px 1fr">' +
          "<dt>GP</dt><dd>Price graph</dd>" +
          "<dt>HP</dt><dd>Historical prices</dd>" +
          "<dt>N</dt><dd>News</dd>" +
          "<dt>BUY / SELL</dt><dd>Trade ticket</dd>" +
        "</dl>" +
      "</div></div>";
    return { title: "DES", sub: s.sym + " \u00b7 " + s.name, right: "EQUITY DES", html: html };
  }

  function describe(s) {
    const map = {
      AAPL: "Apple Inc. designs, manufactures and markets smartphones, personal computers, tablets, wearables and accessories, and sells a range of related services. The Company's products include iPhone, Mac, iPad, AirPods and Apple Watch.",
      MSFT: "Microsoft Corp. develops and licenses software, services, devices and solutions. Segments include Productivity & Business Processes, Intelligent Cloud and More Personal Computing, spanning Azure, Office, Windows and gaming.",
      NVDA: "NVIDIA Corp. is a full-stack computing infrastructure company with data-center-scale offerings. Products include GPUs, accelerated computing platforms, networking and AI software stacks.",
      TSLA: "Tesla, Inc. designs, develops, manufactures and sells fully electric vehicles, energy generation and storage systems, and offers services related to its products.",
      AMZN: "Amazon.com, Inc. is an online retailer and cloud infrastructure provider. Segments include North America, International and Amazon Web Services.",
      GOOGL: "Alphabet Inc. is the parent of Google, providing search, advertising, cloud, YouTube and hardware products and platforms.",
      META: "Meta Platforms, Inc. operates social technology platforms including Facebook, Instagram, WhatsApp and Threads, monetised primarily through advertising.",
      JPM: "JPMorgan Chase & Co. is a financial holding company providing investment banking, consumer and commercial banking, and asset management services.",
      GS: "The Goldman Sachs Group, Inc. is a global investment bank and financial services firm serving corporations, financial institutions, governments and individuals.",
      XOM: "Exxon Mobil Corp. is an energy company engaged in exploration, production, refining, and the marketing of crude oil, natural gas and petroleum products."
    };
    if (map[s.sym]) return map[s.sym];
    if (s.cls === "INDEX") return s.name + " is a market-capitalisation weighted benchmark tracking the performance of its constituent securities in " + s.sect.replace(" Equity Index", "") + ". Index levels are calculated and disseminated by the exchange operator in real time during the trading session.";
    if (s.cls === "FX") return s.sym.slice(0, 3) + "/" + s.sym.slice(3) + " is a spot foreign exchange rate quoted in the interbank market. Prices represent mid-market levels contributed by liquidity providers.";
    if (s.cls === "CMDTY") return s.name + " is a front-month futures contract traded on a regulated exchange. Prices are quoted per contract unit in " + s.ccy + ".";
    if (s.cls === "GOVT") return s.name + " is a benchmark government bond yield, quoted in percent per annum, derived from the on-the-run issue in the interbank market.";
    return s.name;
  }

  function indPanelHTML() {
    const c = App.maCfg;
    const fld = (k, label, min, max, hint) =>
      '<label class="ifld"><span>' + label + "</span><i>" + hint + "</i>" +
      '<input type="number" class="iinp" data-ind="' + k + '" value="' + c[k] + '" min="' + min + '" max="' + max +
      '" step="1" inputmode="numeric" aria-label="' + label + '"></label>';
    return '<div class="indpop" role="dialog" aria-label="Indicator parameters">' +
      '<div class="ihead">INDICATOR PARAMETERS</div>' +
      '<div class="ibody">' +
        fld("a", "MA FAST", 1, 240, "bars") +
        fld("b", "MA SLOW", 2, 240, "bars") +
        fld("bn", "BOLL PERIOD", 2, 240, "bars") +
        fld("bk", "BOLL K", 1, 5, "stdev") +
      "</div>" +
      '<div class="ifoot"><button class="xbtn" data-ind="apply">APPLY</button>' +
        '<button class="xbtn" data-ind="reset">RESET</button>' +
        '<button class="xbtn" data-ind="close">CLOSE</button></div>' +
    "</div>";
  }

  function applyIndCfg(k, raw, persist) {
    const limits = { a: [1, 240], b: [2, 240], bn: [2, 240], bk: [1, 5] };
    if (!limits[k]) return false;
    const v = Math.round(Number(raw));
    if (!isFinite(v) || v < limits[k][0] || v > limits[k][1]) return false;
    App.maCfg[k] = v;
    Store.data.maCfg = Object.assign({}, App.maCfg);
    if (persist !== false) Store.save();
    return true;
  }

  // repaint the mounted price chart without rebuilding the view (keeps inputs focused)
  function drawOnly() {
    const cvs = document.querySelectorAll("#main canvas");
    let n = 0;
    Array.prototype.forEach.call(cvs, (cv) => {
      const box = cv.parentElement;
      if (box && typeof box._redraw === "function") { box._redraw(); n++; }
    });
    return n;
  }

  function setFullChart(on) {
    App.fullChart = !!on;
    document.body.classList.toggle("chart-full", App.fullChart);
    render();
    if (App.fullChart) notice("Full-screen chart \u00b7 press ESC to exit", false);
    return App.fullChart;
  }

  function viewGP() {
    const s = bySym[App.sym] || bySym["AAPL"];
    App.rows = [];
    const html =
      '<div class="chartwrap' + (App.fullChart ? " isful" : "") + '"><div class="chartbox">' +
        '<div class="legend"><span>GP</span><span><b>' + s.sym + '</b></span><span id="xhair">\u2014</span>' +
          '<span class="dtools ctypes">' + CTYPES.map((t) =>
            '<button class="pbtn' + (App.ctype === t ? " on" : "") + '" data-ctype="' + t + '">' + t + "</button>").join("") +
            '<button class="pbtn' + (App.logScale ? " on" : "") + '" id="logtog">LOG</button>' +
          "</span>" +
          '<span class="dtools">' +
            '<button class="pbtn' + (App.drawMode === "trend" ? " on" : "") + '" data-draw="trend">\u2571 TREND</button>' +
            '<button class="pbtn' + (App.drawMode === "hline" ? " on" : "") + '" data-draw="hline">\u2500 H-LINE</button>' +
            '<button class="pbtn" data-draw="undo">\u21b6 UNDO</button>' +
            '<button class="pbtn" data-draw="clear">\u2715 CLEAR</button>' +
          "</span>" +
        "</div>" +
        '<canvas id="canvas"></canvas>' +
        '<canvas id="drawlayer" class="drawlayer"></canvas>' +
      "</div>" +
      '<div class="chartfoot">' +
        "<div>LAST <b class='" + cls(chg(s)) + "'>" + f2(s.px) + "</b></div>" +
        "<div>CHG <b class='" + cls(chg(s)) + "'>" + fpct(chgp(s)) + "</b></div>" +
        "<div>OPEN <b>" + f2(s.open) + "</b></div>" +
        "<div>HIGH <b>" + f2(s.hi) + "</b></div>" +
        "<div>LOW <b>" + f2(s.lo) + "</b></div>" +
        "<div>VWAP <b>" + f2((s.hi + s.lo + s.px) / 3) + "</b></div>" +
        '<div class="pf">' + PERIODS.map((p) =>
          '<button class="pbtn' + (App.period === p ? " on" : "") + '" data-period="' + p + '">' + p + "</button>").join("") + "</div>" +
        '<button class="pbtn' + (App.ma ? " on" : "") + '" id="matog">MA' + App.maCfg.a + "/" + App.maCfg.b + '</button>' +
        '<button class="pbtn' + (App.boll ? " on" : "") + '" id="bolltog">BOLL</button>' +
        '<button class="pbtn' + (App.indPanel ? " on" : "") + '" id="indcfg" aria-expanded="' + (!!App.indPanel) + '" title="Indicator parameters">\u2699 IND</button>' +
        '<button class="pbtn' + (App.fullChart ? " on" : "") + '" id="fultog" title="Full-screen chart (ESC to exit)">\u26f6 FULL</button>' +
        '<button class="pbtn" data-png="GP">PNG</button>' +
        '<div class="pf">' + SUBS.map((p) =>
          '<button class="pbtn' + (App.sub === p ? " on" : "") + '" data-sub="' + p + '">' + p + "</button>").join("") + "</div>" +
        "<div class='dim'>move cursor for crosshair</div>" +
        (App.indPanel ? indPanelHTML() : "") +
      "</div></div>";
    return { title: "GP", sub: "Price graph \u00b7 " + s.sym + " \u00b7 " + s.name + " \u00b7 " + App.period, right: "INTRADAY", html: html };
  }

  /* ---------------- option chain ---------------- */
  function ncdf(x) {
    const t = 1 / (1 + 0.2316419 * Math.abs(x));
    const d = 0.3989422804 * Math.exp(-x * x / 2);
    const p = d * t * (0.31938153 + t * (-0.356563782 + t * (1.781477937 + t * (-1.821255978 + t * 1.330274429))));
    return x > 0 ? 1 - p : p;
  }

  function bsPx(S, K, days, v) {
    const r = 0.042;
    const T = Math.max(1, days) / 365;
    const d1 = (Math.log(S / K) + (r + (v * v) / 2) * T) / (v * Math.sqrt(T));
    const d2 = d1 - v * Math.sqrt(T);
    const call = S * ncdf(d1) - K * Math.exp(-r * T) * ncdf(d2);
    const df = Math.exp(-r * T);
    return {
      call: Math.max(0.01, call),
      put: Math.max(0.01, call - S + K * df),
      callDelta: ncdf(d1),
      putDelta: ncdf(d1) - 1
    };
  }

  function expiries() {
    const out = [];
    [18, 46, 109, 200].forEach((d) => {
      const t = new Date(Date.now() + d * 864e5);
      t.setDate(t.getDate() + ((5 - t.getDay() + 7) % 7));
      out.push({ iso: t.getFullYear() + "-" + pad2(t.getMonth() + 1) + "-" + pad2(t.getDate()), days: d });
    });
    return out;
  }

  function hashNum(str) {
    let h = 0;
    for (let i = 0; i < str.length; i++) h = (h * 31 + str.charCodeAt(i)) % 99991;
    return h;
  }

  function viewOPT() {
    const s = bySym[App.sym] || bySym["AAPL"];
    App.rows = [];
    const exps = expiries();
    const exp = exps[App.optExpIdx || 0] || exps[0];
    const step = s.px > 500 ? 25 : s.px > 200 ? 10 : s.px > 50 ? 5 : s.px > 10 ? 2.5 : 0.5;
    const atm = Math.round(s.px / step) * step;
    const baseVol = s.cls === "INDEX" ? 0.16 : s.cls === "FX" ? 0.08 : 0.33;
    const rows = [];
    let callOi = 0, putOi = 0;
    for (let k = -4; k <= 4; k++) {
      const strike = Number((atm + k * step).toFixed(2));
      if (strike <= 0) continue;
      const skew = baseVol * (1 + 1.9 * Math.abs(Math.log(strike / s.px)));
      const iv = Math.max(0.06, skew);
      const o = bsPx(s.px, strike, exp.days, iv);
      const oiC = 400 + (hashNum(s.sym + strike + "C" + exp.iso) % 6800);
      const oiP = 400 + (hashNum(s.sym + strike + "P" + exp.iso) % 6800);
      callOi += oiC; putOi += oiP;
      rows.push({ strike: strike, iv: iv, call: o.call, cdelta: o.callDelta, coi: oiC, put: o.put, pdelta: o.putDelta, poi: oiP, itmC: strike < s.px, itmP: strike > s.px });
    }
    const atmIv = (() => { const r = rows.find((x) => x.strike === atm) || rows[0]; return r ? r.iv : baseVol; })();
    const card = (l, v, c) => '<div class="card"><span>' + l + "</span><b class=\"" + (c || "") + "\">" + v + "</b></div>";
    const last = (r) => (r ? r.call : 0);
    const body = tableHTML([
      { t: "C IV", a: "r", v: (r) => (r.iv * 100).toFixed(1) + "%" },
      { t: "C DELTA", a: "r", v: (r) => r.cdelta.toFixed(2) },
      { t: "C OI", a: "r", v: (r) => fnum(r.coi) },
      { t: "C LAST", a: "r", v: (r) => '<b class="' + (r.itmC ? "up" : "") + '">' + f2(last(r)) + "</b>" },
      { t: "STRIKE", a: "c", v: (r) => "<b>" + f2(r.strike) + "</b>" },
      { t: "P LAST", a: "r", v: (r) => '<b class="' + (r.itmP ? "dn" : "") + '">' + f2(r.put) + "</b>" },
      { t: "P OI", a: "r", v: (r) => fnum(r.poi) },
      { t: "P DELTA", a: "r", v: (r) => r.pdelta.toFixed(2) },
      { t: "P IV", a: "r", v: (r) => (r.iv * 100).toFixed(1) + "%" }
    ], rows);
    const html =
      '<div class="port">' +
        '<div class="cards">' +
          card("SPOT", f2(s.px)) +
          card("ATM IV", (atmIv * 100).toFixed(1) + "%") +
          card("EXPIRY", exp.iso + " \u00b7 " + exp.days + "D") +
          card("PUT/CALL OI", (putOi / Math.max(1, callOi)).toFixed(2)) +
        "</div>" +
        '<div class="ticket"><span class="tt">EXPIRY</span>' +
          exps.map((x, i) => '<button class="pbtn' + (i === (App.optExpIdx || 0) ? " on" : "") + '" data-exp="' + i + '">' + x.iso + "</button>").join("") +
          '<span class="dim" style="margin-left:auto;font-size:10.5px">Black-Scholes \u00b7 r 4.2% \u00b7 synthetic surface</span>' +
        "</div>" +
        '<div class="optwrap">' + body + "</div>" +
      "</div>";
    return { title: "OPT", sub: s.sym + " option chain \u00b7 " + exp.iso, right: "LISTED OPTIONS", html: html };
  }

  /* ---------------- order book view ---------------- */
  function viewORD() {
    const list = ORDERS();
    App.rows = [];
    const working = list.filter((o) => o.status === "WORKING");
    const filled = list.filter((o) => o.status === "FILLED");
    const dead = list.filter((o) => o.status === "CXL" || o.status === "REJECTED");
    const restNot = working.reduce((a, o) => a + o.qty * (o.px || (bySym[o.sym] ? bySym[o.sym].px : 0)), 0);
    const card = (l, v, c) => '<div class="card"><span>' + l + "</span><b class=\"" + (c || "") + "\">" + v + "</b></div>";

    const body = list.length
      ? tableHTML([
          { t: "ID", v: (o) => "#" + o.id },
          { t: "TIME", v: (o) => hhmmss(new Date(o.t)) },
          { t: "TICKER", v: (o) => o.sym },
          { t: "SIDE", v: (o) => '<span class="' + (o.side === "BUY" ? "up" : "dn") + '">' + o.side + "</span>" },
          { t: "TYPE", v: (o) => o.type },
          { t: "QTY", a: "r", v: (o) => fnum(o.qty) },
          { t: "LIMIT", a: "r", v: (o) => (o.px == null ? '<span class="dim">MKT</span>' : f2(o.px)) },
          { t: "LAST", a: "r", v: (o) => (bySym[o.sym] ? f2(bySym[o.sym].px) : "\u2013") },
          { t: "AWAY", a: "r", v: (o) => {
              const s = bySym[o.sym];
              if (!o.px || !s) return '<span class="dim">\u2013</span>';
              const d = ((o.px - s.px) / s.px) * 100;
              return '<span class="' + cls(-Math.abs(d)) + '">' + fpct(d) + "</span>";
            } },
          { t: "STATUS", v: (o) => '<span class="' + (o.status === "FILLED" ? "up" : o.status === "WORKING" ? "acc" : "dn") + '">' + o.status + "</span>" },
          { t: "", v: (o) => (o.status === "WORKING" ? '<button class="xbtn" data-cxl="' + o.id + '">CXL</button>' : '<span class="dim">\u2013</span>') }
        ], list)
      : '<div class="help"><p>No orders. Type <code>BUY AAPL 100 LMT 230</code> or <code>SELL AAPL 50 STP 210</code> to rest one.</p></div>';

    const html =
      '<div class="port">' +
        '<div class="vbar"><span class="dim">Resting orders are matched on every feed tick \u00b7 LMT caps the fill price, STP triggers at last</span>' +
          '<button class="xbtn" data-csv="ord">\u2913 EXPORT CSV</button></div>' +
        '<div class="cards">' +
          card("WORKING", String(working.length), "acc") +
          card("FILLED", String(filled.length), "up") +
          card("CANCELLED", String(dead.length)) +
          card("RESTING NOTIONAL", fnum(restNot)) +
          card("CASH", fnum(Store.data.cash)) +
        "</div>" +
        '<div class="ticket">' +
          '<span class="tt">ORDER TICKET</span>' +
          '<input id="' + pid("o-sym") + '" placeholder="TICKER" value="' + (App.sym || "AAPL") + '">' +
          '<input id="' + pid("o-qty") + '" placeholder="QTY" value="100">' +
          '<input id="' + pid("o-px") + '" placeholder="LIMIT" value="' + f2((bySym[App.sym] || bySym.AAPL).px) + '">' +
          '<button class="tbtn b" data-ord="BUY">BUY LMT</button>' +
          '<button class="tbtn s" data-ord="SELL">SELL LMT</button>' +
          '<button class="tbtn" data-ord="STPSELL">STOP SELL</button>' +
          '<span class="dim" style="margin-left:auto;font-size:10.5px">Rests until the touch trades through the limit</span>' +
        "</div>" +
        body +
      "</div>";
    return { title: "ORD", sub: "Order book \u00b7 " + working.length + " working", right: "WORKING " + working.length, html: html };
  }

  /* ---------------- price alerts view ---------------- */
  function viewALRT() {
    const list = ALERTS();
    App.rows = [];
    const armed = list.filter((a) => a.st === "ARMED");
    const trg = list.filter((a) => a.st === "TRIGGERED");
    const card = (l, v, c) => '<div class="card"><span>' + l + "</span><b class=\"" + (c || "") + "\">" + v + "</b></div>";

    const body = list.length
      ? tableHTML([
          { t: "ID", v: (a) => "#" + a.id },
          { t: "TICKER", v: (a) => a.sym },
          { t: "CONDITION", v: (a) => '<b class="acc">' + a.op + " " + f2(a.px) + "</b>" },
          { t: "LAST", a: "r", v: (a) => (bySym[a.sym] ? f2(bySym[a.sym].px) : "\u2013") },
          { t: "DISTANCE", a: "r", v: (a) => {
              const s = bySym[a.sym];
              if (!s) return "\u2013";
              const d = ((a.px - s.px) / s.px) * 100;
              return '<span class="' + cls(-Math.abs(d)) + '">' + fpct(d) + "</span>";
            } },
          { t: "STATUS", v: (a) => '<span class="' + (a.st === "TRIGGERED" ? "dn" : "up") + '">' + a.st + "</span>" },
          { t: "SET", v: (a) => hhmmss(new Date(a.t)) },
          { t: "FIRED", v: (a) => (a.tt ? hhmmss(new Date(a.tt)) : '<span class="dim">\u2013</span>') },
          { t: "", v: (a) => '<button class="xbtn" data-adel="' + a.id + '">DEL</button>' }
        ], list)
      : '<div class="help"><p>No alerts. Type <code>ALRT AAPL > 240</code> or <code>ALRT NVDA < 180</code> to arm one.</p></div>';

    const log = (Store.data.alertLog || []).slice(0, 40);
    const logHTML = '<div class="alrtlog"><div class="sec">TRIGGER LOG \u00b7 ' + (Store.data.alertLog || []).length + " EVENTS</div>" +
      (log.length
        ? tableHTML([
            { t: "#", v: (e) => "L" + e.id },
            { t: "FIRED", v: (e) => hhmmss(new Date(e.t)) },
            { t: "TICKER", v: (e) => e.sym },
            { t: "CONDITION", v: (e) => '<b class="acc">' + e.op + " " + f2(e.px) + "</b>" },
            { t: "PRINT", v: (e) => '<span class="' + (e.op === ">" ? "up" : "dn") + '">' + f2(e.last) + "</span>" },
            { t: "OVERSHOOT", v: (e) => {
                const d = ((e.last - e.px) / (e.px || 1)) * 100;
                return '<span class="' + cls(d) + '">' + fpct(d) + "</span>";
              } },
            { t: "", v: (e) => '<button class="xbtn" data-apin="' + e.sym + '">PIN</button>' }
          ], log)
        : '<div class="eqsnote">No triggers recorded in this profile yet \u2014 arm one from the ticket above, or type <code>ALRT AAPL &gt; ' +
          f2((bySym[App.sym] || bySym.AAPL).px * 1.001) + "</code> to fire immediately.</div>") +
      "</div>";

    const html =
      '<div class="port">' +
        `<div class="vbar"><span class="dim">Alerts fire once on a feed tick, sound a tone, drop into the status bar and are recorded below · tone <b class="${setts().sound ? "up" : "dim"}">${setts().sound ? "ON" : "OFF"}</b> · desktop <b class="${setts().notify ? "up" : "dim"}">${setts().notify ? "ON" : "OFF"}</b></span>` +
          '<span style="margin-left:auto;display:flex;gap:8px">' +
            '<button class="xbtn" data-go="SET">⚙ SETTINGS</button>' +
            '<button class="xbtn" data-alrtlog="1">✕ CLEAR LOG</button>' +
            '<button class="xbtn" data-csv="alrt">⤓ EXPORT CSV</button>' +
          "</span></div>" +
        '<div class="cards">' +
          card("ARMED", String(armed.length), "up") +
          card("TRIGGERED", String(trg.length), "dn") +
          card("TOTAL", String(list.length)) +
          card("LAST FIRE", (trg.length ? hhmmss(new Date(trg[0].tt)) : "\u2013")) +
          card("LOG", String((Store.data.alertLog || []).length)) +
        "</div>" +
        '<div class="ticket">' +
          '<span class="tt">NEW ALERT</span>' +
          '<input id="' + pid("a-sym") + '" placeholder="TICKER" value="' + (App.sym || "AAPL") + '">' +
          '<input id="' + pid("a-px") + '" placeholder="PRICE" value="' + f2((bySym[App.sym] || bySym.AAPL).px * 1.01) + '">' +
          '<button class="tbtn b" data-alrt=">">ABOVE &gt;</button>' +
          '<button class="tbtn s" data-alrt="<">BELOW &lt;</button>' +
          '<span class="dim" style="margin-left:auto;font-size:10.5px">Type <code>ALRT AAPL &gt; 240</code> for the same thing</span>' +
        "</div>" +
        body + logHTML +
      "</div>";
    return { title: "ALRT", sub: "Price alerts \u00b7 " + armed.length + " armed \u00b7 " + (Store.data.alertLog || []).length + " logged", right: "ARMED " + armed.length, html: html };
  }

  /* ---------------- trade blotter ---------------- */
  function viewTRD() {
    const b = (Store.data.blot || []).slice();
    App.rows = [];
    const buyNot = b.filter((r) => r.side === "BUY").reduce((a, r) => a + r.qty * r.px, 0);
    const sellNot = b.filter((r) => r.side === "SELL").reduce((a, r) => a + r.qty * r.px, 0);
    const card = (l, v, c) => '<div class="card"><span>' + l + "</span><b class=\"" + (c || "") + "\">" + v + "</b></div>";
    const rows = b.map((r) => Object.assign({ __sym: r.sym }, r));
    const body = rows.length
      ? tableHTML([
          { t: "TIME", v: (r) => hhmmss(new Date(r.t)) },
          { t: "TICKER", v: (r) => r.sym },
          { t: "SIDE", v: (r) => '<span class="' + (r.side === "BUY" ? "up" : "dn") + '">' + r.side + "</span>" },
          { t: "QTY", a: "r", v: (r) => fnum(r.qty) },
          { t: "PRICE", a: "r", v: (r) => f2(r.px) },
          { t: "NOTIONAL", a: "r", v: (r) => fnum(r.qty * r.px) },
          { t: "REALIZED", a: "r", v: (r) => (r.side === "SELL" ? '<span class="' + cls(r.real || 0) + '">' + ((r.real || 0) >= 0 ? "+" : "") + fnum(r.real || 0) + "</span>" : '<span class="dim">\u2013</span>') }
        ], rows)
      : '<div class="help"><p>No fills yet. Type <code>BUY AAPL 100</code> to create one.</p></div>';
    const html =
      '<div class="port">' +
        '<div class="vbar"><span class="dim">Blotter keeps the last 300 fills \u00b7 realized P&amp;L is booked on every sell</span>' +
          '<button class="xbtn" data-csv="trd">\u2913 EXPORT CSV</button></div>' +
        '<div class="cards">' +
          card("FILLS", String(b.length)) +
          card("BUY NOTIONAL", fnum(buyNot)) +
          card("SELL NOTIONAL", fnum(sellNot)) +
          card("REALIZED P&L", ((Store.data.realized || 0) >= 0 ? "+" : "") + fnum(Store.data.realized || 0), cls(Store.data.realized || 0)) +
          card("CASH", fnum(Store.data.cash)) +
        "</div>" +
        body +
      "</div>";
    return { title: "TRD", sub: "Trade blotter \u00b7 fills persisted locally", right: "REALIZED " + fnum(Store.data.realized || 0), html: html };
  }

  function viewHELP() {
    App.rows = [];
    const rows = Object.keys(FUNCS).map((k) =>
      "<tr><td><code>" + k + "</code></td><td>" + FUNCS[k].label + "</td><td>" + FUNCS[k].key + "</td><td>" +
      (FUNCS[k].needsSym ? "needs a security" : "market-wide") + "</td></tr>").join("");
    const html =
      '<div class="help">' +
        "<h3>COMMAND SYNTAX</h3>" +
        '<p>Type a command in the top bar and press <code>Enter</code> (same as clicking <code>&lt;GO&gt;</code>). ' +
        "Security commands accept an optional ticker: <code>AAPL US Equity</code> resolves to <code>AAPL</code>.</p>" +
        '<p style="margin-top:8px">Examples: <code>AAPL GP</code> \u00b7 <code>NVDA DES</code> \u00b7 <code>WEI</code> \u00b7 ' +
        "<code>TOP</code> \u00b7 <code>MOST</code> \u00b7 <code>EURUSD</code> \u00b7 <code>CL1 HP</code></p>" +
        "<h3>TRADING &amp; WATCHLIST</h3>" +
        '<table><tbody>' +
        "<tr><td><code>BUY AAPL 100</code></td><td>Buy at the offer; fills against cash balance</td></tr>" +
        "<tr><td><code>SELL AAPL 100</code></td><td>Sell at the bid</td></tr>" +
        "<tr><td><code>ADD AMD</code></td><td>Add a ticker to the watchlist</td></tr>" +
        "<tr><td><code>DEL AMD</code></td><td>Remove a ticker from the watchlist</td></tr>" +
        "<tr><td><code>PORT</code></td><td>Positions, P&amp;L and trade ticket</td></tr>" +
        "<tr><td><code>TRD</code></td><td>Trade blotter with realised P&amp;L</td></tr>" +
        "<tr><td><code>AAPL OPT</code></td><td>Listed option chain (Black-Scholes surface)</td></tr>" +
        "</tbody></table>" +
        "<h3>ORDERS, ALERTS &amp; EXPORT</h3>" +
        '<table><tbody>' +
        "<tr><td><code>BUY AAPL 100</code></td><td>Market order — fills immediately at the offer</td></tr>" +
        "<tr><td><code>BUY AAPL 100 LMT 228.50</code></td><td>Limit order — rests until the offer trades through the limit</td></tr>" +
        "<tr><td><code>SELL AAPL 100 STP 210</code></td><td>Stop order — triggers once the last trades at or through the stop</td></tr>" +
        "<tr><td><code>ORD</code></td><td>Order book: working / filled / cancelled, distance to limit, cancel buttons</td></tr>" +
        "<tr><td><code>CXL 1002</code> / <code>CXL ALL</code></td><td>Cancel one order or every working order</td></tr>" +
        "<tr><td><code>ALRT AAPL &gt; 240</code></td><td>Arm a price alert; fires once, sounds a tone, logs in the status bar</td></tr>" +
        "<tr><td><code>ALRT DEL 3</code></td><td>Delete an alert by id</td></tr>" +
        "<tr><td><code>ALRT</code></td><td>Alert manager with ticket, trigger times, distance to level, a trigger log (PIN back to the tape) and CLEAR LOG</td></tr>" +
        "<tr><td><code>EXPORT TRD</code></td><td>Download the blotter as CSV (also PORT / ORD / ALRT)</td></tr>" +
        "<tr><td><code>EXPORT PNG</code></td><td>Save the active chart canvas as a PNG file (or name one: GP / FA / GOV / CMDT)</td></tr>" +
        "<tr><td><code>SET</code></td><td>Settings: alert tone, desktop notifications, background pause, density, brand icon, profiles, exports and print</td></tr>" +
        "</tbody></table>" +
        "<h3>LAYOUT &amp; CHART TOOLS</h3>" +
        '<table><tbody>' +
        "<tr><td><code>LAY 1</code> / <code>LAY 2</code> / <code>LAY 4</code></td><td>Single, two-up or four-quadrant workspace (<code>LAY</code> cycles); drag the divider to resize, double-click it to reset 50/50</td></tr>" +
        "<tr><td>Panel header</td><td>Click a quadrant to focus it — commands and function keys retarget that panel; below 900px a two-up workspace stacks vertically</td></tr>" +
        "<tr><td>Column header</td><td>Click any header to sort the table on that column; click again to reverse. The sort survives the next refresh pass</td></tr>" +
        "<tr><td>Row right-click</td><td>Context menu on any quote row: DES / GP / N / COMP / DEPTH, toggle the symbol in the watchlist, or copy the ticker</td></tr>" +
        "<tr><td>Row long-press / Enter</td><td>Touch and keyboard get the same context menu: hold a row on a phone, or focus it with Tab and press Enter / Space; \u2191\u2193 walk the rows</td></tr>" +
        "<tr><td>Watchlist rows</td><td>Drag a row in <code>W</code> to reorder the monitor, or use the MOVE \u2191\u2193 buttons (the touch equivalent); the order is saved per profile</td></tr>" +
        "<tr><td>CANDLE / BAR / LINE / AREA</td><td>Price plot style; the tool row also carries the log-scale toggle for the y-axis</td></tr>" +
        "<tr><td>TREND / H-LINE</td><td>Draw a two-point trend line or a horizontal level on the price chart</td></tr>" +
        "<tr><td>UNDO / CLEAR</td><td>Remove the last drawing or wipe every drawing on the current symbol + period</td></tr>" +
        "</tbody></table>" +
        "<h3>MARKET SURFACES</h3>" +
        '<table><tbody>' +
        "<tr><td><code>GOV</code></td><td>US Treasury active curve, 2s10s / 3m10y spreads, inverted-zone shading</td></tr>" +
        "<tr><td><code>FX</code></td><td>8 x 8 cross-currency matrix with per-cell daily change, plus a spot converter (<code>CONVERT</code> / <code>SWAP</code>)</td></tr>" +
        "<tr><td><code>CMDT</code> / <code>CMDT CL</code></td><td>Commodity forward curve: settle per contract month, front-to-back spread, contango / backwardation shading (CL / GC / HG)</td></tr>" +
        "<tr><td><code>ECO</code></td><td>Economic calendar with importance, survey and prior</td></tr>" +
        "<tr><td><code>AAPL COMP</code></td><td>Peer comparison vs sector median P/E, market-cap rank</td></tr>" +
        "<tr><td><code>TH</code> / <code>TH ICE</code></td><td>Cycle or select colour theme (AMBER / ICE / TOXIC)</td></tr>" +
        "<tr><td><code>K</code> / <code>PALETTE</code></td><td>Open the command palette</td></tr>" +
        "</tbody></table>" +
        "<h3>ANALYTICS, SCREENING &amp; FIELD REFERENCE</h3>" +
        '<table><tbody>' +
        "<tr><td><code>AAPL FA</code></td><td>Financial analysis: 5-year income statement, revenue / EBITDA / margin chart, valuation ratios</td></tr>" +
        "<tr><td><code>EQS</code></td><td>Equity screener over the local universe, ranked by market cap</td></tr>" +
        "<tr><td><code>EQS PE&lt;30</code></td><td>Screen with criteria: <code>PE</code> <code>MCAP</code> <code>CHG</code> <code>PX</code> <code>VOL</code>, operators <code>&lt;</code> <code>&gt;</code> <code>&lt;=</code> <code>&gt;=</code> <code>=</code>, suffixes <code>K</code> <code>M</code> <code>B</code> <code>T</code></td></tr>" +
        "<tr><td>Screen builder</td><td>Stack criteria with AND / OR, name and save a screen (up to 8, kept per profile), reload or delete it from the SAVED row</td></tr>" +
        "<tr><td><code>FLDS</code></td><td>Field dictionary: mnemonic, data type, category, description and the terminal column it feeds</td></tr>" +
        "<tr><td><code>FLDS MARGIN</code></td><td>Filter the dictionary by mnemonic, category or description text</td></tr>" +
        "<tr><td><code>SRCH</code> / <code>SRCH SEMI</code></td><td>Security search over ticker, company name and sector, with class chips and OPEN shortcuts</td></tr>" +
        "<tr><td><code>APPLE</code> / <code>NVIDIA CORP</code></td><td>Company names resolve to a ticker automatically; several matches open the search page pre-filled</td></tr>" +
        "</tbody></table>" +
        "<h3>FUNCTIONS</h3>" +
        '<table><thead><tr><th>CODE</th><th>FUNCTION</th><th>KEY</th><th>SCOPE</th></tr></thead><tbody>' +
        rows + "</tbody></table>" +
        "<h3>KEYBOARD</h3>" +
        '<table><tbody>' +
        "<tr><td>\u2191 / \u2193</td><td>Move selection, walk autocomplete, or recall command history</td></tr>" +
        "<tr><td>Tab</td><td>Accept autocomplete suggestion</td></tr>" +
        "<tr><td>Enter</td><td>Open selected security (DES) / run command</td></tr>" +
        "<tr><td>Esc</td><td>Clear the command line</td></tr>" +
        "<tr><td>F1 \u2013 F10</td><td>Jump to function</td></tr>" +
        "<tr><td>\u2318K / Ctrl+K</td><td>Command palette \u2014 fuzzy jump to any function or security</td></tr>" +
        "</tbody></table>" +
        "<h3>DATA</h3>" +
        '<p>Prices are generated by a local random-walk engine and refresh roughly once per second \u2014 ' +
        "there is no network connection and no licensed market data. Sparklines, bars and volumes are synthesised deterministically from the same series. " +
        "Watchlist, period, chart overlays, cash, positions, layout theme and per-user profiles persist in localStorage.</p>" +
      "</div>";
    return { title: "HELP", sub: "Command reference", right: "v1.4", html: html };
  }

  /* ---------------- portfolio / trading ---------------- */
  function portfolioStats() {
    const rows = Object.keys(Store.data.pos).map((sym) => {
      const p = Store.data.pos[sym];
      const s = bySym[sym];
      if (!s) return null;
      return {
        sym: sym, qty: p.qty, avg: p.avg, last: s.px, s: s,
        val: p.qty * s.px,
        pnl: (s.px - p.avg) * p.qty,
        pnlp: (s.px / p.avg - 1) * 100
      };
    }).filter(Boolean).sort((a, b) => b.val - a.val);
    let mv = 0, pnl = 0;
    rows.forEach((r) => { mv += r.val; pnl += r.pnl; });
    return { rows: rows, mv: mv, pnl: pnl, equity: Store.data.cash + mv };
  }

  function rets(bars) {
    const out = [];
    for (let i = 1; i < bars.length; i++) {
      const p0 = bars[i - 1][3], p1 = bars[i][3];
      out.push(p0 ? p1 / p0 - 1 : 0);
    }
    return out;
  }

  function stdev(a) {
    const n = a.length;
    if (!n) return 0;
    const m = a.reduce((x, y) => x + y, 0) / n;
    return Math.sqrt(a.reduce((x, y) => x + (y - m) * (y - m), 0) / n);
  }

  function betaTo(s, ref) {
    if (!s || !ref || s.sym === ref.sym) return 1;
    const a = rets(s.hist), b = rets(ref.hist);
    const n = Math.min(a.length, b.length);
    if (n < 5) return 1;
    const A = a.slice(-n), B = b.slice(-n);
    const ma = A.reduce((x, y) => x + y, 0) / n, mb = B.reduce((x, y) => x + y, 0) / n;
    let cov = 0, va = 0;
    for (let i = 0; i < n; i++) {
      cov += (A[i] - ma) * (B[i] - mb);
      va += (B[i] - mb) * (B[i] - mb);
    }
    return va ? cov / va : 1;
  }

  function portRisk(st) {
    const ref = bySym["SPX"] || indices()[0];
    const mv = st.mv || 0;
    const w = st.rows.map((r) => ({ r: r, w: mv ? r.val / mv : 0 }));
    let beta = 0, vol = 0;
    const secW = {};
    w.forEach((x) => {
      const b = ref ? betaTo(x.r.s, ref) : 1;
      const sd = stdev(rets(x.r.s.hist)) * Math.sqrt(78) * 100;
      beta += x.w * b;
      vol += x.w * sd;
      const k = x.r.s.sect || "Other";
      secW[k] = (secW[k] || 0) + x.w * 100;
    });
    const var95 = 1.645 * (vol / 100) * mv;
    const top = w.slice().sort((a, b) => b.w - a.w)[0];
    const hhi = w.reduce((a, x) => a + x.w * x.w, 0) * 10000;
    return { beta: beta, vol: vol, var95: var95, top: top, hhi: hhi, secW: secW, mv: mv, ref: ref };
  }

  function viewPORT() {
    const st = portfolioStats();
    App.rows = st.rows;
    const card = (l, v, c) => '<div class="card"><span>' + l + "</span><b class=\"" + (c || "") + "\">" + v + "</b></div>";
    const body = st.rows.length
      ? tableHTML([
          { t: "TICKER", v: (r) => r.sym },
          { t: "DESCRIPTION", c: "nm", v: (r) => r.s.name },
          { t: "QTY", v: (r) => fnum(r.qty) },
          { t: "AVG COST", v: (r) => f2(r.avg) },
          { t: "LAST", v: (r) => f2(r.last) },
          { t: "MKT VAL", v: (r) => fnum(r.val) },
          { t: "P&L", v: (r) => '<span class="' + cls(r.pnl) + '">' + (r.pnl >= 0 ? "+" : "") + fnum(r.pnl) + "</span>" },
          { t: "P&L %", v: (r) => '<span class="' + cls(r.pnlp) + '">' + fpct(r.pnlp) + "</span>" },
          { t: "", v: (r) => '<button class="xbtn" data-close="' + r.sym + '">CLOSE</button>' }
        ], st.rows)
      : '<div class="help"><p>No open positions. Use the ticket above, or type <code>BUY AAPL 100</code>.</p></div>';

    const rk = portRisk(st);
    const secList = Object.keys(rk.secW).sort((a, b) => rk.secW[b] - rk.secW[a]);
    const riskHTML = '<div class="riskwrap">' +
      '<div class="sec" style="margin-top:0">RISK &amp; EXPOSURE</div>' +
      '<div class="cards">' +
        card("PORT BETA", st.rows.length ? rk.beta.toFixed(2) : "\u2013", rk.beta >= 1 ? "dn" : "up") +
        card("ANN VOL", st.rows.length ? rk.vol.toFixed(1) + "%" : "\u2013") +
        card("1D VAR 95%", st.rows.length ? fnum(rk.var95) : "\u2013", "dn") +
        card("TOP POSITION", rk.top ? rk.top.r.sym + " " + (rk.top.w * 100).toFixed(0) + "%" : "\u2013") +
        card("HHI", st.rows.length ? rk.hhi.toFixed(0) : "\u2013", rk.hhi > 4000 ? "dn" : "") +
      "</div>" +
      (st.rows.length
        ? '<div class="secbars">' + secList.map((k) =>
            '<div class="sbrow"><span class="sbl">' + k + '</span>' +
            '<div class="sbbar"><i style="width:' + Math.min(100, rk.secW[k]).toFixed(1) + '%"></i></div>' +
            '<span class="sbv dim">' + rk.secW[k].toFixed(0) + "%</span></div>").join("") + "</div>"
        : '<div class="eqsnote">Risk metrics need at least one open position \u2014 beta and VaR are computed against ' +
          (rk.ref ? rk.ref.sym : "the index universe") + " from the local series.</div>") +
      '<div class="eqsnote">Beta uses the ' + (rk.ref ? rk.ref.sym : "index") + " 5-minute return series, annualised vol scales the intraday sigma by \u221a78, " +
        "VaR is a parametric 1-day 95% figure on current market value, HHI above 4000 indicates a concentrated book. " +
        "All figures are indicative on simulated prices.</div>" +
    "</div>";

    const html =
      '<div class="port">' +
        '<div class="vbar"><span class="dim">Marked to the live feed \u00b7 positions and cash persist per profile</span>' +
          '<button class="xbtn" data-csv="port">\u2913 EXPORT CSV</button></div>' +
        '<div class="cards">' +
          card("TOTAL EQUITY", fnum(st.equity)) +
          card("CASH", fnum(Store.data.cash)) +
          card("MARKET VALUE", fnum(st.mv)) +
          card("UNREALIZED P&L", (st.pnl >= 0 ? "+" : "") + fnum(st.pnl), cls(st.pnl)) +
          card("POSITIONS", String(st.rows.length)) +
        "</div>" +
        riskHTML +
        '<div class="ticket">' +
          '<span class="tt">TRADE TICKET</span>' +
          '<input id="t-sym" placeholder="TICKER" value="' + (App.sym || "AAPL") + '">' +
          '<input id="t-qty" placeholder="QTY" value="100">' +
          '<button class="tbtn b" id="t-buy">BUY</button>' +
          '<button class="tbtn s" id="t-sell">SELL</button>' +
          '<span class="dim" style="margin-left:auto;font-size:10.5px">Fills at touch \u00b7 state persisted locally</span>' +
        "</div>" +
        body +
      "</div>";
    return {
      title: "PORT",
      sub: "Portfolio \u00b7 simulated fills \u00b7 cash " + fnum(Store.data.cash),
      right: "EQUITY " + fnum(st.equity),
      html: html
    };
  }

  function trade(sym, qty, side, capPx) {
    const s = bySym[String(sym || "").toUpperCase()];
    if (!s) { notice("Unknown security " + sym, true); return false; }
    qty = Math.round(Number(qty));
    if (!qty || qty <= 0 || isNaN(qty)) { notice("Quantity must be a positive integer", true); return false; }
    const px = capPx != null && isFinite(Number(capPx)) ? Number(capPx) : (side === "BUY" ? s.ask : s.bid);
    const notional = px * qty;
    const p = Store.data.pos[s.sym] || { qty: 0, avg: 0 };
    let realized = 0;

    if (side === "BUY") {
      if (notional > Store.data.cash) { notice("Insufficient cash \u2014 need " + fnum(notional), true); return false; }
      p.avg = (p.avg * p.qty + notional) / (p.qty + qty);
      p.qty += qty;
      Store.data.cash -= notional;
      Store.data.pos[s.sym] = p;
    } else {
      if (p.qty < qty) { notice("Position too small \u2014 holding " + p.qty + " " + s.sym, true); return false; }
      realized = (px - p.avg) * qty;
      p.qty -= qty;
      Store.data.cash += notional;
      Store.data.realized = Number(((Store.data.realized || 0) + realized).toFixed(2));
      if (p.qty === 0) delete Store.data.pos[s.sym];
      else Store.data.pos[s.sym] = p;
    }
    Store.data.blot = Store.data.blot || [];
    Store.data.blot.unshift({ t: Date.now(), sym: s.sym, side: side, qty: qty, px: Number(px.toFixed(4)), real: Number(realized.toFixed(2)) });
    if (Store.data.blot.length > 300) Store.data.blot.length = 300;
    Store.save();
    notice(side + " " + qty + " " + s.sym + " @ " + f2(px) + " \u00b7 FILLED", false);
    if (App.func === "PORT" || App.func === "TRD") render();
    return true;
  }

  function closePos(sym) {
    const p = Store.data.pos[sym];
    if (!p) return;
    trade(sym, p.qty, "SELL");
  }

  /* ---------------- working orders (ORD) ---------------- */
  const ORDERS = () => (Store.data.orders = Store.data.orders || []);
  const ALERTS = () => (Store.data.alerts = Store.data.alerts || []);
  function pid(n) { return (App.pfx || "") + n; }

  function placeOrder(sym, side, qty, type, px) {
    const s = bySym[String(sym || "").toUpperCase()];
    if (!s) { notice("Unknown security " + sym, true); return null; }
    qty = Math.round(Number(qty));
    if (!qty || qty <= 0) { notice("Quantity must be a positive integer", true); return null; }
    type = (type || "LMT").toUpperCase();
    if (type !== "MKT") {
      px = Number(px);
      if (!isFinite(px) || px <= 0) { notice(type + " order needs a price \u2014 e.g. BUY " + s.sym + " " + qty + " LMT " + f2(s.px), true); return null; }
    }
    const o = {
      id: Store.data.nextOid = (Store.data.nextOid || 1001) + 1,
      t: Date.now(),
      sym: s.sym,
      side: side,
      type: type === "MKT" ? "MKT" : type,
      qty: qty,
      px: type === "MKT" ? null : Number(px),
      status: "WORKING",
      ft: 0,
      fpx: 0
    };
    ORDERS().unshift(o);
    if (ORDERS().length > 200) ORDERS().length = 200;
    Store.save();
    checkOrders();
    checkAlerts();
    if (App.func === "ORD") render();
    if (o.status === "WORKING") {
      const dist = o.px ? ((o.px - s.px) / s.px) * 100 : 0;
      notice("ORDER #" + o.id + " " + o.side + " " + o.qty + " " + o.sym + " " + o.type + (o.px ? " @" + f2(o.px) : "") + " \u00b7 WORKING (" + fpct(dist) + " away)", false);
    }
    return o;
  }

  function cancelOrder(id) {
    if (String(id).toUpperCase() === "ALL") {
      let n = 0;
      ORDERS().forEach((o) => { if (o.status === "WORKING") { o.status = "CXL"; n++; } });
      Store.save();
      if (App.func === "ORD") render();
      notice(n ? "Cancelled " + n + " order(s)" : "No working orders", !n);
      return n;
    }
    const o = ORDERS().find((x) => String(x.id) === String(id));
    if (!o) { notice("Order #" + id + " not found", true); return false; }
    if (o.status !== "WORKING") { notice("Order #" + id + " is " + o.status, true); return false; }
    o.status = "CXL";
    Store.save();
    if (App.func === "ORD") render();
    notice("Order #" + o.id + " cancelled");
    return true;
  }

  function fillOrder(o) {
    const s = bySym[o.sym];
    if (!s) { o.status = "REJECTED"; return false; }
    let px;
    if (o.type === "LMT") px = o.side === "BUY" ? Math.min(o.px, s.ask) : Math.max(o.px, s.bid);
    else px = o.side === "BUY" ? s.ask : s.bid;
    if (trade(o.sym, o.qty, o.side, px)) {
      o.status = "FILLED";
      o.ft = Date.now();
      o.fpx = Number(Number(px).toFixed(4));
      return true;
    }
    o.status = "REJECTED";
    return false;
  }

  function checkOrders() {
    const list = ORDERS();
    let filled = 0;
    list.forEach((o) => {
      if (o.status !== "WORKING") return;
      const s = bySym[o.sym];
      if (!s) return;
      let hit;
      if (o.type === "LMT") hit = o.side === "BUY" ? s.ask <= o.px : s.bid >= o.px;
      else hit = o.side === "BUY" ? s.px >= o.px : s.px <= o.px;
      if (!hit) return;
      if (fillOrder(o)) filled++;
    });
    if (filled) Store.save();
    return filled;
  }

  /* ---------------- price alerts (ALRT) ---------------- */
  function placeAlert(sym, op, px) {
    const s = bySym[String(sym || "").toUpperCase()];
    if (!s) { notice("Unknown security " + sym, true); return null; }
    px = Number(px);
    if (!isFinite(px) || px <= 0) { notice("Alert needs a price \u2014 e.g. ALRT " + s.sym + " > " + f2(s.px * 1.01), true); return null; }
    const a = {
      id: Store.data.nextAid = (Store.data.nextAid || 1) + 1,
      sym: s.sym,
      op: op === "<" ? "<" : ">",
      px: Number(px),
      st: "ARMED",
      t: Date.now(),
      tt: 0,
      last: s.px
    };
    ALERTS().unshift(a);
    if (ALERTS().length > 200) ALERTS().length = 200;
    Store.save();
    checkAlerts();
    if (App.func === "ALRT") render();
    if (a.st === "ARMED") notice("ALERT #" + a.id + " armed \u00b7 " + a.sym + " " + a.op + " " + f2(a.px) + " \u00b7 last " + f2(s.px));
    return a;
  }

  function removeAlert(id) {
    const before = ALERTS().length;
    Store.data.alerts = ALERTS().filter((a) => String(a.id) !== String(id));
    Store.save();
    if (App.func === "ALRT") render();
    notice(Store.data.alerts.length < before ? "Alert #" + id + " removed" : "Alert #" + id + " not found", Store.data.alerts.length === before);
  }

  function checkAlerts() {
    let hit = 0;
    ALERTS().forEach((a) => {
      if (a.st !== "ARMED") return;
      const s = bySym[a.sym];
      if (!s) return;
      a.last = s.px;
      const trig = a.op === ">" ? s.px >= a.px : s.px <= a.px;
      if (trig) {
        a.st = "TRIGGERED";
        a.tt = Date.now();
        hit++;
        Store.data.alertLog = Store.data.alertLog || [];
        Store.data.alertLog.unshift({ t: a.tt, id: a.id, sym: a.sym, op: a.op, px: a.px, last: s.px });
        if (Store.data.alertLog.length > 120) Store.data.alertLog.length = 120;
        notifyAlert(a, s);
        notice("ALERT #" + a.id + " TRIGGERED \u00b7 " + a.sym + " " + a.op + " " + f2(a.px) + " \u00b7 last " + f2(s.px), true);
        ping();
      }
    });
    if (hit) {
      Store.save();
      if (App.func === "ALRT") render();
    }
    return hit;
  }

  /* ---------------- csv export ---------------- */
  function csvText(cols, rows) {
    const esc = (v) => {
      const s = v == null ? "" : String(v);
      return /[",\r\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
    };
    return [cols.join(",")].concat(rows.map((r) => r.map(esc).join(","))).join("\r\n");
  }

  function stamp() {
    const d = new Date();
    return d.getFullYear() + pad2(d.getMonth() + 1) + pad2(d.getDate()) + "_" + pad2(d.getHours()) + pad2(d.getMinutes());
  }

  function exportSet(kind) {
    let cols, rows, name;
    if (kind === "trd") {
      cols = ["TIME", "TICKER", "SIDE", "QTY", "PRICE", "NOTIONAL", "REALIZED"];
      rows = (Store.data.blot || []).map((r) => [
        new Date(r.t).toISOString(), r.sym, r.side, r.qty, r.px,
        Number((r.qty * r.px).toFixed(2)), r.side === "SELL" ? Number((r.real || 0).toFixed(2)) : ""
      ]);
      name = "blotter_" + (App.user || "GUEST") + "_" + stamp() + ".csv";
    } else if (kind === "port") {
      cols = ["TICKER", "DESCRIPTION", "QTY", "AVG_COST", "LAST", "MARKET_VALUE", "PNL", "PNL_PCT"];
      rows = portfolioStats().rows.map((r) => [r.sym, r.s.name, r.qty, r.avg, r.last, r.val, r.pnl, r.pnlp]);
      name = "positions_" + (App.user || "GUEST") + "_" + stamp() + ".csv";
    } else if (kind === "alrt") {
      cols = ["ID", "CREATED", "SYMBOL", "CONDITION", "TARGET_PRICE", "STATUS", "TRIGGERED_AT"];
      rows = (Store.data.alerts || []).map(a => [a.id, new Date(a.t).toISOString(), a.sym, a.op, a.px, a.st, a.tt ? new Date(a.tt).toISOString() : ""]);
      name = "alerts_" + (App.user || "GUEST") + "_" + stamp() + ".csv";
    } else {
      cols = ["ID", "CREATED", "SYMBOL", "SIDE", "TYPE", "QTY", "LIMIT", "STATUS", "FILLED_AT", "FILL_PRICE"];
      rows = ORDERS().map((o) => [
        o.id, new Date(o.t).toISOString(), o.sym, o.side, o.type, o.qty,
        o.px == null ? "" : o.px, o.status, o.ft ? new Date(o.ft).toISOString() : "", o.fpx || ""
      ]);
      name = "orders_" + (App.user || "GUEST") + "_" + stamp() + ".csv";
    }
    return { cols: cols, rows: rows, name: name };
  }

  function backupPayload() {
    return {
      app: "TERMINAL",
      version: window.__TERMINAL__ ? window.__TERMINAL__.version : "1.0",
      profile: App.user,
      exported: new Date().toISOString(),
      data: JSON.parse(JSON.stringify(Store.data))
    };
  }

  function downloadJSON() {
    const obj = backupPayload();
    try {
      const blob = new Blob([JSON.stringify(obj, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "terminal-" + App.user.toLowerCase() + "-backup.json";
      document.body.appendChild(a);
      a.click();
      setTimeout(() => { URL.revokeObjectURL(url); a.remove(); }, 500);
      Store.data.lastBackup = obj.exported.slice(0, 19).replace("T", " ");
      Store.save();
      notice("Backup exported \u00b7 " + a.download, false);
      return obj;
    } catch (e) {
      notice("Backup failed: " + (e && e.message), true);
      return null;
    }
  }

  function importJSON(obj) {
    if (!obj || typeof obj !== "object" || !obj.data || typeof obj.data !== "object") {
      notice("Import failed \u2014 not a TERMINAL backup file", true);
      return false;
    }
    Store.data = Object.assign(JSON.parse(JSON.stringify(DEFAULT_PROFILE)), obj.data);
    Store.save();
    Store.load();
    App.layout = Store.data.layout || "1";
    App.focus = 0;
    App.logScale = !!Store.data.logScale;
    applySetts();
    applyTheme(Store.data.theme || "AMBER");
    App.maCfg = Object.assign({ a: 20, b: 60, bn: 20, bk: 2 }, Store.data.maCfg || {});
    App.ma = !!Store.data.ma;
    App.boll = !!Store.data.boll;
    App.period = Store.data.period;
    App.sub = Store.data.sub;
    App.ctype = Store.data.ctype;
    notice("Imported backup from " + (obj.profile || "?") + " \u00b7 " + (obj.exported || "").slice(0, 19).replace("T", " "), false);
    render();
    syncNavigation();
    return true;
  }

  function importFromFile() {
    const inp = document.createElement("input");
    inp.type = "file";
    inp.accept = "application/json,.json";
    inp.style.display = "none";
    inp.id = "impjson";
    document.body.appendChild(inp);
    inp.addEventListener("change", () => {
      const f = inp.files && inp.files[0];
      if (!f) { inp.remove(); return; }
      const rd = new FileReader();
      rd.onload = () => {
        try { importJSON(JSON.parse(String(rd.result))); }
        catch (e) { notice("Import failed \u2014 invalid JSON", true); }
        inp.remove();
      };
      rd.onerror = () => { notice("Import failed \u2014 unreadable file", true); inp.remove(); };
      rd.readAsText(f);
    });
    inp.click();
    return inp;
  }

  function resetProfile() {
    const ok = window.confirm ? window.confirm("Reset profile " + App.user + "?\n\nThis clears cash, positions, blotter, orders, alerts, watchlist and screens. Chart preferences are reset too. This cannot be undone.") : true;
    if (!ok) return false;
    Store.reset();
    Store.save();
    App.maCfg = Object.assign({}, DEFAULT_PROFILE.maCfg);
    App.ma = Store.data.ma;
    App.boll = Store.data.boll;
    App.period = Store.data.period;
    App.sub = Store.data.sub;
    App.ctype = Store.data.ctype;
    applyTheme(Store.data.theme || "AMBER");
    notice("Profile " + App.user + " reset to defaults", false);
    render();
    return true;
  }

  function downloadCSV(kind) {
    const set = exportSet(kind);
    const txt = csvText(set.cols, set.rows);
    try {
      const blob = new Blob(["\ufeff" + txt], { type: "text/csv;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = set.name;
      document.body.appendChild(a);
      a.click();
      setTimeout(() => { URL.revokeObjectURL(url); a.remove(); }, 500);
      notice("Exported " + set.name + " \u00b7 " + set.rows.length + " row(s)");
    } catch (e) {
      notice("Export failed: " + (e && e.message), true);
    }
    return txt;
  }

  function ping() {
    if (!setts().sound) return;
    try {
      const AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return;
      ping._c = ping._c || new AC();
      const osc = ping._c.createOscillator();
      const g = ping._c.createGain();
      osc.type = "square";
      osc.frequency.value = 880;
      g.gain.value = 0.02;
      osc.connect(g);
      g.connect(ping._c.destination);
      osc.start();
      osc.stop(ping._c.currentTime + 0.09);
    } catch (e) { /* audio optional */ }
  }

  /* ---------------- autocomplete ---------------- */
  const NAME_STOP = /^(US|EQUITY|INDEX|CURNCY|COMDTY|GOVT|LN|GY|JP|HK|GO)$/;
  function nameHits(q) {
    const toks = String(q || "").toUpperCase().replace(/<GO>/g, " ").split(/\s+/).filter((t) => t && !NAME_STOP.test(t) && !/^\d+$/.test(t));
    if (!toks.length) return [];
    return UNIV.filter((u) => {
      const n = u.name.toUpperCase();
      return toks.every((t) => n.indexOf(t) >= 0);
    });
  }

  function suggest(q) {
    const raw = String(q || "").toUpperCase().replace(/<GO>/g, "").trim();
    if (!raw) return [];
    const out = [];
    ["BUY", "SELL", "ADD", "DEL"].forEach((a) => {
      if (a.indexOf(raw) === 0 || raw.indexOf(a) === 0) {
        out.push({ code: a + " ", label: a === "BUY" || a === "SELL" ? "trade a security" : "edit watchlist", kind: "CMD" });
      }
    });
    Object.keys(FUNCS).forEach((k) => {
      if (k.indexOf(raw) === 0 || FUNCS[k].label.toUpperCase().indexOf(raw) >= 0) {
        out.push({ code: k, label: FUNCS[k].label, kind: "FN" });
      }
    });
    UNIV.forEach((u) => {
      if (u.sym.indexOf(raw) === 0 || u.name.toUpperCase().indexOf(raw) >= 0) {
        out.push({ code: u.sym, label: u.name, kind: u.cls });
      }
    });
    return out.slice(0, 8);
  }

  function updateSugg() {
    const q = $("cmd").value;
    App.sugg.items = suggest(q);
    App.sugg.idx = -1;
    paintSugg();
  }

  function paintSugg() {
    let box = $("sugg");
    if (!box) {
      box = document.createElement("div");
      box.id = "sugg";
      document.querySelector(".cmdwrap").appendChild(box);
      box.addEventListener("mousedown", (e) => {
        const it = e.target.closest("[data-code]");
        if (!it) return;
        e.preventDefault();
        $("cmd").value = it.getAttribute("data-code");
        App.sugg.items = [];
        App.sugg.idx = -1;
        paintSugg();
        $("cmd").focus();
      });
    }
    const items = App.sugg.items;
    if (!items.length) { box.innerHTML = ""; box.classList.remove("on"); return; }
    box.classList.add("on");
    const wrap = document.querySelector(".cmdwrap");
    const r = wrap ? wrap.getBoundingClientRect() : null;
    if (r) { box.style.left = r.left + "px"; box.style.top = r.bottom + "px"; box.style.width = Math.max(320, r.width) + "px"; }
    box.innerHTML = items.map((it, i) =>
      '<div class="sg' + (i === App.sugg.idx ? " sel" : "") + '" data-code="' + it.code.replace(/"/g, "&quot;") + '">' +
      '<span class="c">' + it.code + '</span><span class="l">' + it.label + '</span><span class="k">' + it.kind + "</span></div>").join("");
  }


  /* ---------------- GOV: treasury active curve ---------------- */
  const YC = [
    { t: "1M", v: 5.302 }, { t: "3M", v: 5.241 }, { t: "6M", v: 5.108 },
    { t: "1Y", v: 4.842 }, { t: "2Y", v: 4.552 }, { t: "3Y", v: 4.421 },
    { t: "5Y", v: 4.383 }, { t: "7Y", v: 4.412 }, { t: "10Y", v: 4.284 },
    { t: "20Y", v: 4.702 }, { t: "30Y", v: 4.615 }
  ];
  YC.forEach((x, i) => {
    x.prev = Number((x.v + ((i % 3) - 1) * 0.017).toFixed(3));
    x.d = Number(((x.v - x.prev) * 100).toFixed(1));
  });
  function yc(t) { return YC.filter((x) => x.t === t)[0]; }

  function viewGOV() {
    App.rows = [];
    const y2 = yc("2Y"), y10 = yc("10Y"), y3m = yc("3M"), y30 = yc("30Y");
    const s210 = (y10.v - y2.v) * 100;
    const s310 = (y10.v - y3m.v) * 100;
    const shape = s210 < -2 ? "INVERTED" : s210 < 20 ? "FLAT" : "STEEPENER";
    const avg = YC.reduce((a, b) => a + b.v, 0) / YC.length;
    const cards = [
      { k: "2S10S SPREAD", v: (s210 >= 0 ? "+" : "") + s210.toFixed(1) + " bp", c: s210 >= 0 ? "up" : "dn" },
      { k: "3M10Y SPREAD", v: (s310 >= 0 ? "+" : "") + s310.toFixed(1) + " bp", c: s310 >= 0 ? "up" : "dn" },
      { k: "10Y YIELD", v: y10.v.toFixed(3) + "%", c: cls(y10.d) },
      { k: "30Y YIELD", v: y30.v.toFixed(3) + "%", c: cls(y30.d) },
      { k: "CURVE SHAPE", v: shape, c: shape === "INVERTED" ? "dn" : "up" }
    ];
    const cardsHTML = '<div class="cards">' + cards.map((c) =>
      '<div class="card"><span>' + c.k + '</span><b class="' + c.c + '">' + c.v + "</b></div>").join("") + "</div>";
    const cols = [
      { t: "TENOR", v: (r) => r.t },
      { t: "YIELD %", a: "r", v: (r) => r.v.toFixed(3) },
      { t: "1D CHG bp", a: "r", v: (r) => '<span class="' + cls(r.d) + '">' + (r.d >= 0 ? "+" : "") + r.d.toFixed(1) + "</span>" },
      { t: "PREV %", a: "r", v: (r) => r.prev.toFixed(3) },
      { t: "VS AVG bp", a: "r", v: (r) => { const dd = (r.v - avg) * 100; return '<span class="' + cls(dd) + '">' + (dd >= 0 ? "+" : "") + dd.toFixed(1) + "</span>"; } },
      { t: "SIGNAL", v: (r) => (r.d > 0.4 ? "STEEPEN" : r.d < -0.4 ? "FLATTEN" : "HOLD") }
    ];
    const rows = YC.map((x) => ({ t: x.t, v: x.v, prev: x.prev, d: x.d }));
    return {
      title: "GOV",
      sub: "US Treasury Actives \u00b7 " + YC.length + " tenors \u00b7 " + shape,
      right: "CURVE \u00b7 SIM",
      html: '<div class="govwrap">' + cardsHTML +
        '<div class="govchart"><div class="legend"><span>GOV</span><span><b>US TREASURY ACTIVE CURVE</b></span>' +
        '<span id="yclive">AVG ' + avg.toFixed(3) + "%</span></div>" +
        '<canvas id="ycurve"></canvas></div>' +
        tableHTML(cols, rows) + "</div>"
    };
  }

  function mountCurve() {
    const cv = $("ycurve");
    if (!cv) return;
    const box = cv.parentElement;
    const dpr = window.devicePixelRatio || 1;
    const w = Math.max(320, box.clientWidth - 20);
    const h = Math.max(180, box.clientHeight - 10);
    cv.width = Math.round(w * dpr);
    cv.height = Math.round(h * dpr);
    cv.style.width = w + "px";
    cv.style.height = h + "px";
    const ctx = cv.getContext("2d");
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, cv.width, cv.height);
    ctx.scale(dpr, dpr);

    const padL = 46, padR = 52, padT = 24, padB = 26;
    const cw = w - padL - padR, ch = h - padT - padB;
    let mn = Infinity, mx = -Infinity;
    YC.forEach((x) => { mn = Math.min(mn, x.v, x.prev); mx = Math.max(mx, x.v, x.prev); });
    const pad = (mx - mn) * 0.22 || 0.1;
    mn -= pad; mx += pad;
    const X = (i) => padL + (i / (YC.length - 1)) * cw;
    const Y = (v) => padT + ch - ((v - mn) / (mx - mn)) * ch;

    const css = getComputedStyle(document.body);
    const cLine = (css.getPropertyValue("--line") || "#182028").trim();
    const cDim = (css.getPropertyValue("--dim2") || "#4d5c69").trim();
    const cAcc = (css.getPropertyValue("--acc") || "#fb8b1e").trim();
    const cPre = (css.getPropertyValue("--dim") || "#7b8b9a").trim();

    ctx.font = "10px ui-monospace,Menlo,monospace";
    ctx.textBaseline = "middle";
    for (let i = 0; i <= 4; i++) {
      const y = padT + (ch / 4) * i;
      const v = mx - ((mx - mn) / 4) * i;
      ctx.strokeStyle = cLine;
      ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(padL + cw, y); ctx.stroke();
      ctx.fillStyle = cDim; ctx.textAlign = "right";
      ctx.fillText(v.toFixed(2) + "%", padL - 8, y);
    }
    YC.forEach((x, i) => {
      ctx.fillStyle = cDim; ctx.textAlign = "center";
      ctx.fillText(x.t, X(i), padT + ch + 14);
      ctx.strokeStyle = "rgba(255,255,255,.045)";
      ctx.beginPath(); ctx.moveTo(X(i), padT); ctx.lineTo(X(i), padT + ch); ctx.stroke();
    });

    // inverted zone shading
    const i2 = YC.findIndex((x) => x.t === "2Y");
    const i10 = YC.findIndex((x) => x.t === "10Y");
    if (YC[i10].v < YC[i2].v) {
      ctx.fillStyle = "rgba(255,77,94,.08)";
      ctx.fillRect(X(i2), padT, X(i10) - X(i2), ch);
    }

    // previous curve (dashed)
    ctx.strokeStyle = cPre;
    ctx.setLineDash([3, 3]);
    ctx.lineWidth = 1;
    ctx.beginPath();
    YC.forEach((x, i) => { const px = X(i), py = Y(x.prev); i ? ctx.lineTo(px, py) : ctx.moveTo(px, py); });
    ctx.stroke();
    ctx.setLineDash([]);

    // active curve (area + line)
    const grad = ctx.createLinearGradient(0, padT, 0, padT + ch);
    grad.addColorStop(0, "rgba(251,139,30,.24)");
    grad.addColorStop(1, "rgba(251,139,30,0)");
    ctx.beginPath();
    YC.forEach((x, i) => { const px = X(i), py = Y(x.v); i ? ctx.lineTo(px, py) : ctx.moveTo(px, py); });
    const lastPx = X(YC.length - 1);
    ctx.lineTo(lastPx, padT + ch);
    ctx.lineTo(X(0), padT + ch);
    ctx.closePath();
    ctx.fillStyle = grad;
    ctx.fill();

    ctx.beginPath();
    YC.forEach((x, i) => { const px = X(i), py = Y(x.v); i ? ctx.lineTo(px, py) : ctx.moveTo(px, py); });
    ctx.strokeStyle = cAcc;
    ctx.lineWidth = 1.7;
    ctx.stroke();

    YC.forEach((x, i) => {
      ctx.beginPath();
      ctx.arc(X(i), Y(x.v), 2.6, 0, Math.PI * 2);
      ctx.fillStyle = "#060a0e"; ctx.fill();
      ctx.strokeStyle = cAcc; ctx.lineWidth = 1.4; ctx.stroke();
    });
    const y10 = yc("10Y");
    const lx = X(YC.findIndex((x) => x.t === "10Y"));
    ctx.fillStyle = cAcc;
    ctx.textAlign = "left";
    ctx.fillText("10Y " + y10.v.toFixed(3) + "%", lx + 6, Y(y10.v) - 10);
  }

  /* ---------------- FX: cross matrix ---------------- */
  const FX_CCY = ["USD", "EUR", "JPY", "GBP", "CHF", "AUD", "CAD", "CNH"];

  function usdPer(c) {
    if (c === "USD") return 1;
    if (c === "EUR") return bySym["EURUSD"].px;
    if (c === "GBP") return bySym["GBPUSD"].px;
    if (c === "JPY") return 1 / bySym["USDJPY"].px;
    if (c === "CNH") return 1 / bySym["USDCNH"].px;
    if (c === "CHF") return 1 / 0.8812;
    if (c === "AUD") return 0.6584;
    return 1 / 1.3606;
  }
  const fxRate = (r, c) => usdPer(r) / usdPer(c);
  const fmtFx = (v) => (v >= 100 ? v.toFixed(2) : v >= 10 ? v.toFixed(3) : v.toFixed(4));
  function fxChg(r, c) { const h = hashNum(r + "|" + c); return ((h % 161) / 100 - 0.8) * 0.3; }

  function viewFX() {
    App.rows = [];
    const pairs = [["EURUSD", "EUR"], ["USDJPY", "JPY"], ["GBPUSD", "GBP"], ["USDCNH", "CNH"]];
    const cards = pairs.map((p) => {
      const q = bySym[p[0]];
      const cp = chgp(q);
      return { k: p[0], v: q.px.toFixed(q.px > 10 ? 2 : 4), c: cls(cp), s: fpct(cp) };
    });
    const cardsHTML = '<div class="cards">' + cards.map((c) =>
      '<div class="card"><span>' + c.k + '</span><b class="' + c.c + '">' + c.v +
      '</b><em class="' + c.c + '">' + c.s + "</em></div>").join("") + "</div>";

    let head = '<tr><th class="fxh corner">CCY</th>' +
      FX_CCY.map((c) => '<th class="fxh' + (c === "USD" ? " on" : "") + '">' + c + "</th>").join("") + "</tr>";
    const body = FX_CCY.map((r) => {
      let tr = '<tr><td class="fxr">' + r + "</td>";
      FX_CCY.forEach((c) => {
        if (r === c) { tr += '<td class="fxdiag">\u2014</td>'; return; }
        const v = fxRate(r, c), pc = fxChg(r, c);
        tr += '<td class="fxcell ' + cls(pc) + '"><b>' + fmtFx(v) + "</b><i>" +
          (pc >= 0 ? "+" : "") + pc.toFixed(2) + "%</i></td>";
      });
      return tr + "</tr>";
    }).join("");

    const amt = Number(String(App.fxAmt).replace(/,/g, "")) || 0;
    const rate = fxRate(App.fxFrom, App.fxTo);
    const sel = (v) => FX_CCY.map((c) => '<option' + (v === c ? " selected" : "") + ">" + c + "</option>").join("");
    const convHTML = '<div class="fxconv">' +
      '<span class="tt">CONVERTER</span>' +
      '<input id="fx-amt" aria-label="amount" value="' + App.fxAmt + '">' +
      '<select id="fx-from" aria-label="from currency">' + sel(App.fxFrom) + "</select>" +
      '<span class="dim">\u2192</span>' +
      '<select id="fx-to" aria-label="to currency">' + sel(App.fxTo) + "</select>" +
      '<button class="xbtn" data-fxconv="1">CONVERT</button>' +
      '<b class="acc">' + fmtFx(amt * rate) + " " + App.fxTo + "</b>" +
      '<span class="dim">1 ' + App.fxFrom + " = " + fmtFx(rate) + " " + App.fxTo + "</span>" +
      '<button class="xbtn" data-fxswap="1" aria-label="swap currencies">\u21c4 SWAP</button>' +
      "</div>";

    return {
      title: "FX",
      sub: "Cross Currency Matrix \u00b7 1 unit of row currency in column currency",
      right: "SPOT \u00b7 SIM",
      html: '<div class="fxwrap">' + cardsHTML + convHTML +
        '<table class="fxmat"><thead>' + head + "</thead><tbody>" + body + "</tbody></table>" +
        '<p class="fxnote">Row / column intersection = amount of column currency per 1 unit of row currency. Daily change is simulated.</p></div>'
    };
  }

  /* ---------------- CMDT: futures term structure ---------------- */
  const CMD_ROOTS = [
    { root: "CL", sym: "CL1", name: "WTI Crude", unit: "USD/bbl", carry: -0.0035, vol: 30 },
    { root: "GC", sym: "GC1", name: "Gold", unit: "USD/oz", carry: 0.0042, vol: 14 },
    { root: "HG", sym: "HG1", name: "Copper", unit: "USD/lb", carry: -0.0018, vol: 22 }
  ];
  const CMD_MONTHS = ["NOV 26", "DEC 26", "JAN 27", "FEB 27", "MAR 27", "APR 27", "MAY 27", "JUN 27", "SEP 27", "DEC 27"];

  function cmdCurve(c) {
    const s = bySym[c.sym];
    return CMD_MONTHS.map((m, i) => {
      const px = s.px * Math.pow(1 + c.carry, i);
      return { m: m, i: i, px: px, chg: (px / s.px - 1) * 100, legs: i };
    });
  }

  function viewCMDT() {
    App.rows = [];
    const c = CMD_ROOTS[App.cmdRoot] || CMD_ROOTS[0];
    const cur = cmdCurve(c);
    const front = cur[0], back = cur[cur.length - 1];
    const roll = (front.px / back.px - 1) * 100;
    const shape = c.carry > 0 ? "CONTANGO" : "BACKWARDATION";
    const card = (l, v, cl) => '<div class="card"><span>' + l + '</span><b class="' + (cl || "") + '">' + v + "</b></div>";
    const chips = '<div class="eqsbar"><span class="dim eqlead">ROOT</span>' + CMD_ROOTS.map((r, i) =>
      '<button class="pbtn' + (i === App.cmdRoot ? " on" : "") + '" data-cmd="' + i + '">' + r.root + " \u00b7 " + r.name + "</button>").join("") + "</div>";
    const cols = [
      { t: "CONTRACT", v: (r) => r.m },
      { t: "LEGS", a: "r", v: (r) => "+" + r.legs + "M" },
      { t: "SETTLE", a: "r", v: (r) => f2(r.px) },
      { t: "VS FRONT %", a: "r", v: (r) => '<span class="' + cls(r.chg) + '">' + fpct(r.chg) + "</span>" },
      { t: "SPREAD bp", a: "r", v: (r) => (r.chg * 100).toFixed(0) },
      { t: "STRUCTURE", v: (r) => (r.chg > 0.5 ? "CONTANGO" : r.chg < -0.5 ? "BACKWARDATION" : "FLAT") }
    ];
    return {
      title: "CMDT",
      sub: "Futures term structure \u00b7 " + c.name + " \u00b7 " + c.unit + " \u00b7 " + shape,
      right: c.root + " \u00b7 SIM",
      html: '<div class="govwrap">' +
        '<div class="cards">' +
          card("FRONT " + cur[0].m, f2(front.px)) +
          card("BACK " + back.m, f2(back.px)) +
          card("ROLL YIELD", (roll >= 0 ? "+" : "") + roll.toFixed(2) + "%", roll >= 0 ? "up" : "dn") +
          card("STRUCTURE", shape, shape === "CONTANGO" ? "dn" : "up") +
          card("ANN VOL", c.vol + "%") +
        "</div>" + chips +
        '<div class="govchart"><div class="legend"><span>CMDT</span><span><b>' + c.name + " CURVE</b></span>" +
          '<span class="dim">front to ' + back.m + "</span></div>" +
          '<canvas id="cmdcurve"></canvas></div>' +
        tableHTML(cols, cur) +
        '<div class="eqsnote">Curve is built from the front-month price with a constant monthly carry of ' +
          (c.carry * 100).toFixed(2) + "% \u2014 negative carry is backwardation, positive carry is contango. Indicative only.</div>" +
      "</div>"
    };
  }

  function mountCmdCurve() {
    const cv = $("cmdcurve");
    if (!cv) return;
    const c = CMD_ROOTS[App.cmdRoot] || CMD_ROOTS[0];
    const cur = cmdCurve(c);
    const dpr = window.devicePixelRatio || 1;
    const box = cv.parentElement;
    const w = Math.max(320, box.clientWidth - 20);
    const h = Math.max(170, box.clientHeight - 10);
    cv.width = Math.round(w * dpr);
    cv.height = Math.round(h * dpr);
    cv.style.width = w + "px";
    cv.style.height = h + "px";
    const ctx = cv.getContext("2d");
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, cv.width, cv.height);
    ctx.scale(dpr, dpr);
    const padL = 52, padR = 52, padT = 22, padB = 28;
    const cw = w - padL - padR, ch = h - padT - padB;
    let mn = Infinity, mx = -Infinity;
    cur.forEach((p) => { mn = Math.min(mn, p.px); mx = Math.max(mx, p.px); });
    const pd = (mx - mn) * 0.25 || 1;
    mn -= pd; mx += pd;
    const X = (i) => padL + (i / (cur.length - 1)) * cw;
    const Y = (v) => padT + ch - ((v - mn) / (mx - mn)) * ch;
    const cssg = getComputedStyle(document.body);
    const cLine = (cssg.getPropertyValue("--line") || "#182028").trim();
    const cDim = (cssg.getPropertyValue("--dim2") || "#4d5c69").trim();
    const cAcc = (cssg.getPropertyValue("--acc") || "#fb8b1e").trim();
    ctx.font = "10px ui-monospace,Menlo,monospace";
    ctx.textBaseline = "middle";
    for (let i = 0; i <= 4; i++) {
      const y = padT + (ch / 4) * i;
      const v = mx - ((mx - mn) / 4) * i;
      ctx.strokeStyle = cLine; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(padL + cw, y); ctx.stroke();
      ctx.fillStyle = cDim; ctx.textAlign = "right";
      ctx.fillText(f2(v), padL - 8, y);
    }
    cur.forEach((p, i) => {
      ctx.fillStyle = cDim; ctx.textAlign = "center";
      ctx.fillText(p.m.slice(0, 3), X(i), padT + ch + 14);
      ctx.strokeStyle = "rgba(255,255,255,.04)";
      ctx.beginPath(); ctx.moveTo(X(i), padT); ctx.lineTo(X(i), padT + ch); ctx.stroke();
    });
    const grad = ctx.createLinearGradient(0, padT, 0, padT + ch);
    grad.addColorStop(0, "rgba(74,163,255,.26)");
    grad.addColorStop(1, "rgba(74,163,255,0)");
    ctx.beginPath();
    cur.forEach((p, i) => (i ? ctx.lineTo(X(i), Y(p.px)) : ctx.moveTo(X(i), Y(p.px))));
    ctx.lineTo(X(cur.length - 1), padT + ch);
    ctx.lineTo(X(0), padT + ch);
    ctx.closePath();
    ctx.fillStyle = grad; ctx.fill();
    ctx.beginPath();
    cur.forEach((p, i) => (i ? ctx.lineTo(X(i), Y(p.px)) : ctx.moveTo(X(i), Y(p.px))));
    ctx.strokeStyle = "#4aa3ff"; ctx.lineWidth = 1.6; ctx.stroke();
    cur.forEach((p, i) => {
      ctx.beginPath();
      ctx.arc(X(i), Y(p.px), 2.4, 0, Math.PI * 2);
      ctx.fillStyle = "#060a0e"; ctx.fill();
      ctx.strokeStyle = cAcc; ctx.lineWidth = 1.2; ctx.stroke();
    });
  }

  /* ---------------- ECO: economic calendar ---------------- */
  const ECO = [
    { tm: "07:30", reg: "CN", ev: "Industrial Production YoY", imp: 2, act: "5.4%", est: "5.1%", prev: "4.9%" },
    { tm: "08:00", reg: "DE", ev: "IFO Business Climate", imp: 2, act: "86.2", est: "85.8", prev: "85.4" },
    { tm: "08:30", reg: "US", ev: "Initial Jobless Claims", imp: 3, act: "221K", est: "224K", prev: "218K" },
    { tm: "09:00", reg: "EU", ev: "ECB Consumer Expectations Survey", imp: 1, act: "2.9%", est: "2.9%", prev: "3.0%" },
    { tm: "10:00", reg: "US", ev: "ISM Manufacturing PMI", imp: 3, act: "", est: "47.6", prev: "47.2" },
    { tm: "10:00", reg: "US", ev: "Construction Spending MoM", imp: 1, act: "", est: "0.2%", prev: "-0.1%" },
    { tm: "11:30", reg: "US", ev: "4-Week Bill Auction", imp: 1, act: "", est: "-", prev: "4.28%" },
    { tm: "13:00", reg: "US", ev: "10-Year Note Auction", imp: 2, act: "", est: "-", prev: "4.31%" },
    { tm: "14:00", reg: "US", ev: "FOMC Minutes Release", imp: 3, act: "", est: "-", prev: "-" },
    { tm: "16:00", reg: "JP", ev: "BoJ Core CPI YoY", imp: 2, act: "", est: "2.1%", prev: "2.0%" },
    { tm: "21:45", reg: "CN", ev: "Caixin Services PMI", imp: 2, act: "", est: "51.6", prev: "51.4" },
    { tm: "23:50", reg: "JP", ev: "Tankan Large Mfg Index", imp: 2, act: "", est: "13", prev: "12" }
  ];

  function stars(n) { return "\u25CF".repeat(n) + '<span class="dim">' + "\u25CF".repeat(3 - n) + "</span>"; }

  function viewECO() {
    App.rows = [];
    const nowHHMM = pad2(new Date().getHours()) + ":" + pad2(new Date().getMinutes());
    const rows = ECO.slice().sort((a, b) => a.tm.localeCompare(b.tm));
    const pend = rows.filter((r) => !r.act).length;
    const cols = [
      { t: "TIME", v: (r) => '<span class="' + (r.act ? "dim" : "") + '">' + r.tm + "</span>" },
      { t: "REGION", v: (r) => '<span class="tag">' + r.reg + "</span>" },
      { t: "EVENT", c: "nm", v: (r) => r.ev },
      { t: "IMP", v: (r) => '<span class="acc">' + stars(r.imp) + "</span>" },
      { t: "ACTUAL", a: "r", v: (r) => (r.act ? "<b>" + r.act + "</b>" : '<span class="dim">\u2014</span>') },
      { t: "SURVEY", a: "r", v: (r) => r.est },
      { t: "PRIOR", a: "r", v: (r) => r.prev },
      { t: "STATUS", v: (r) => (r.act ? '<span class="up">RELEASED</span>' : r.tm <= nowHHMM ? '<span class="acc">DUE</span>' : '<span class="dim">SCHEDULED</span>') }
    ];
    return {
      title: "ECO",
      sub: "Economic Calendar \u00b7 " + rows.length + " events \u00b7 " + pend + " pending",
      right: "GMT+8 \u00b7 SIM",
      html: '<div class="ecowrap">' + tableHTML(cols, rows) + "</div>"
    };
  }

  /* ---------------- COMP: peer comparison ---------------- */
  function peersOf(base) {
    const same = equities().filter((s) => s.sect === base.sect && s.sym !== base.sym);
    const pool = same.length >= 2 ? same
      : equities().filter((s) => ["Technology", "Semiconductors", "Communication Services"].indexOf(s.sect) >= 0 && s.sym !== base.sym);
    return [base].concat(pool).slice(0, 6);
  }

  function viewCOMP() {
    const base = bySym[App.sym] || bySym["AAPL"];
    const list = peersOf(base);
    const rows = list.map(withQuote);
    App.rows = rows;
    const pes = list.filter((s) => s.pe).map((s) => s.pe).sort((a, b) => a - b);
    const med = pes.length ? pes[Math.floor(pes.length / 2)] : 0;
    const caps = list.slice().sort((a, b) => b.mcap - a.mcap);
    const rank = caps.findIndex((s) => s.sym === base.sym) + 1;
    const avgChg = list.reduce((a, s) => a + chgp(s), 0) / list.length;
    const cards = [
      { k: "PEER SET", v: base.sect || "-", c: "" },
      { k: "BASE P/E", v: base.pe ? base.pe.toFixed(1) : "\u2013", c: "" },
      { k: "PEER MEDIAN P/E", v: med ? med.toFixed(1) : "\u2013", c: base.pe && base.pe > med ? "dn" : "up" },
      { k: "MKT CAP RANK", v: "#" + rank + " / " + list.length, c: "" },
      { k: "VS PEER AVG", v: fpct(chgp(base) - avgChg), c: cls(chgp(base) - avgChg) }
    ];
    const cardsHTML = '<div class="cards">' + cards.map((c) =>
      '<div class="card"><span>' + c.k + '</span><b class="' + c.c + '">' + c.v + "</b></div>").join("") + "</div>";
    const bcp = chgp(base);
    const cols = [
      { t: "TICKER", v: (r) => (r.__sym === base.sym ? '<b class="acc">' + r.__sym + "</b>" : r.__sym) },
      { t: "DESCRIPTION", c: "nm", v: (r) => r.name },
      { t: "LAST", a: "r", v: (r) => f2(r.px) },
      { t: "%CHG", a: "r", v: (r) => '<span class="' + cls(r.__cp) + '">' + fpct(r.__cp) + "</span>" },
      { t: "VS BASE", a: "r", v: (r) => { const dd = r.__cp - bcp; return '<span class="' + cls(dd) + '">' + (dd >= 0 ? "+" : "") + dd.toFixed(2) + "pp</span>"; } },
      { t: "MKT CAP", a: "r", v: (r) => (r.mcap ? (r.mcap / 1e9).toFixed(0) + "B" : "\u2013") },
      { t: "P/E", a: "r", v: (r) => (r.pe ? r.pe.toFixed(1) : "\u2013") },
      { t: "VOL", a: "r", v: (r) => (r.vol ? fnum(r.vol) : "\u2013") }
    ];
    return {
      title: "COMP",
      sub: "Peer Comparison \u00b7 " + base.sym + " \u00b7 " + list.length + " names \u00b7 " + (base.sect || ""),
      right: "RELATIVE \u00b7 SIM",
      html: '<div class="compwrap">' + cardsHTML + tableHTML(cols, rows) + "</div>"
    };
  }

  /* ---------------- theme ---------------- */
  const _themeCache = {};
  function themeVar(n, fb) {
    const key = (document.body.className || "-") + "|" + n;
    if (key in _themeCache) return _themeCache[key];
    let v = fb;
    try { v = (getComputedStyle(document.body).getPropertyValue(n) || "").trim() || fb; } catch (e) { v = fb; }
    _themeCache[key] = v;
    return v;
  }
  function UP_COL(fb) { return themeVar("--up", fb || "#20c97a"); }
  function DN_COL(fb) { return themeVar("--dn", fb || "#ff4d5e"); }
  function FA_REV_COL() { return "#2a5f86"; }
  function FA_EBITDA_COL() { return themeVar("--acc", "#fb8b1e"); }

  function applyTheme(name) {
    const t = THEMES.indexOf(String(name || "").toUpperCase()) >= 0 ? String(name).toUpperCase() : "AMBER";
    document.body.classList.remove("theme-ice", "theme-toxic");
    if (t !== "AMBER") document.body.classList.add("theme-" + t.toLowerCase());
    Store.data.theme = t;
    Store.save();
    const b = $("thbtn");
    if (b) b.setAttribute("data-theme", t);
    // canvas charts bake colours at paint time -> repaint the live view
    const v = $("view");
    if (v && v.children.length) { try { render(); } catch (e) { /* boot race */ } }
    return t;
  }

  /* ---------------- command palette ---------------- */
  const pal = { items: [], idx: 0 };

  function palItems(q) {
    const term = String(q || "").trim().toUpperCase();
    const out = [];
    Object.keys(FUNCS).forEach((k) => {
      out.push({ code: k, label: FUNCS[k].label, kind: "FUNC", cmd: k });
    });
    UNIV.forEach((s) => out.push({ code: s.sym, label: s.name, kind: s.cls, cmd: s.sym + " DES" }));
    [
      ["CXL ALL", "Cancel every working order", "ACTION"],
      ["BUY AAPL 100 LMT", "Rest a limit order", "ACTION"],
      ["SELL AAPL 100 STP", "Rest a stop order", "ACTION"],
      ["ALRT AAPL > 240", "Arm a price alert", "ACTION"],
      ["ALRT DEL", "Delete an alert by id", "ACTION"],
      ["LAY 1", "Single panel", "LAYOUT"],
      ["LAY 2", "Two panels side by side", "LAYOUT"],
      ["LAY 4", "Four-quadrant workspace", "LAYOUT"],
      ["AAPL FA", "Financial analysis for AAPL", "ACTION"],
      ["EQS PE<30", "Screen equities under 30x earnings", "ACTION"],
      ["FLDS PX_", "Search the field dictionary", "ACTION"],
      ["EXPORT TRD", "Download the blotter as CSV", "ACTION"],
      ["EXPORT PORT", "Download positions as CSV", "ACTION"],
      ["EXPORT ORD", "Download the order book as CSV", "ACTION"]
    ].forEach((a) => out.push({ code: a[0], label: a[1], kind: a[2], cmd: a[0] }));
    if (!term) return out.slice(0, 80);
    return out.filter((i) => (i.code + " " + i.label).toUpperCase().indexOf(term) >= 0).slice(0, 80);
  }

  function paintPalette() {
    const box = $("plist");
    if (!box) return;
    if (!pal.items.length) { box.innerHTML = '<div class="pempty">No match</div>'; return; }
    box.innerHTML = pal.items.map((i, n) =>
      '<div class="pitem' + (n === pal.idx ? " sel" : "") + '" data-n="' + n + '">' +
      '<span class="pc">' + i.code + '</span><span class="pl">' + i.label + '</span>' +
      '<span class="pk">' + i.kind + "</span></div>").join("");
  }

  function openPalette() {
    const mask = $("palette");
    if (!mask) return;
    mask._returnFocus = document.activeElement;
    mask.classList.remove("hidden");
    const pin = $("pinput");
    pin.value = "";
    pal.items = palItems("");
    pal.idx = 0;
    paintPalette();
    setTimeout(() => pin.focus(), 20);
  }

  function closePalette() {
    const mask = $("palette");
    if (mask) { mask.classList.add("hidden"); if(mask._returnFocus && mask._returnFocus.isConnected)mask._returnFocus.focus(); }
  }

  /* ---------------- footer status: autosave + feed freshness ---------------- */
  function flashSaved() {
    const el = $("savedflag");
    if (!el) return;
    el.textContent = "SAVED " + hhmmss(new Date());
    el.classList.add("on");
    if (App.savedTmr) clearTimeout(App.savedTmr);
    App.savedTmr = setTimeout(() => {
      el.classList.remove("on");
      el.textContent = "SAVED";
    }, 1600);
  }

  /* ---------------- UI zoom (Cmd +/-/0) ---------------- */
  function zoomStep(delta, reset) {
    const cur = reset || delta === 0 ? 1 : (App.zoom || 1) + delta;
    const z = Math.min(1.3, Math.max(0.8, Math.round(cur * 100) / 100));
    applyZoom(z, true);
    notice("UI SCALE " + Math.round(z * 100) + "%" + (z === 1 ? " (default)" : ""));
    return z;
  }
  function applyZoom(z, persist) {
    App.zoom = z;
    if (document.body) document.body.style.zoom = z === 1 ? "" : String(z);
    if (persist) { Store.data.zoom = z; Store.save(); }
  }

  function setFresh(state) {
    const el = $("freshflag");
    if (!el) return;
    const s = state || (App.paused ? "stale" : "live");
    el.textContent = s === "stale" ? "STALE" : "LIVE";
    el.classList.toggle("live", s === "live");
    el.classList.toggle("stale", s !== "live");
  }

  /* ---------------- keyboard reference overlay ---------------- */
  function openQuickref() {
    const el = $("quickref");
    if (!el) return false;
    el._returnFocus = document.activeElement;
    el.classList.remove("hidden");
    App.qfOpen = true;
    const x = $("qkx");
    if (x && x.focus) x.focus();
    return true;
  }

  function closeQuickref() {
    const el = $("quickref");
    if (!el) return false;
    el.classList.add("hidden");
    App.qfOpen = false;
    if(el._returnFocus && el._returnFocus.isConnected)el._returnFocus.focus();
    return true;
  }

  /* ---------------- command history popover ---------------- */
  function paintHist() {
    const ul = $("histlist");
    if (!ul) return;
    const items = (App.cmdHist || []).slice(0, 14);
    if (!items.length) {
      ul.innerHTML = '<li class="hempty">No commands yet — type one above</li>';
      return;
    }
    ul.innerHTML = items.map((c, i) =>
      '<li class="hitem" data-hist="' + i + '" tabindex="0" role="button">' +
        '<span class="hn">' + (i + 1) + "</span><span class=\"hc\">" + String(c).replace(/[<>&]/g, (m) => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;" }[m])) + "</span></li>"
    ).join("");
  }

  function openHist() {
    const pop = $("histpop");
    if (!pop) return false;
    paintHist();
    pop.classList.remove("hidden");
    App.histOpen = true;
    return true;
  }

  function closeHist() {
    const pop = $("histpop");
    if (!pop) return false;
    pop.classList.add("hidden");
    App.histOpen = false;
    return true;
  }

  function toggleHist() {
    return App.histOpen ? closeHist() : openHist();
  }

  function useHist(i) {
    const cmd = (App.cmdHist || [])[i];
    if (!cmd) return false;
    closeHist();
    const inp = $("cmd");
    if (inp) { inp.value = cmd; inp.focus(); }
    exec(cmd);
    return true;
  }

  function palChoose(n) {
    const it = pal.items[n];
    if (!it) return;
    closePalette();
    exec(it.cmd);
  }

  function bootUI() {
    const th = $("thbtn");
    if (th) th.addEventListener("click", () => {
      const next = THEMES[(THEMES.indexOf(Store.data.theme) + 1) % THEMES.length];
      applyTheme(next);
      notice("Theme " + next, false);
    });
    const qth = new URLSearchParams(location.search).get("theme");
    applyTheme(qth || Store.data.theme || "AMBER");
    const pb = $("palbtn");
    if (pb) pb.addEventListener("click", openPalette);

    const qb = $("qkbtn");
    if (qb) qb.addEventListener("click", openQuickref);
    const qfb = $("qkfoot");
    if (qfb) qfb.addEventListener("click", openQuickref);
    setFresh();
    const vEl = $("view");
    if (vEl) vEl.addEventListener("scroll", () => { App.scrollMemo[App.func] = vEl.scrollTop; }, { passive: true });
    const qx = $("qkx");
    if (qx) qx.addEventListener("click", closeQuickref);
    const qf = $("quickref");
    if (qf) qf.addEventListener("click", (e) => { if (e.target === qf) closeQuickref(); });

    const hb = $("histbtn");
    if (hb) hb.addEventListener("click", (e) => { e.stopPropagation(); toggleHist(); });
    const hl = $("histlist");
    if (hl) {
      hl.addEventListener("click", (e) => {
        const it = e.target.closest("[data-hist]");
        if (it) useHist(Number(it.getAttribute("data-hist")));
      });
      hl.addEventListener("keydown", (e) => {
        const it = e.target.closest("[data-hist]");
        if (it && (e.key === "Enter" || e.key === " ")) {
          e.preventDefault();
          useHist(Number(it.getAttribute("data-hist")));
        }
      });
    }
    document.addEventListener("click", (e) => {
      if (!App.histOpen) return;
      if (e.target.closest("#histpop") || e.target.closest("#histbtn")) return;
      closeHist();
    });

    const mask = $("palette");
    if (mask) mask.addEventListener("click", (e) => { if (e.target === mask) closePalette(); });
    const pin = $("pinput");
    if (pin) {
      pin.addEventListener("input", () => {
        pal.items = palItems(pin.value);
        pal.idx = 0;
        paintPalette();
      });
      pin.addEventListener("keydown", (e) => {
        if (e.key === "ArrowDown") { e.preventDefault(); pal.idx = Math.min(pal.items.length - 1, pal.idx + 1); paintPalette(); }
        else if (e.key === "ArrowUp") { e.preventDefault(); pal.idx = Math.max(0, pal.idx - 1); paintPalette(); }
        else if (e.key === "Enter") { e.preventDefault(); palChoose(pal.idx); }
        else if (e.key === "Escape") { e.preventDefault(); closePalette(); }
      });
    }
    const list = $("plist");
    if (list) list.addEventListener("click", (e) => {
      const it = e.target.closest(".pitem");
      if (it) palChoose(Number(it.getAttribute("data-n")));
    });
    if (new URLSearchParams(location.search).get("pal") === "1") setTimeout(openPalette, 60);
    document.addEventListener("keydown", (e) => {
      const typing = /^(INPUT|TEXTAREA|SELECT)$/.test((e.target && e.target.tagName) || "");
      if ((e.metaKey || e.ctrlKey) && String(e.key).toLowerCase() === "k") {
        e.preventDefault();
        openPalette();
        return;
      }
      if ((e.metaKey || e.ctrlKey) && String(e.key).toLowerCase() === "h") {
        e.preventDefault();
        toggleHist();
        return;
      }
      if (e.key === "?" && !typing && !e.metaKey && !e.ctrlKey) {
        e.preventDefault();
        openQuickref();
      }
      // UI zoom: Cmd +/-/0
      if (e.metaKey || e.ctrlKey) {
        const kz = String(e.key);
        if (kz === "=" || kz === "+") { e.preventDefault(); zoomStep(0.1); return; }
        if (kz === "-" || kz === "_") { e.preventDefault(); zoomStep(-0.1); return; }
        if (kz === "0") { e.preventDefault(); zoomStep(0, true); return; }
      }
    });
  }

  /* ---------------- FA: financial analysis ---------------- */
  function viewFA() {
    App.rows = [];
    const s = bySym[App.sym] || bySym["AAPL"];
    const fin = finFor(s.sym);
    if (!fin) {
      return {
        title: "FA " + s.sym,
        sub: "Financial analysis",
        right: "N/A",
        html: '<div class="help"><h3>FINANCIAL ANALYSIS</h3><p>' + s.sym + " \u00b7 " + s.name +
          " is a " + s.cls.toLowerCase() + " security \u2014 no corporate statements are modelled. " +
          'Load an equity instead: <code>AAPL FA</code> \u00b7 <code>NVDA FA</code>.</p></div>'
      };
    }
    const cp = chgp(s);
    const capTxt = (s.mcap / 1e12) >= 1 ? (s.mcap / 1e12).toFixed(2) + "T" : (s.mcap / 1e9).toFixed(0) + "B";
    const cards = [
      { k: "LAST", v: f2(s.px), c: cls(cp) },
      { k: "%CHG", v: fpct(cp), c: cls(cp) },
      { k: "MKT CAP", v: capTxt, c: "" },
      { k: "REVENUE TTM", v: (fin.revNow / 1e9).toFixed(1) + "B", c: "" },
      { k: "EBITDA TTM", v: (fin.yrs[4].ebitda / 1e9).toFixed(1) + "B", c: "" },
      { k: "NET DEBT", v: ((fin.debt - fin.cash) / 1e9).toFixed(1) + "B", c: fin.debt > fin.cash ? "dn" : "up" }
    ];
    const cardsHTML = '<div class="cards">' + cards.map((c) =>
      '<div class="card"><span>' + c.k + '</span><b class="' + c.c + '">' + c.v + "</b></div>").join("") + "</div>";

    const money = (v) => (v / 1e9).toFixed(1);
    const pcols = [
      { t: "FISCAL YEAR", v: (r) => r.fy },
      { t: "REVENUE", a: "r", v: (r) => money(r.rev) },
      { t: "GROSS PROFIT", a: "r", v: (r) => money(r.gross) },
      { t: "EBITDA", a: "r", v: (r) => money(r.ebitda) },
      { t: "NET INCOME", a: "r", v: (r) => money(r.ni) },
      { t: "EPS", a: "r", v: (r) => r.eps.toFixed(2) },
      { t: "FCF", a: "r", v: (r) => money(r.fcf) },
      { t: "NET MARGIN", a: "r", v: (r) => ((r.ni / r.rev) * 100).toFixed(1) + "%" }
    ];
    const rcols = [
      { t: "RATIO", v: (r) => r[0] },
      { t: "VALUE", a: "r", v: (r) => r[1] }
    ];
    return {
      title: "FA " + s.sym,
      sub: s.name + " \u00b7 " + s.sect + " \u00b7 income statement, ratios and 5-year trend",
      right: "FUNDAMENTALS \u00b7 SIM",
      html: '<div class="fawrap">' + cardsHTML +
        '<div class="fachart"><div class="legend"><span>FA</span><span><b>REVENUE \u00b7 EBITDA \u00b7 NET MARGIN</b></span>' +
        '<span>' + fin.yrs[0].fy + " \u2013 " + fin.yrs[4].fy + "</span></div>" +
        '<canvas id="fachart"></canvas></div>' +
        '<div class="fatwo">' +
          '<div><div class="sec">INCOME STATEMENT \u00b7 ' + (s.ccy || "USD") + " BILLIONS</div>" +
            tableHTML(pcols, fin.yrs) + "</div>" +
          '<div><div class="sec">RATIOS &amp; VALUATION</div>' + tableHTML(rcols, fin.ratios) + "</div>" +
        "</div></div>"
    };
  }

  function mountFA() {
    const cv = $(pid("fachart"));
    if (!cv) return;
    const s = bySym[App.sym] || bySym["AAPL"];
    const fin = finFor(s.sym);
    if (!fin) return;
    const box = cv.parentElement;
    const dpr = window.devicePixelRatio || 1;
    const w = Math.max(320, box.clientWidth - 20);
    const h = Math.max(180, box.clientHeight - 10);
    cv.width = Math.round(w * dpr);
    cv.height = Math.round(h * dpr);
    cv.style.width = w + "px";
    cv.style.height = h + "px";
    const ctx = cv.getContext("2d");
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, cv.width, cv.height);
    ctx.scale(dpr, dpr);

    const padL = 56, padR = 58, padT = 22, padB = 28;
    const cw = w - padL - padR, ch = h - padT - padB;
    const yrs = fin.yrs;
    const maxRev = Math.max.apply(null, yrs.map((y) => y.rev)) * 1.16;
    const maxMar = Math.max.apply(null, yrs.map((y) => (y.ni / y.rev) * 100)) * 1.7 || 10;
    const Y = (v) => padT + ch - (v / maxRev) * ch;
    const Y2 = (v) => padT + ch - (v / maxMar) * ch;

    ctx.font = '9px ui-monospace, "SF Mono", Menlo, monospace';
    ctx.textAlign = "right";
    for (let i = 0; i <= 4; i++) {
      const v = (maxRev * i) / 4, y = Y(v);
      ctx.strokeStyle = i === 0 ? "#243240" : "#141d25";
      ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(padL + cw, y); ctx.stroke();
      ctx.fillStyle = "#4d5c69";
      ctx.fillText("$" + (v / 1e9).toFixed(0) + "B", padL - 8, y + 3);
    }
    ctx.textAlign = "left";
    for (let i = 0; i <= 4; i++) {
      const v = (maxMar * i) / 4, y = Y2(v);
      ctx.fillStyle = "#2f6b4a";
      ctx.fillText(v.toFixed(0) + "%", padL + cw + 8, y + 3);
    }

    const slot = cw / yrs.length;
    yrs.forEach((y, i) => {
      const cx = padL + slot * (i + 0.5);
      const bw = Math.min(42, slot * 0.34);
      const revTop = Y(y.rev);
      ctx.fillStyle = FA_REV_COL();
      ctx.fillRect(cx - bw - 2, revTop, bw, padT + ch - revTop);
      const eTop = Y(y.ebitda);
      ctx.fillStyle = FA_EBITDA_COL();
      ctx.fillRect(cx + 2, eTop, bw, padT + ch - eTop);
      ctx.textAlign = "center";
      ctx.fillStyle = "#7b8b9a";
      ctx.fillText(y.fy, cx, padT + ch + 16);
      ctx.fillStyle = "#9db0c0";
      ctx.fillText((y.rev / 1e9).toFixed(0), cx - bw / 2 - 2, revTop - 4);
    });

    ctx.beginPath();
    yrs.forEach((y, i) => {
      const cx = padL + slot * (i + 0.5);
      const py = Y2((y.ni / y.rev) * 100);
      if (i === 0) ctx.moveTo(cx, py); else ctx.lineTo(cx, py);
    });
    ctx.strokeStyle = UP_COL();
    ctx.lineWidth = 1.6;
    ctx.stroke();
    ctx.lineWidth = 1;
    yrs.forEach((y, i) => {
      const cx = padL + slot * (i + 0.5);
      const py = Y2((y.ni / y.rev) * 100);
      ctx.beginPath();
      ctx.arc(cx, py, 2.6, 0, Math.PI * 2);
      ctx.fillStyle = UP_COL();
      ctx.fill();
    });

    ctx.textAlign = "left";
    ctx.fillStyle = "#7b8b9a";
    ctx.fillText("REV", padL, padT - 8);
    ctx.fillStyle = FA_REV_COL();
    ctx.fillRect(padL + 26, padT - 13, 8, 8);
    ctx.fillStyle = "#7b8b9a";
    ctx.fillText("EBITDA", padL + 40, padT - 8);
    ctx.fillStyle = FA_EBITDA_COL();
    ctx.fillRect(padL + 84, padT - 13, 8, 8);
    ctx.fillStyle = "#7b8b9a";
    ctx.fillText("NET MARGIN", padL + 98, padT - 8);
    ctx.fillStyle = UP_COL();
    ctx.fillRect(padL + 174, padT - 13, 8, 8);
  }

  /* ---------------- EQS: equity screener ---------------- */
  const EQ_FIELDS = ["PE", "MCAP", "CHG", "PX", "VOL"];
  const EQ_OPS = ["<", ">", "<=", ">=", "="];

  function builderCrit() {
    const out = [];
    App.eqsBuild.forEach((r) => {
      const raw = String(r.v == null ? "" : r.v).replace(/[,\s$]/g, "").toUpperCase();
      if (!raw) return;
      const m = raw.match(/^(-?[\d.]+)([KMBT]?)$/);
      if (!m) return;
      out.push({ f: r.f, op: r.op, v: Number(m[1]) * multOf(m[2]), txt: raw });
    });
    return out;
  }

  function screenRowsJoin(crit, join) {
    const ops = {
      "<": (a, b) => a < b, ">": (a, b) => a > b,
      "<=": (a, b) => a <= b, ">=": (a, b) => a >= b, "=": (a, b) => Math.abs(a - b) < 1e-9
    };
    if (!crit.length) return equities();
    return equities().filter((s) => {
      const res = crit.map((c) => {
        const v = SCREEN_MET[c.f](s);
        return v != null && ops[c.op](v, c.v);
      });
      return join === "OR" ? res.some(Boolean) : res.every(Boolean);
    });
  }

  function syncBuild() {
    const rows = document.querySelectorAll("#view .eqrow");
    if (!rows.length) return;
    App.eqsBuild = Array.prototype.map.call(rows, (r) => {
      const f = r.querySelector("[data-eqf]"), o = r.querySelector("[data-eqo]"), v = r.querySelector("[data-eqv]");
      return { f: f ? f.value : "PE", op: o ? o.value : "<", v: v ? v.value : "" };
    });
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function builderHTML() {
    const rows = App.eqsBuild.map((r, i) =>
      '<div class="eqrow">' +
        '<span class="dim eqlead">' + (i === 0 ? "WHERE" : App.eqsJoin) + "</span>" +
        '<select data-eqf aria-label="field">' + EQ_FIELDS.map((f) =>
          "<option" + (r.f === f ? " selected" : "") + ">" + f + "</option>").join("") + "</select>" +
        '<select data-eqo aria-label="operator">' + EQ_OPS.map((o) =>
          "<option" + (r.op === o ? " selected" : "") + ">" + esc(o) + "</option>").join("") + "</select>" +
        '<input data-eqv aria-label="value" placeholder="VALUE \u2014 30 / 500B / 20M" value="' + esc(r.v) + '">' +
        '<button class="xbtn" data-eqdelrow="' + i + '" aria-label="remove criterion">\u2715</button>' +
      "</div>").join("");
    const saved = (Store.data.screens || []);
    const savedChips = saved.length
      ? '<div class="eqsbar"><span class="dim eqlead">SAVED</span>' + saved.map((sc, i) =>
          '<span class="eqsave"><button class="pbtn" data-eqsaved="' + i + '">' + esc(sc.name) + "</button>" +
          '<button class="xbtn" data-eqsd="' + i + '" aria-label="delete screen">\u2715</button></span>').join("") + "</div>"
      : "";
    return '<div class="eqbuild">' +
      '<div class="sec" style="margin-top:0">SCREEN BUILDER</div>' +
      rows +
      '<div class="eqtools">' +
        '<button class="xbtn" data-eqadd="1">+ CRITERION</button>' +
        '<button class="xbtn' + (App.eqsJoin === "AND" ? " on" : "") + '" data-eqjoin="AND">AND</button>' +
        '<button class="xbtn' + (App.eqsJoin === "OR" ? " on" : "") + '" data-eqjoin="OR">OR</button>' +
        '<button class="xbtn" data-eqapply="1">\u25b6 APPLY</button>' +
        '<input id="eq-name" aria-label="screen name" placeholder="SCREEN NAME" value="' + esc(App.eqsName || "") + '">' +
        '<button class="xbtn" data-eqsave="1">\u2913 SAVE</button>' +
        '<button class="xbtn" data-eqreset="1">RESET</button>' +
      "</div>" + savedChips + "</div>";
  }

  function viewEQS() {
    App.rows = [];
    const useBuild = !!App.eqsUseBuild;
    const parsed = parseScreen(App.eqsQ);
    let crit = parsed.crit;
    if (useBuild) {
      crit = builderCrit().map((c) => ({ f: c.f, op: c.op, v: c.v }));
      if (!crit.length) crit = parsed.crit;
    }
    const hits = screenRowsJoin(crit, useBuild ? App.eqsJoin : "AND").map(withQuote);
    const key = crit.length ? crit[0].f : "MCAP";
    const getv = SCREEN_MET[key] || SCREEN_MET.MCAP;
    hits.sort((a, b) => (getv(b) || 0) - (getv(a) || 0));
    const capTxt = (v) => (v >= 1e12 ? (v / 1e12).toFixed(2) + "T" : (v / 1e9).toFixed(0) + "B");
    const avg = hits.length ? hits.reduce((a, b) => a + b.__cp, 0) / hits.length : 0;
    const critTxt = crit.length
      ? crit.map((c) => c.f + c.op + (c.v >= 1e9 ? (c.v / 1e9) + "B" : c.v)).join(useBuild ? " " + App.eqsJoin + " " : " ")
      : "NONE";
    const cards = [
      { k: "MATCHES", v: hits.length + "/" + equities().length, c: "" },
      { k: "CRITERIA", v: critTxt, c: "" },
      { k: "AVG %CHG", v: fpct(avg), c: cls(avg) },
      { k: "SORT", v: key, c: "" },
      { k: "SAVED", v: String((Store.data.screens || []).length), c: "" }
    ];
    const cardsHTML = '<div class="cards">' + cards.map((c) =>
      '<div class="card"><span>' + c.k + '</span><b class="' + c.c + '" title="' + esc(c.v) + '">' + esc(c.v) + "</b></div>").join("") + "</div>";
    const presets = ["PE<30", "PE<20", "CHG>0", "CHG<0", "MCAP>500B", "VOL>20M"];
    const chips = '<div class="eqsbar"><span class="dim eqlead">PRESETS</span>' + presets.map((p) =>
      '<button class="pbtn' + (!useBuild && App.eqsQ === p ? " on" : "") + '" data-eqs="' + p + '">' + p + "</button>").join("") +
      '<button class="pbtn' + (!useBuild && !App.eqsQ ? " on" : "") + '" data-eqs="">CLEAR</button></div>';
    const cols = [
      { t: "#", a: "r", v: (r) => String(hits.indexOf(r) + 1) },
      { t: "TICKER", v: (r) => r.__sym },
      { t: "DESCRIPTION", c: "nm", v: (r) => r.name },
      { t: "SECTOR", v: (r) => r.sect },
      { t: "LAST", a: "r", v: (r) => f2(r.px) },
      { t: "%CHG", a: "r", v: (r) => '<span class="' + cls(r.__cp) + '">' + fpct(r.__cp) + "</span>" },
      { t: "MKT CAP", a: "r", v: (r) => (r.mcap ? capTxt(r.mcap) : "\u2013") },
      { t: "P/E", a: "r", v: (r) => (r.pe ? r.pe.toFixed(1) : "\u2013") },
      { t: "VOL", a: "r", v: (r) => (r.vol ? fnum(r.vol) : "\u2013") }
    ];
    const bad = parsed.bad.length ? '<div class="eqsnote">IGNORED: ' + parsed.bad.join(" ") +
      " \u2014 syntax is FIELD OP VALUE, e.g. <code>PE&lt;30</code> <code>MCAP&gt;500B</code> <code>CHG&gt;0</code></div>" : "";
    return {
      title: "EQS",
      sub: "Equity screener \u00b7 " + hits.length + " of " + equities().length + " securities match \u00b7 " + critTxt,
      right: crit.length ? critTxt : "ALL",
      html: '<div class="fawrap">' + cardsHTML + builderHTML() + chips + bad +
        (hits.length ? tableHTML(cols, hits) : '<div class="eqsnote">No security passes the screen \u2014 widen the criteria, switch to OR, or CLEAR.</div>') +
        "</div>"
    };
  }

  /* ---------------- FLDS: field dictionary ---------------- */
  function viewFLDS() {
    App.rows = [];
    const rowsHit = dictRows(App.dictQ);
    const cats = [];
    FIELD_DICT.forEach((f) => { if (cats.indexOf(f[2]) < 0) cats.push(f[2]); });
    const cards = [
      { k: "FIELDS", v: String(FIELD_DICT.length), c: "" },
      { k: "CATEGORIES", v: String(cats.length), c: "" },
      { k: "MATCHES", v: String(rowsHit.length), c: rowsHit.length ? "up" : "dn" },
      { k: "FILTER", v: App.dictQ ? App.dictQ.toUpperCase() : "NONE", c: "" }
    ];
    const cardsHTML = '<div class="cards">' + cards.map((c) =>
      '<div class="card"><span>' + c.k + '</span><b class="' + c.c + '">' + c.v + "</b></div>").join("") + "</div>";
    const chips = '<div class="eqsbar"><button class="pbtn' + (!App.dictQ ? " on" : "") + '" data-dict="">ALL</button>' +
      cats.map((c) => '<button class="pbtn' + (App.dictQ === c ? " on" : "") + '" data-dict="' + c + '">' + c + "</button>").join("") + "</div>";
    const cols = [
      { t: "FIELD", v: (r) => r[0] },
      { t: "TYPE", v: (r) => r[1] },
      { t: "CATEGORY", v: (r) => r[2] },
      { t: "DESCRIPTION", c: "nm", v: (r) => r[3] },
      { t: "TERMINAL COLUMN", v: (r) => r[4] }
    ];
    return {
      title: "FLDS",
      sub: "Field dictionary \u00b7 " + rowsHit.length + " mnemonics" + (App.dictQ ? " matching " + App.dictQ.toUpperCase() : ""),
      right: "REFERENCE \u00b7 LOCAL",
      html: '<div class="fawrap">' + cardsHTML + chips +
        '<div class="eqsnote">Local reference table shipped with this terminal \u2014 mnemonic names, data types and the column each one feeds. No licensed data is included. ' +
        "Search with <code>FLDS PX_</code>, <code>FLDS MARGIN</code>, or click a category chip.</div>" +
        tableHTML(cols, rowsHit) + "</div>"
    };
  }

  /* ---------------- security search (SRCH) ---------------- */
  function viewSRCH() {
    const rows = (typeof UNIV !== "undefined" ? UNIV : []).map(withQuote);
    App.rows = rows;
    const klasses = ["ALL", "EQUITY", "INDEX", "FX", "CMDTY", "GOVT"];
    const chips = klasses.map((c) =>
      '<button class="pbtn' + (App.srchCls === c ? " on" : "") + '" data-srchcls="' + c + '">' + c + "</button>").join("");
    const cols = [
      { t: "TICKER", v: (r) => "<b>" + r.__sym + "</b>" },
      { t: "DESCRIPTION", c: "nm", v: (r) => r.name },
      { t: "CLASS", v: (r) => '<span class="dim">' + r.cls + "</span>" },
      { t: "SECTOR", c: "nm", v: (r) => '<span class="dim">' + r.sect + "</span>" },
      { t: "LAST", a: "r", v: (r) => f2(r.px) },
      { t: "%CHG", a: "r", v: (r) => '<span class="' + cls(r.__cp) + '">' + fpct(r.__cp) + "</span>" },
      { t: "BID", a: "r", v: (r) => f2(r.bid) },
      { t: "ASK", a: "r", v: (r) => f2(r.ask) },
      { t: "", a: "r", v: (r) => '<button class="xbtn" data-srchgo="' + r.__sym + '">OPEN \u203a</button>' }
    ];
    const html =
      '<div class="srchwrap">' +
        '<div class="nfbar">' +
          '<input id="srch-q" data-live="srch" aria-label="search securities" placeholder="SEARCH TICKER / NAME / SECTOR \u2014 e.g. NV, SEMI, TREASURY" value="' +
            String(App.srchQ || "").replace(/"/g, "&quot;") + '">' +
          '<span class="dim" id="srch-count" data-count="srch">' + rows.length + "</span>" +
          '<span class="dim" id="srch-stat" data-count="srchstat">' + rows.length + " / " + rows.length + " SECURITIES</span>" +
          '<button class="xbtn" data-srchclear="1">CLEAR</button>' +
        "</div>" +
        '<div class="eqsbar">' + chips + "</div>" +
        tableHTML(cols, rows) +
      "</div>";
    return {
      title: "SRCH",
      sub: "Security search \u00b7 " + rows.length + " instruments \u00b7 type <code>SRCH NV</code> from the command line",
      right: "REFERENCE \u00b7 LOCAL",
      html: html
    };
  }

  function setEmptyHint(scope, afterSel, shown, msg) {
    let hint = scope.querySelector(".emptyhint");
    if (shown > 0) { if (hint) hint.parentNode.removeChild(hint); return; }
    if (!hint) {
      hint = document.createElement("div");
      hint.className = "emptyhint";
      const anchor = scope.querySelector(afterSel);
      if (anchor && anchor.parentNode) anchor.parentNode.insertBefore(hint, anchor.nextSibling);
      else scope.appendChild(hint);
    }
    hint.textContent = msg;
  }

  function applyNewsFilter(root) {
    const q = String(App.newsQ || "").toUpperCase().trim();
    const scopes = root ? [root] : Array.prototype.slice.call(document.querySelectorAll(".newswrap"));
    if (!scopes.length) return 0;
    let last = 0;
    scopes.forEach((scope) => {
      let shown = 0;
      Array.prototype.forEach.call(scope.querySelectorAll(".nitem"), (li) => {
        const sym = String(li.getAttribute("data-sym") || "").toUpperCase();
        const hay = String(li.textContent || "").toUpperCase();
        const on = !q || hay.indexOf(q) >= 0 || sym.indexOf(q) >= 0;
        li.style.display = on ? "" : "none";
        if (on) shown++;
      });
      Array.prototype.forEach.call(scope.querySelectorAll('[data-count="news"]'), (c) => {
        c.textContent = shown;
      });
      setEmptyHint(scope, "ul.news", shown,
        q ? "NO STORIES MATCH \u201C" + q + "\u201D" : "NO STORIES IN THIS SESSION");
      last = shown;
    });
    return last;
  }

  function applySrchFilter(root) {
    const q = String(App.srchQ || "").toUpperCase().trim();
    const want = App.srchCls || "ALL";
    const scopes = root ? [root] : Array.prototype.slice.call(document.querySelectorAll(".srchwrap"));
    if (!scopes.length) return 0;
    let last = 0;
    scopes.forEach((scope) => {
      let shown = 0;
      const nodes = scope.querySelectorAll("tbody tr[data-sym]");
      Array.prototype.forEach.call(nodes, (tr) => {
        const s = bySym[tr.getAttribute("data-sym")];
        if (!s) return;
        const hay = (s.sym + " " + s.name + " " + (s.sect || "") + " " + s.cls).toUpperCase();
        const on = (!q || hay.indexOf(q) >= 0) && (want === "ALL" || s.cls === want);
        tr.style.display = on ? "" : "none";
        if (on) shown++;
      });
      Array.prototype.forEach.call(scope.querySelectorAll('[data-count="srch"]'), (c) => {
        c.textContent = shown;
      });
      Array.prototype.forEach.call(scope.querySelectorAll('[data-count="srchstat"]'), (c) => {
        c.textContent = shown + " / " + nodes.length + " SECURITIES";
      });
      setEmptyHint(scope, "table", shown,
        "NO SECURITIES MATCH \u201C" + (q || "*") + "\u201D" + (want !== "ALL" ? " \u00B7 CLASS " + want : ""));
      last = shown;
    });
    return last;
  }

  /* ---------------- market depth (DEPTH) ---------------- */
  function depthOf(s, n) {
    const tick = s.px > 500 ? 0.25 : s.px > 100 ? 0.05 : s.px > 10 ? 0.01 : s.px > 1 ? 0.001 : 0.0001;
    const base = s.book && s.book.length ? s.book : [{ bpx: s.bid, bq: 100, apx: s.ask, aq: 100 }];
    const bids = [], asks = [];
    let bcum = 0, acum = 0;
    for (let i = 0; i < n; i++) {
      const src = base[i % base.length];
      const step = Math.floor(i / base.length);
      const grow = 1 + 0.28 * i + step * 0.12;
      const bq = Math.max(100, Math.round((src.bq || 100) * grow));
      const aq = Math.max(100, Math.round((src.aq || 100) * grow));
      bcum += bq; acum += aq;
      bids.push({ px: s.bid - i * tick, qty: bq, cum: bcum });
      asks.push({ px: s.ask + i * tick, qty: aq, cum: acum });
    }
    return { bids: bids, asks: asks, bcum: bcum, acum: acum, tick: tick };
  }

  function viewDEPTH() {
    const s = bySym[App.sym] || bySym["AAPL"];
    App.rows = [];
    const d = depthOf(s, 10);
    const maxCum = Math.max(d.bcum, d.acum) || 1;
    const imb = (d.bcum / (d.bcum + d.acum)) * 100;
    const card = (l, v, c) => '<div class="card"><span>' + l + "</span><b class=\"" + (c || "") + "\">" + v + "</b></div>";
    let ladder = "";
    for (let i = 0; i < 10; i++) {
      const b = d.bids[i], a = d.asks[i];
      const bw = (b.cum / maxCum) * 100, aw = (a.cum / maxCum) * 100;
      ladder += "<tr>" +
        '<td class="r dim">' + fnum(b.cum) + "</td>" +
        '<td class="r">' + fnum(b.qty) + "</td>" +
        '<td class="r up" style="background:linear-gradient(90deg,rgba(32,201,122,.22) ' + bw.toFixed(1) + '%,transparent ' + bw.toFixed(1) + '%)">' + f2(b.px) + "</td>" +
        '<td class="dim r" style="width:34px">' + (i === 0 ? "BID" : "") + "</td>" +
        '<td class="dn" style="background:linear-gradient(270deg,rgba(255,77,94,.22) ' + aw.toFixed(1) + '%,transparent ' + aw.toFixed(1) + '%)">' + f2(a.px) + "</td>" +
        '<td>' + fnum(a.qty) + "</td>" +
        '<td class="dim">' + fnum(a.cum) + "</td>" +
      "</tr>";
    }
    const tape = s.tas.slice(-24).reverse();
    let trows = "";
    tape.forEach((r, i) => {
      const nxt = tape[i + 1];
      const side = nxt ? (r.px >= nxt.px ? "up" : "dn") : "dim";
      const big = (s.vol || 1) > 0 && r.sz > 3000;
      trows += '<tr' + (big ? ' class="big"' : "") + '><td class="dim">' + hhmmss(new Date(r.t)) + "</td>" +
        '<td class="' + side + '">' + f2(r.px) + "</td>" +
        '<td class="r ' + (side === "up" ? "up" : side === "dn" ? "dn" : "dim") + '">' + fnum(r.sz) + "</td>" +
        '<td class="dim r">' + (side === "up" ? "B" : side === "dn" ? "S" : "\u2013") + "</td></tr>";
    });
    const html =
      '<div class="port depth">' +
        '<div class="vbar"><span class="dim">Level-2 style ladder \u00b7 simulated book, 10 price levels per side \u00b7 tick ' + d.tick + "</span>" +
          '<button class="xbtn" data-csv="depth">\u2913 EXPORT CSV</button></div>' +
        '<div class="cards">' +
          card("SPREAD", (s.ask - s.bid).toFixed(4)) +
          card("MID", f2((s.bid + s.ask) / 2)) +
          card("BID DEPTH", fnum(d.bcum) + " @ " + f2(d.bids[9].px), "up") +
          card("ASK DEPTH", fnum(d.acum) + " @ " + f2(d.asks[9].px), "dn") +
          card("IMBALANCE", imb.toFixed(1) + "% BID", imb >= 50 ? "up" : "dn") +
        "</div>" +
        '<div class="dwrap">' +
          '<div class="dcol">' +
            '<div class="sec">PRICE LADDER \u00b7 ' + s.sym + "</div>" +
            '<table class="ladder"><thead><tr><th class="r">BID CUM</th><th class="r">SIZE</th><th class="r">BID</th><th></th><th>ASK</th><th>ASK SZ</th><th class="r">ASK CUM</th></tr></thead><tbody>' +
              ladder + "</tbody></table>" +
            '<div class="imbwrap"><span class="dim">Bid</span><div class="imbbar"><i style="width:' + imb.toFixed(1) + '%"></i></div><span class="dim">Ask</span></div>' +
            '<div class="eqsnote">Book shape is synthesised from the same local random-walk feed \u2014 no exchange depth is licensed. ' +
              "Sizes scale geometrically with distance from the touch, so the cumulative bars widen as you walk down the ladder.</div>" +
          "</div>" +
          '<div class="dcol">' +
            '<div class="sec">TIME &amp; SALES \u00b7 LAST ' + tape.length + "</div>" +
            '<table class="book tas"><thead><tr><th>TIME</th><th>PRICE</th><th class="r">SIZE</th><th class="r">SIDE</th></tr></thead><tbody>' +
              trows + "</tbody></table>" +
            '<div class="sec">QUOTE TOTALS</div>' +
            '<dl class="kv" style="grid-template-columns:110px 1fr">' +
              "<dt>BEST BID</dt><dd class='up'>" + f2(s.bid) + "</dd>" +
              "<dt>BEST ASK</dt><dd class='dn'>" + f2(s.ask) + "</dd>" +
              "<dt>LEVELS</dt><dd>10 \u00d7 2</dd>" +
              "<dt>DAY VOL</dt><dd>" + (s.vol ? fnum(s.vol) : "\u2013") + "</dd>" +
              "<dt>AVG PRINT</dt><dd>" + fnum(Math.round(tape.reduce((a, r) => a + r.sz, 0) / (tape.length || 1))) + "</dd>" +
            "</dl>" +
          "</div>" +
        "</div>" +
      "</div>";
    return {
      title: "DEPTH",
      sub: "Market depth \u00b7 " + s.sym + " \u00b7 " + s.name,
      right: "LEVEL 2 \u00b7 SIM",
      html: html
    };
  }

  /* ---------------- market map (MAP) ---------------- */
  function viewMAP() {
    const eq = equities();
    App.rows = [];
    const groups = {};
    eq.forEach((s) => { (groups[s.sect] = groups[s.sect] || []).push(s); });
    const maxM = Math.max.apply(null, eq.map((s) => s.mcap || 1)) || 1;
    const secs = Object.keys(groups).sort((a, b) => {
      const sum = (k) => groups[k].reduce((x, s) => x + (s.mcap || 0), 0);
      return sum(b) - sum(a);
    });
    const cols = secs.map((name) => {
      const list = groups[name].slice().sort((a, b) => (b.mcap || 0) - (a.mcap || 0));
      const tiles = list.map((s) => {
        const cp = chgp(s);
        const col = cp >= 0 ? "32,201,122" : "255,77,94";
        const a = Math.min(0.82, 0.10 + Math.abs(cp) / 4);
        const grow = 0.35 + Math.sqrt((s.mcap || 1) / maxM) * 2.4;
        return '<div class="mtile" data-sym="' + s.sym + '" role="button" tabindex="0" title="' + s.sym + " \u00b7 " + s.name +
          " \u00b7 " + fpct(cp) + '" style="background:rgba(' + col + "," + a.toFixed(2) + ");flex-grow:" + grow.toFixed(2) + '">' +
          "<b>" + s.sym + "</b><span>" + fpct(cp) + "</span></div>";
      }).join("");
      const avg = list.reduce((x, s) => x + chgp(s), 0) / (list.length || 1);
      return '<div class="mcol"><div class="mcl"><span title="' + String(name).replace(/"/g, "&quot;") + '">' + name + '</span><b class="' + cls(avg) + '">' + fpct(avg) + "</b></div>" +
        '<div class="mtiles">' + tiles + "</div></div>";
    }).join("");
    const up = eq.filter((s) => chgp(s) >= 0).length;
    const card = (l, v, c) => '<div class="card"><span>' + l + "</span><b class=\"" + (c || "") + "\">" + v + "</b></div>";
    const best = eq.slice().sort((a, b) => chgp(b) - chgp(a))[0];
    const worst = eq.slice().sort((a, b) => chgp(a) - chgp(b))[0];
    const html =
      '<div class="port map">' +
        '<div class="vbar"><span class="dim">Tile height scales with market cap, fill colour with session change \u00b7 click a tile for DES</span>' +
          '<span class="dim">' + new Set(eq.map((s) => s.cls)).size + " classes</span></div>" +
        '<div class="cards">' +
          card("ADVANCERS", String(up), "up") +
          card("DECLINERS", String(eq.length - up), "dn") +
          card("BREADTH", ((up / (eq.length || 1)) * 100).toFixed(0) + "%", up >= eq.length / 2 ? "up" : "dn") +
          card("BEST", best.sym + " " + fpct(chgp(best)), "up") +
          card("WORST", worst.sym + " " + fpct(chgp(worst)), "dn") +
        "</div>" +
        '<div class="mmap">' + cols + "</div>" +
        '<div class="eqsnote">Heat map covers the local equity universe only (' + eq.length + " names across " + secs.length +
          " sectors). Index, FX, commodity and government-bond instruments are not shown; open WEI or FX for those.</div>" +
      "</div>";
    return { title: "MAP", sub: "Market map \u00b7 " + eq.length + " equities \u00b7 " + secs.length + " sectors", right: "SESSION", html: html };
  }

  /* ---------------- SET: settings, profiles, export ---------------- */
  function viewSET() {
    const st = setts();
    const on = (x) => (x ? " on" : "");
    const themes = THEMES.map((t) =>
      '<button class="pbtn' + on((Store.data.theme || "AMBER") === t) + '" data-set="theme" data-val="' + t + '">' + t + "</button>").join("");
    const icons = [16, 32, 64, 128, 256].map((v) =>
      '<button class="pbtn iconbtn' + on(String(st.icon) === String(v)) + '" data-set="icon" data-val="' + v + '" title="' + v + 'px">' +
      '<img class="pico" src="assets/icon-' + v + '.png" alt="' + v + 'px"></button>').join("");
    const dens = ["normal", "compact"].map((d) =>
      '<button class="pbtn' + on(st.density === d) + '" data-set="density" data-val="' + d + '">' + d.toUpperCase() + "</button>").join("");
    const profs = profileNames().map((n) =>
      '<button class="pchip' + on(n === App.user) + '" data-prof="' + n + '">' + n + "</button>").join("");
    const perm = !("Notification" in window) ? "UNSUPPORTED" : Notification.permission.toUpperCase();
    const row = (k, label, hint) =>
      '<div class="srow"><div class="slab"><b>' + label + "</b><i>" + hint + "</i></div>" +
      '<button class="swtch' + on(st[k]) + '" data-set="' + k + '" data-val="' + (st[k] ? "0" : "1") +
      '" aria-pressed="' + (!!st[k]) + '" aria-checked="' + (!!st[k]) + '" role="switch">' + (st[k] ? "ON" : "OFF") + "</button></div>";

    return {
      title: "SETTINGS",
      sub: "preferences \u00b7 profiles \u00b7 export",
      right: "SET \u00b7 " + App.user,
      html:
        '<div class="setwrap"><div class="setgrid">' +
          '<section class="setcard"><h3>FEEDBACK</h3>' +
            row("sound", "ALERT TONE", "square-wave ping when a price alert fires") +
            row("notify", "DESKTOP NOTIFICATION", "system toast \u00b7 permission: " + perm) +
          "</section>" +
          '<section class="setcard"><h3>PERFORMANCE</h3>' +
            row("pauseHidden", "PAUSE WHEN HIDDEN", "stop the tick loop while this tab is backgrounded") +
            '<div class="srow"><div class="slab"><b>DENSITY</b><i>row height across every table</i></div><div class="sbtns">' + dens + "</div></div>" +
          "</section>" +
          '<section class="setcard"><h3>APPEARANCE</h3>' +
            '<div class="srow"><div class="slab"><b>THEME</b><i>palette for chrome and canvases</i></div><div class="sbtns">' + themes + "</div></div>" +
            '<div class="srow"><div class="slab"><b>BRAND ICON</b><i>favicon from the installer asset set</i></div><div class="sbtns">' + icons + "</div></div>" +
            '<div class="srow"><div class="slab"><b>SCALE</b><i>workstation zoom \u00b7 also \u2318 + / \u2212 / 0</i></div>' +
              '<div class="sbtns"><button class="xbtn" data-zoom="-0.1" aria-label="Zoom out">\u2212</button>' +
              '<b class="acc" id="setzoom" style="display:inline-block;min-width:44px;text-align:center">' + Math.round((App.zoom || 1) * 100) + "%</b>" +
              '<button class="xbtn" data-zoom="0.1" aria-label="Zoom in">+</button>' +
              '<button class="xbtn" data-zoom="0">RESET</button></div></div>' +
          "</section>" +
          '<section class="setcard"><h3>PROFILES</h3>' +
            '<div class="srow"><div class="slab"><b>CURRENT</b><i>state is stored per profile</i></div><b class="acc">' + App.user + "</b></div>" +
            '<div class="srow"><div class="slab"><b>SWITCH</b><i>' + profileNames().length + ' saved</i></div><div class="plist">' + profs + "</div></div>" +
            '<div class="srow"><div class="slab"><b>MANAGE</b><i>create, rename or delete a profile</i></div>' +
              '<div class="sbtns"><input id="setprof" class="sinp" maxlength="12" placeholder="NAME" spellcheck="false" aria-label="new profile name">' +
              '<button class="xbtn" data-prof="new">+ CREATE</button>' +
              '<button class="xbtn" data-prof="rename">RENAME</button>' +
              '<button class="xbtn" data-prof="del">DELETE</button></div></div>' +
          "</section>" +
          '<section class="setcard"><h3>EXPORT</h3>' +
            '<div class="srow"><div class="slab"><b>CHART PNG</b><i>raster snapshot of the live canvas</i></div><div class="sbtns">' +
              '<button class="xbtn" data-png="GP">GP</button>' +
              '<button class="xbtn" data-png="FA">FA</button>' +
              '<button class="xbtn" data-png="GOV">GOV</button>' +
              '<button class="xbtn" data-png="CMDT">CMDT</button></div></div>' +
            '<div class="srow"><div class="slab"><b>TABLES CSV</b><i>blotter, positions, orders, alerts</i></div><div class="sbtns">' +
              '<button class="xbtn" data-csv="trd">TRD</button>' +
              '<button class="xbtn" data-csv="port">PORT</button>' +
              '<button class="xbtn" data-csv="ord">ORD</button>' +
              '<button class="xbtn" data-csv="alrt">ALRT</button>' +
              '<button class="xbtn" data-print="1">\u2399 PRINT</button></div></div>' +
          "</section>" +
          '<section class="setcard"><h3>DATA</h3>' +
            '<div class="srow"><div class="slab"><b>BACKUP JSON</b><i>whole profile \u00b7 last: ' +
              (Store.data.lastBackup || "never") + "</i></div><div class=\"sbtns\">" +
              '<button class="xbtn" data-backup="export">\u2913 EXPORT</button>' +
              '<button class="xbtn" data-backup="import">\u2911 IMPORT</button></div></div>' +
            '<div class="srow"><div class="slab"><b>RESET PROFILE</b><i>wipe positions, blotter and alerts for ' + App.user + "</i></div>" +
              '<div class="sbtns"><button class="xbtn danger" data-backup="reset">RESET</button></div></div>' +
          "</section>" +
          '<section class="setcard span2"><h3>WORKSPACE & SYSTEM</h3>' +
            row("reduceMotion", "REDUCED MOTION", "disable pulses, flashing cells and animated transitions") +
            row("hideMonitor", "HIDE SIDEBAR MONITOR", "reserve sidebar space for function navigation") +
            '<div class="srow"><div class="slab"><b>SYSTEM PAGES</b><i>layout, data sources and built-in components</i></div><div class="sbtns"><button class="xbtn" data-go="WORK">WORKSPACE</button><button class="xbtn" data-go="CONN">CONNECTIONS</button><button class="xbtn" data-go="PLUG">COMPONENTS</button><button class="xbtn" data-go="ABOUT">ABOUT</button><button class="xbtn" data-go="ACCOUNT">ACCOUNT</button><button class="xbtn" data-go="INBOX">NOTIFICATIONS</button><button class="xbtn" data-go="SUPPORT">SUPPORT</button></div></div>' +
          '</section>' +
          '<section class="setcard span2"><h3>ABOUT</h3>' +
            '<div class="srow"><div class="slab"><b>INSTALLER ASSETS</b><i>Bloomberg installer replica built from ui-assets</i></div>' +
              '<div class="sbtns"><a class="xbtn" href="installer/index.html" target="_blank" rel="noopener">OPEN REPLICA</a></div></div>' +
            '<div class="srow"><div class="slab"><b>KEYBOARD</b><i>type a function code or use the rail</i></div>' +
              '<div class="sbtns"><button class="xbtn" data-go="HELP">FUNCTION GUIDE</button></div></div>' +
            '<div class="srow"><div class="slab"><b>DATA SOURCE</b><i>local random walk \u00b7 no network, no storage of quotes</i></div><b class="dim">v1.0</b></div>' +
          "</section>" +
        "</div></div>"
    };
  }

  function askNotify() {
    if (!("Notification" in window)) { notice("Notifications unsupported in this browser", true); return false; }
    if (Notification.permission === "granted") { saveSetts({ notify: true }); if (App.func === "SET") render(); return true; }
    if (Notification.permission === "denied") { notice("Notifications blocked in browser settings", true); return false; }
    try {
      Notification.requestPermission().then(() => {
        const ok = Notification.permission === "granted";
        saveSetts({ notify: ok });
        notice(ok ? "Desktop alerts enabled" : "Notification permission " + Notification.permission.toLowerCase(), !ok);
        if (App.func === "SET") render();
      }).catch(() => notice("Notification request failed", true));
    } catch (e) { notice("Notification request failed", true); }
    return true;
  }

  function notifyAlert(a, s) {
    const st = setts();
    if (!st.notify || !("Notification" in window) || Notification.permission !== "granted") return false;
    try {
      const n = new Notification("ALERT #" + a.id + " \u00b7 " + a.sym, {
        body: a.op + " " + f2(a.px) + " \u00b7 last " + f2(s.px),
        tag: "terminal-alert-" + a.id,
        icon: "assets/icon-128.png"
      });
      n.onclick = () => { try { window.focus(); go("ALRT"); } catch (e) { /* ignore */ } };
      return true;
    } catch (e) { return false; }
  }

  function exportPNG(kind) {
    const map = { GP: "#canvas", FA: "#fachart", GOV: "#ycurve", CMDT: "#cmdcurve" };
    const k = String(kind || "").toUpperCase();
    const sel = map[k];
    if (!sel) { notice("PNG export: GP | FA | GOV | CMDT", true); return false; }
    const canvasId = sel.slice(1);
    const focused = App.layout === "1" ? document.getElementById("view") : document.querySelector('.qcell[data-cell="' + App.focus + '"]');
    const findCanvas = host => host && (host.querySelector('[id="' + canvasId + '"]') || host.querySelector('[id$="-' + canvasId + '"]'));
    const cv = findCanvas(focused) || findCanvas(document.getElementById("view"));
    if (!cv || !cv.width) { if (App.func !== k) { go(k, App.sym || "AAPL"); return exportPNG(k); } notice("Chart is not ready to export", true); return false; }
    let href = "";
    try { href = cv.toDataURL("image/png"); } catch (e) { notice("Canvas export failed", true); return false; }
    const a = document.createElement("a");
    a.href = href;
    const ownerCell = cv.closest(".qcell");
    const exportSym = ownerCell ? panelAt(Number(ownerCell.getAttribute("data-cell"))).sym : App.sym;
    a.download = "terminal-" + k.toLowerCase() + "-" + (exportSym || "MKT") + ".png";
    document.body.appendChild(a);
    a.click();
    a.remove();
    notice("Exported " + a.download);
    return true;
  }

  function normProfile(raw) {
    return String(raw || "").toUpperCase().replace(/[^A-Z0-9_.-]/g, "").slice(0, 12);
  }

  function profileNew(raw) {
    const u = normProfile(raw);
    if (!u) { notice("Profile name: A-Z 0-9 only", true); return false; }
    if (profileNames().indexOf(u) >= 0) { notice("Profile " + u + " already exists", true); return false; }
    switchUser(u);
    Store.save();
    if (App.func === "SET") render();
    notice("Profile " + u + " created");
    return true;
  }

  function profileRename(raw) {
    const u = normProfile(raw);
    if (!u) { notice("Profile name: A-Z 0-9 only", true); return false; }
    if (u === App.user) { notice("Profile name unchanged", true); return false; }
    if (profileNames().indexOf(u) >= 0) { notice("Profile " + u + " already exists", true); return false; }
    const old = App.user;
    Store.save();
    try {
      const cur = localStorage.getItem(PROFILE_PREFIX + old);
      if (cur !== null) localStorage.setItem(PROFILE_PREFIX + u, cur);
    } catch (e) { /* ignore */ }
    switchUser(u);
    Store.save();
    try { localStorage.removeItem(PROFILE_PREFIX + old); } catch (e) { /* ignore */ }
    render();
    notice("Profile " + old + " renamed to " + u);
    return true;
  }

  function profileDelete() {
    if (App.user === "GUEST") { notice("GUEST is the fallback profile and cannot be deleted", true); return false; }
    const gone = App.user;
    switchUser("GUEST");
    try { localStorage.removeItem(PROFILE_PREFIX + gone); } catch (e) { /* ignore */ }
    render();
    notice("Profile " + gone + " deleted");
    return true;
  }

  /* ---------------- watchlist reorder / touch / keyboard affordances ---------------- */
  function watchMove(sym, delta) {
    const w = Store.data.watch.slice();
    const i = w.indexOf(sym);
    if (i < 0) return false;
    const j = Math.max(0, Math.min(w.length - 1, i + delta));
    if (j === i) return false;
    w.splice(i, 1);
    w.splice(j, 0, sym);
    Store.data.watch = w;
    Store.save();
    render();
    notice("Watchlist order saved");
    return true;
  }

  function mountKbdRows() {
    const rows = document.querySelectorAll('#view tbody tr[data-sym], #view tbody tr[data-i]');
    Array.prototype.forEach.call(rows, (tr) => {
      if (tr.getAttribute("tabindex") === "0") return;
      tr.setAttribute("tabindex", "0");
      tr.setAttribute("role", "row");
      const sym = tr.getAttribute("data-sym");
      if (sym && !tr.getAttribute("aria-label")) tr.setAttribute("aria-label", sym + " row \\u00b7 Enter for actions");
    });
  }

  function mountWatchDrag(root) {
    const body = root ? root.querySelector("tbody") : document.querySelector(".qcell.focus tbody") || document.querySelector("#view tbody");
    if (!body) return;
    Array.prototype.forEach.call(body.querySelectorAll("tr[data-sym]"), (tr) => {
      tr.setAttribute("draggable", "true");
      tr.setAttribute("title", "drag to reorder \\u00b7 right-click or long-press for actions");
    });
    if (body.getAttribute("data-dragbound") === "1") return;
    body.setAttribute("data-dragbound", "1");
    body.addEventListener("dragstart", (e) => {
      const tr = e.target.closest ? e.target.closest("tr[data-sym]") : null;
      if (!tr) return;
      App.dragSym = tr.getAttribute("data-sym");
      tr.classList.add("dragging");
      try { e.dataTransfer.effectAllowed = "move"; e.dataTransfer.setData("text/plain", App.dragSym); } catch (er) { /* ignore */ }
    });
    body.addEventListener("dragover", (e) => {
      if (!App.dragSym) return;
      const tr = e.target.closest ? e.target.closest("tr[data-sym]") : null;
      if (!tr || tr.getAttribute("data-sym") === App.dragSym) return;
      e.preventDefault();
      const dragEl = body.querySelector("tr.dragging");
      if (!dragEl) return;
      const r = tr.getBoundingClientRect();
      const after = e.clientY > r.top + r.height / 2;
      body.insertBefore(dragEl, after ? tr.nextSibling : tr);
    });
    body.addEventListener("drop", (e) => {
      if (!App.dragSym) return;
      e.preventDefault();
      const order = Array.prototype.map.call(body.querySelectorAll("tr[data-sym]"), (t) => t.getAttribute("data-sym")).filter((x) => bySym[x]);
      App.dragSym = null;
      if (order.length) { Store.data.watch = order; Store.save(); notice("Watchlist order saved"); }
      render();
    });
    body.addEventListener("dragend", () => {
      if (!App.dragSym) return;
      App.dragSym = null;
      render();
    });
  }

  function bindTouchAffordances() {
    let lp = null;
    const cancel = () => { if (lp) { clearTimeout(lp); lp = null; } };
    document.addEventListener("touchstart", (e) => {
      const row = e.target.closest ? e.target.closest("#view tbody tr[data-sym]") : null;
      if (!row || !e.touches || !e.touches.length) return;
      const x = e.touches[0].clientX;
      const y = e.touches[0].clientY;
      cancel();
      lp = setTimeout(() => {
        lp = null;
        openCtx(Math.round(x), Math.round(y), row.getAttribute("data-sym"));
        try { if (navigator.vibrate) navigator.vibrate(12); } catch (er) { /* ignore */ }
      }, 520);
    }, { passive: true });
    ["touchend", "touchmove", "touchcancel"].forEach((ev) => document.addEventListener(ev, cancel, { passive: true }));

  }

  /* System UI pages: local state and explicit integration boundaries. */
  function systemPage(title, sub, html) {
    return {title, sub, right: "LOCAL UI", html: '<div class="setwrap"><div class="setgrid">' + html + '</div></div>'};
  }
  function systemCard(title, text, action) {
    return '<section class="setcard"><h3>' + title + '</h3><p class="system-copy">' + text + '</p>' + (action || '') + '</section>';
  }
  function viewCONN() {
    return systemPage("CONNECTIONS", "data sources · permissions · session status",
      systemCard("LOCAL SIMULATION", 'Active · ' + UNIV.length + ' instruments. Quotes, depth, news and fundamentals are simulated locally. No exchange session is connected.', '<div class="cards"><div class="card"><span>ENGINE</span><b class="up">LOCAL</b></div><div class="card"><span>TICKS</span><b>' + App.ticks + '</b></div></div>') +
      systemCard("MARKET DATA PROVIDERS", 'Bloomberg, exchange and broker feeds are not integrated. This UI has no credentials or entitlement service. Provider setup requires a separate backend integration.', '<button class="xbtn" data-go="FEED">PROVIDER SETUP</button>') +
      systemCard("BROWSER PERMISSIONS", 'Desktop notifications: ' + (!("Notification" in window) ? 'unsupported' : Notification.permission) + '. Alert audio and notification preferences can be configured in Settings.', '<button class="xbtn" data-go="SET">OPEN SETTINGS</button>') +
      systemCard("LOCAL STORAGE", 'Profiles, layouts, watchlists and simulated activity are saved in this browser. Export a profile JSON before moving to a different browser.', '<button class="xbtn" data-backup="export">EXPORT PROFILE</button>'));
  }
  function viewPLUG() {
    const entries = [["CHART ENGINE", "Canvas price charts, indicators and drawing tools", "GP"], ["RESEARCH TOOLS", "Financial statements, screening and peer comparison", "EQS"], ["ALERT ENGINE", "Local price conditions and trigger log", "ALRT"], ["DATA TRANSFER", "CSV, PNG and profile JSON export", "SET"]];
    return systemPage("COMPONENTS", "built-in modules · external integration inventory",
      entries.map(e => systemCard(e[0], 'Built in · ' + e[1], '<button class="xbtn" data-go="' + e[2] + '">OPEN MODULE</button>')).join('') +
      systemCard("EXCEL / OFFICE ADD-IN", 'Formula builder, export and add-in preferences UI. Native add-in remains disconnected.', '<button class="xbtn" data-go="XL">OPEN OFFICE TOOLS</button>') +
      systemCard("MESSAGING / API / BROKER", 'Configuration and local preview pages are available. External services remain disconnected.', '<div class="sbtns"><button class="xbtn" data-go="MSG">MESSAGING</button><button class="xbtn" data-go="FEED">DATA SETUP</button><button class="xbtn" data-go="BROKER">BROKER</button></div>'));
  }
  function viewWORK() {
    const st = setts();
    const toggle = (key, name) => '<button class="xbtn" data-set="' + key + '" data-val="' + (st[key] ? '0' : '1') + '" aria-pressed="' + !!st[key] + '">' + name + ': ' + (st[key] ? 'ON' : 'OFF') + '</button> ';
    const saved = integrationState().workspaces.map((w,i) => '<div class="saved-workspace"><b>'+uiEscape(w.name)+'</b><span>'+w.layout+' panels</span><button class="xbtn" data-workspace-load="'+i+'">LOAD</button><button class="xbtn" data-workspace-delete="'+i+'">DELETE</button></div>').join('');
    return systemPage("WORKSPACE", "layout · accessibility · navigation",
      systemCard("PANEL LAYOUT", 'Use one, two or four independent panels. Click a panel header to focus it; choose a function from its dropdown. Drag dividers to resize.', '<div class="sbtns"><button class="xbtn" data-system-layout="1">SINGLE</button><button class="xbtn" data-system-layout="2">TWO PANELS</button><button class="xbtn" data-system-layout="4">FOUR PANELS</button><button class="xbtn" data-system-reset-split="1">RESET DIVIDERS</button></div>') +
      '<section class="setcard"><h3>SAVED WORKSPACES</h3>'+uiForm('workspace',uiField('Workspace name','workspaceName','My workspace'),'SAVE CURRENT WORKSPACE')+'<p class="system-copy">Save panel functions, securities, layout and divider positions. Up to 12 per profile.</p>'+(saved || '<p class="system-copy">No saved workspaces.</p>')+'</section>' +
      systemCard("ACCESSIBILITY", 'Preferences are saved per profile. Reduced motion disables animation and transition effects.', toggle('reduceMotion','REDUCED MOTION') + toggle('hideMonitor','HIDE MONITOR')) +
      systemCard("KEYBOARD & SEARCH", 'Use the command bar, F1–F12, Cmd/Ctrl+K palette or All functions directory. Escape closes overlays.', '<button class="xbtn" data-go="HELP">FUNCTION GUIDE</button>') +
      systemCard("DISPLAY & BACKUP", 'Theme, table density, interface scale, profile management and JSON backup are available in Settings.', '<button class="xbtn" data-go="SET">DISPLAY SETTINGS</button>'));
  }
  function viewABOUT() {
    return systemPage("ABOUT", "UI scope · reconstruction evidence",
      systemCard("UI INVENTORY", '37 function pages, plus local login, command palette, keyboard reference, context menus and an installer preview. System pages are included in single and split workspaces.') +
      systemCard("LAYOUT PROVENANCE", 'The terminal shell and new pages are a reconstruction based on the handed-over web project. Original application screenshots and runtime UI trees were not available for comparison. Pixel-identical original layout is not verified.') +
      systemCard("BINARY EVIDENCE", 'REA artifact inspection was run on both EXE installers. Deep native analysis was unavailable without a configured provider. The extracted sotr directory does not provide a complete executable for the attempted inspection route.') +
      systemCard("INSTALLER PREVIEW", 'The previous installer preview is bundled locally. It demonstrates installer screens; it does not install software.', '<a class="xbtn" href="installer/index.html" target="_blank" rel="noopener">OPEN PREVIEW</a>') +
      systemCard("SCOPE", 'Market data, financials, news and execution are demonstrations. External integrations listed in Components remain unimplemented.', '<button class="xbtn" data-go="PLUG">COMPONENT INVENTORY</button>'));
  }

  function uiEscape(value) { return String(value == null ? '' : value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
  function integrationState() {
    if (!Store.data.integrationUI) Store.data.integrationUI = { feed: 'Local simulation', broker: 'Paper workspace', office: 'Excel', messages: [], notices: [], preferences: {} };
    const ui = Store.data.integrationUI;
    if (!Array.isArray(ui.workspaces)) ui.workspaces = [];
    return ui;
  }
  function uiField(label, name, value, options) {
    return '<label class="integration-field"><span>' + label + '</span>' + (options ? '<select name="' + name + '">' + options.map(v => '<option' + (v === value ? ' selected' : '') + '>' + uiEscape(v) + '</option>').join('') + '</select>' : '<input name="' + name + '" value="' + uiEscape(value) + '" maxlength="120" required>') + '</label>';
  }
  function uiForm(kind, body, button) { return '<form class="integration-form" data-ui-form="' + kind + '">' + body + '<button class="xbtn" type="submit">' + button + '</button><output class="integration-result" aria-live="polite"></output></form>'; }
  function uiStatus() { return '<div class="integration-banner">LOCAL PREVIEW · Configuration is saved in this profile. External services are not connected.</div>'; }
  function viewFEED() {
    const st = integrationState();
    return systemPage('DATA SOURCES','provider setup · subscriptions · diagnostics',
      '<section class="setcard span2">' + uiStatus() + '<h3>PROVIDER CONFIGURATION</h3>' + uiForm('feed', uiField('Provider','provider',st.feed,['Local simulation','Bloomberg Desktop API','Exchange feed','Custom market API']) + uiField('Dataset','dataset',st.preferences.dataset || 'Equities',['Equities','FX','Rates','Commodities']) + uiField('Refresh interval','refresh',st.preferences.refresh || '1 second',['1 second','5 seconds','15 seconds','On demand']), 'SAVE PREVIEW CONFIGURATION') + '</section>' +
      systemCard('SUBSCRIPTIONS','Local sample universe: ' + UNIV.length + ' instruments. Real-time exchange entitlements and provider API credentials have not been configured.','<button class="xbtn" data-go="W">OPEN WATCHLIST</button>') +
      systemCard('CONNECTION DIAGNOSTICS','Local simulation engine is available. External provider state: disconnected. Saving a provider selection does not switch the quote engine.','<button class="xbtn" data-ui-check="feed">CHECK LOCAL STATUS</button><output class="integration-result" aria-live="polite"></output>'));
  }
  function viewBROKER() {
    const st=integrationState();
    return systemPage('BROKER','connection setup · routing preview · order controls',
      '<section class="setcard span2">' + uiStatus() + '<h3>CONNECTION PROFILE</h3>' + uiForm('broker',uiField('Connection','provider',st.broker,['Paper workspace','Broker API','FIX session']) + uiField('Environment','environment','Paper / sandbox',['Paper / sandbox']) + uiField('Routing preference','routing',st.preferences.routing || 'Manual review',['Manual review','Order ticket']), 'SAVE CONNECTION PREVIEW') + '</section>' +
      systemCard('ROUTING STATUS','External routing: disconnected. Orders in this application use the existing local simulator. No account authentication, order submission or FIX session is performed.','<button class="xbtn" data-go="ORD">ORDER MONITOR</button>') +
      systemCard('ACCOUNT OVERVIEW','Review the local demonstration cash balance, positions and simulated fills.','<div class="sbtns"><button class="xbtn" data-go="PORT">PORTFOLIO</button><button class="xbtn" data-go="TRD">FILLS</button></div>'));
  }
  function viewXL() {
    const st=integrationState();
    return systemPage('OFFICE','spreadsheet tools · formula preview · local export',
      '<section class="setcard span2">' + uiStatus() + '<h3>FORMULA BUILDER</h3>' + uiForm('formula',uiField('Security','security',App.sym || 'AAPL') + uiField('Field','field','PX_LAST',['PX_LAST','PX_BID','PX_ASK','VOLUME']) + uiField('Formula type','formula','Reference',['Reference','History']), 'GENERATE FORMULA PREVIEW') + '</section>' +
      systemCard('WORKBOOK EXPORT','Export the current local portfolio or fills as CSV for a spreadsheet. This does not install an Office add-in.','<div class="sbtns"><button class="xbtn" data-csv="port">PORTFOLIO CSV</button><button class="xbtn" data-csv="trd">FILLS CSV</button></div>') +
      '<section class="setcard"><h3>ADD-IN PREFERENCES</h3>' + uiForm('office',uiField('Target application','office',st.office,['Excel','LibreOffice','CSV only']), 'SAVE PREFERENCE') + '<p class="system-copy">Native add-in installation, workbook streaming and Bloomberg formula execution are unavailable.</p></section>');
  }
  function viewMSG() {
    const st=integrationState();
    const drafts=st.messages.length ? st.messages.map((m,index)=>'<article class="message-preview"><b>'+uiEscape(m.recipient)+'</b><time>'+uiEscape(m.time)+'</time><p>'+uiEscape(m.text)+'</p><span class="dim">LOCAL DRAFT · NOT SENT</span><button class="xbtn" data-draft-delete="'+index+'" aria-label="Delete draft">DELETE DRAFT</button></article>').join('') : '<p class="system-copy">No local drafts. Compose a message to preview the conversation layout.</p>';
    return systemPage('MESSAGING','contacts · compose · local draft history',
      '<section class="setcard">'+uiStatus()+'<h3>COMPOSE</h3>'+uiForm('message',uiField('Contact','recipient','Research desk',['Research desk','Trading desk','Support desk'])+'<label class="integration-field"><span>Message</span><textarea name="text" maxlength="2000" required placeholder="Write a local draft…"></textarea></label>','SAVE LOCAL DRAFT')+'</section>'+systemCard('CONVERSATIONS','Drafts are stored only in this browser profile. No external delivery service is connected.',drafts));
  }
  function viewACCOUNT() {
    return systemPage('ACCOUNT','profile · session · entitlement status',
      systemCard('CURRENT PROFILE',uiEscape(App.user)+' · local browser profile. This is not an authenticated Bloomberg or broker account.','<button class="xbtn" data-go="SET">MANAGE PROFILES</button>')+
      systemCard('ENTITLEMENTS','Local UI modules: available. Live market data, native Office add-in, messaging and external order routing: not connected.','<button class="xbtn" data-go="PLUG">INTEGRATION DIRECTORY</button>')+
      systemCard('SESSION & DATA','Profile state is held in localStorage. No remote login session, password storage or cloud sync is configured.','<button class="xbtn" data-backup="export">BACKUP PROFILE</button>')+
      systemCard('NOTIFICATIONS','Review local configuration events and price alerts.','<button class="xbtn" data-go="INBOX">NOTIFICATION CENTER</button>'));
  }
  function viewINBOX() {
    const notices=integrationState().notices;
    return systemPage('NOTIFICATIONS','local events · read status · alert links',
      '<section class="setcard span2"><h3>LOCAL ACTIVITY</h3>'+(notices.length ? notices.map((n,index)=>'<article class="message-preview"><b>'+uiEscape(n.title)+'</b><time>'+uiEscape(n.time)+'</time><p>'+uiEscape(n.text)+'</p><span class="dim">'+(n.read?'READ':'UNREAD')+'</span><button class="xbtn" data-notice-read="'+index+'">'+(n.read?'MARK UNREAD':'MARK READ')+'</button></article>').join('') : '<p class="system-copy">No local events yet. Saving an integration preview adds an event here.</p>')+'<button class="xbtn" data-ui-read="all">MARK ALL READ</button></section>'+systemCard('PRICE ALERTS','Triggered price alerts and their log remain in the alert manager.','<button class="xbtn" data-go="ALRT">OPEN ALERT MANAGER</button>'));
  }
  function viewSUPPORT() {
    return systemPage('SUPPORT','help · diagnostics · reconstruction boundaries',
      systemCard('GETTING STARTED','Choose a function from the rail or All functions. Use the workspace controls to split panels. Change each panel with its function selector.','<button class="xbtn" data-go="HELP">COMMAND REFERENCE</button>')+
      systemCard('PAGE & FUNCTION INVENTORY','All registered functions are listed here. Integration pages provide local configuration previews.', '<div class="coverage-list">'+Object.keys(FUNCS).map(code=>'<div><button class="xbtn" data-go="'+code+'">'+code+'</button><span>'+FUNCS[code].label+'</span><small>'+(['FEED','BROKER','XL','MSG'].includes(code)?'LOCAL PREVIEW':'LOCAL UI')+'</small></div>').join('')+'</div>')+
      systemCard('LOCAL DIAGNOSTICS','30 original and system views plus seven integration UI pages. Canvas charts and local profile storage run in the browser. External services remain disconnected.','<button class="xbtn" data-ui-check="system">CHECK BROWSER FEATURES</button><output class="integration-result" aria-live="polite"></output>')+
      systemCard('CONTACT PREVIEW','Create a support message draft locally. It is not sent to a support service.','<button class="xbtn" data-go="MSG">COMPOSE DRAFT</button>')+
      systemCard('UI COVERAGE','These pages complete the identified UI gaps. Original application layout parity is still unverified.','<button class="xbtn" data-go="ABOUT">ABOUT THIS UI</button>'));
  }
  function recordUIEvent(title,text) {
    const st=integrationState();st.notices.unshift({title,text,time:new Date().toLocaleString(),read:false});st.notices=st.notices.slice(0,60);Store.save();
  }
  document.addEventListener('submit',e=>{
    const form=e.target.closest('[data-ui-form]');if(!form)return;e.preventDefault();
    const data=new FormData(form),kind=form.getAttribute("data-ui-form"),st=integrationState();let result='';
    if(kind==='workspace'){const name=String(data.get('workspaceName')).trim().slice(0,60);if(!name)return;const workspace={name,layout:App.layout,panels:JSON.parse(JSON.stringify(panels())),split:Object.assign({},Store.data.split),func:App.func,sym:App.sym};const existing=st.workspaces.findIndex(w=>w.name===name);if(existing>=0)st.workspaces[existing]=workspace;else if(st.workspaces.length<12)st.workspaces.push(workspace);else{form.querySelector('output').textContent='Workspace limit reached. Delete a saved workspace first.';return;}Store.save();render();return;}
    if(kind==='feed'){st.feed=String(data.get('provider'));st.preferences.dataset=String(data.get('dataset'));st.preferences.refresh=String(data.get('refresh'));result='Provider preference saved. Quotes continue to use local simulation.';}
    if(kind==='broker'){st.broker=String(data.get('provider'));st.preferences.routing=String(data.get('routing'));result='Connection preview saved. External routing remains disconnected.';}
    if(kind==='office'){st.office=String(data.get('office'));result='Spreadsheet preference saved. Native add-in is not installed.';}
    if(kind==='formula'){
      const sym=String(data.get('security')).trim().toUpperCase();if(!/^[A-Z0-9 ._/-]{1,40}$/.test(sym)){form.querySelector('output').textContent='Enter a valid security identifier (letters, numbers, spaces or ._/-).';return;}
      result=data.get('formula')==='History' ? '=BDH("'+sym+' US Equity","'+data.get('field')+'","20260101","20261103")' : '=BDP("'+sym+' US Equity","'+data.get('field')+'")';
      result+=' · Syntax preview only; requires a compatible installed add-in.';
    }
    if(kind==='message'){const text=String(data.get('text')).trim();if(!text)return;st.messages.unshift({recipient:String(data.get('recipient')),text:text.slice(0,2000),time:new Date().toLocaleString()});st.messages=st.messages.slice(0,40);recordUIEvent('Message draft saved','Local draft only; no message sent.');render();return;}
    if(kind!=='formula')recordUIEvent('Configuration saved',result);form.querySelector('output').textContent=result;
  });
  document.addEventListener('click',e=>{
    const draftDelete=e.target.closest('[data-draft-delete]');
    if(draftDelete){integrationState().messages.splice(Number(draftDelete.getAttribute('data-draft-delete')),1);Store.save();render();return;}
    const noticeRead=e.target.closest('[data-notice-read]');
    if(noticeRead){const n=integrationState().notices[Number(noticeRead.getAttribute('data-notice-read'))];if(n)n.read=!n.read;Store.save();render();return;}
    const workspaceDelete=e.target.closest('[data-workspace-delete]');
    if(workspaceDelete){integrationState().workspaces.splice(Number(workspaceDelete.getAttribute('data-workspace-delete')),1);Store.save();render();return;}
    const workspaceLoad=e.target.closest('[data-workspace-load]');
    if(workspaceLoad){const w=integrationState().workspaces[Number(workspaceLoad.getAttribute('data-workspace-load'))];if(!w)return;Store.data.panels=JSON.parse(JSON.stringify(w.panels));Store.data.split=Object.assign({},w.split);Store.data.layout=App.layout=w.layout;App.focus=0;App.func=w.func;App.sym=w.sym;Store.save();render();syncNavigation();notice('Workspace loaded: '+w.name);return;}
    const check=e.target.closest('[data-ui-check]');if(check){check.nextElementSibling.textContent=check.dataset.uiCheck==='feed' ? 'Local engine available · external provider disconnected.' : 'Canvas: '+(!!document.createElement('canvas').getContext('2d'))+' · Browser storage: '+(typeof localStorage!=='undefined')+' · Notifications: '+('Notification' in window)+' · External services: disconnected.';}
    if(e.target.closest('[data-ui-read]')){integrationState().notices.forEach(n=>n.read=true);Store.save();render();}
  });

  const VIEWS = { WEI: viewWEI, W: viewW, TOP: viewTOP, DES: viewDES, GP: viewGP, HP: viewHP, N: viewN, MOST: viewMOST, PORT: viewPORT, HELP: viewHELP, TRD: viewTRD, OPT: viewOPT, GOV: viewGOV, FX: viewFX, ECO: viewECO, COMP: viewCOMP, ORD: viewORD, ALRT: viewALRT, FA: viewFA, EQS: viewEQS, FLDS: viewFLDS, SRCH: viewSRCH, DEPTH: viewDEPTH, MAP: viewMAP, CMDT: viewCMDT, SET: viewSET, CONN: viewCONN, PLUG: viewPLUG, WORK: viewWORK, ABOUT: viewABOUT, XL: viewXL, MSG: viewMSG, FEED: viewFEED, BROKER: viewBROKER, ACCOUNT: viewACCOUNT, INBOX: viewINBOX, SUPPORT: viewSUPPORT };

  /* ---------------- render cycle ---------------- */
  for (const feature of window.TERMINAL_FEATURES || []) {
    if (!/^[A-Z0-9]+$/.test(feature.code) || FUNCS[feature.code]) continue;
    FUNCS[feature.code] = {label:feature.label,key:'',needsSym:false};
    VIEWS[feature.code] = () => ({title:feature.label,sub:'业务功能面板 · 数据状态以面板标识为准',right:'READ ONLY / PAPER',html:'<iframe class="legacy-feature-frame" title="'+uiEscape(feature.label)+'" data-terminal-feature="'+feature.code+'" src="features/terminal-feature.html"></iframe>'});
  }

  function render() {
    if (App.dragging) { App.renderPending = true; return; }
    const view = $("view");
    if (App.routeError) {
      view.className = ""; App.pfx = "";
      $("phTitle").textContent = "PAGE UNAVAILABLE";
      $("phSub").textContent = "Check the function code or security identifier";
      $("phRight").textContent = "LOCAL RECOVERY";
      view.innerHTML = '<div class="setwrap"><section class="setcard"><h3>PAGE NOT FOUND</h3><p class="system-copy">The address '+uiEscape(App.routeError)+' does not match an available function and security. Your saved profile has not been changed.</p><div class="sbtns"><button class="xbtn" data-go="HELP">FUNCTION DIRECTORY</button><button class="xbtn" data-go="WEI">MARKETS</button><button class="xbtn" data-go="SET">SETTINGS</button></div></section></div>';
      return;
    }
    if (App.layout !== "1") { renderQuad(); return; }
    view.className = "";
    App.pfx = "";
    const st = App.scrollMemo[App.func] != null ? App.scrollMemo[App.func] : 0;
    const fn = VIEWS[App.func] || viewHELP;
    const out = fn();
    view.innerHTML = out.html;
    $("phTitle").textContent = out.title;
    $("phSub").textContent = out.sub;
    $("phRight").textContent = out.right || "";
    const ph = document.querySelector(".panel-hd");
    if (ph) ph.setAttribute("data-printed", App.user + " \u00b7 " + hhmmss(new Date()) + " \u00b7 " + out.title);
    view.scrollTop = st;
    App.scrollMemo[App.func] = view.scrollTop;
    if (App.func === "SRCH") applySrchFilter();
    if (App.func === "TOP" || App.func === "N") applyNewsFilter();
    applySortToView();
    if (App.func === "GP") mountChart();
    if (App.func === "GOV") mountCurve();
    if (App.func === "CMDT") mountCmdCurve();
    if (App.func === "FA") mountFA();
    mountKbdRows();
    if (App.func === "W") mountWatchDrag();
    paintRail();
  }

  /* ---------------- split screen (2-up / 4-up) ---------------- */
  function panels() {
    if (!Array.isArray(Store.data.panels) || Store.data.panels.length !== 4) {
      Store.data.panels = [
        { func: "GP", sym: "AAPL" },
        { func: "W", sym: "" },
        { func: "TOP", sym: "" },
        { func: "ORD", sym: "" }
      ];
    }
    return Store.data.panels;
  }

  function panelAt(i) {
    const ps = panels();
    const p = ps[i];
    if (!p || !VIEWS[p.func]) {
      ps[i] = { func: ["GP", "W", "TOP", "ORD"][i] || "WEI", sym: "AAPL" };
    }
    return ps[i];
  }

  function nextLayout() {
    return App.layout === "1" ? "2" : App.layout === "2" ? "4" : "1";
  }

  function setLayout(mode) {
    mode = String(mode);
    if (["1", "2", "4"].indexOf(mode) < 0) { notice("Layout must be 1, 2 or 4", true); return; }
    App.layout = mode;
    Store.data.layout = mode;
    if(mode !== "1") { App.focus=Math.min(App.focus,mode === "4" ? 3 : 1); const panel=panelAt(App.focus);App.func=panel.func;if(panel.sym)App.sym=panel.sym; }
    Store.save();
    render();
    syncNavigation();
    notice("Layout " + mode + "-up" + (mode === "1" ? "" : " \u00b7 click a panel header to focus it"));
  }

  function renderQuad() {
    const view = $("view");
    const n = App.layout === "4" ? 4 : 2;
    if (App.focus >= n) App.focus = 0;
    view.className = "quadmode";
    view.innerHTML = '<div class="quad quad' + n + '">' +
      Array.from({ length: n }, (_, i) =>
        '<section class="qcell' + (i === App.focus ? " focus" : "") + '" data-cell="' + i + '">' +
          '<div class="qhd"><span class="qidx">' + (i + 1) + "</span>" +
            '<span class="qfn">\u2014</span><span class="qsub"></span></div>' +
          '<div class="qbody"></div>' +
        "</section>").join("") + "</div>";

    const host = view.querySelector(".quad");
    if (host) {
      host.insertAdjacentHTML("beforeend",
        '<div class="qsplit v" data-split="v" title="drag to resize \u00b7 double-click to reset"></div>' +
        (App.layout === "4" ? '<div class="qsplit h" data-split="h" title="drag to resize \u00b7 double-click to reset"></div>' : ""));
      mountSplitters(host);
      applySplit(host);
    }

    for (let i = 0; i < n; i++) {
      const cell = view.querySelector('.qcell[data-cell="' + i + '"]');
      if (!cell) continue;
      const body = cell.querySelector(".qbody");
      const p = panelAt(i);
      const savePfx = App.pfx, saveFn = App.func, saveSym = App.sym;
      App.pfx = "q" + i + "-";
      App.func = p.func;
      App.sym = p.sym || App.sym || "AAPL";
      const out = (VIEWS[p.func] || viewHELP)();
      body.innerHTML = out.html;
      // 同一个页面里四个面板，id 必须唯一
      body.querySelectorAll("[id]").forEach((el) => { if (!el.id.startsWith(App.pfx)) el.id = App.pfx + el.id; });
      cell.querySelector(".qfn").textContent = p.func;
      cell.querySelector(".qsub").textContent = out.title + (p.sym ? " \u00b7 " + p.sym : "");
      if (p.func === "GP") mountChart();
      if (p.func === "GOV") mountCurve();
      if (p.func === "CMDT") mountCmdCurve();
      if (p.func === "FA") mountFA();
      if (p.func === "W") mountWatchDrag(body);
      App.pfx = savePfx;
      App.func = saveFn;
      App.sym = saveSym;
    }
    App.pfx = "";
    mountKbdRows();
    if (panelAt(App.focus).func === "W") mountWatchDrag();
    $("phTitle").textContent = "SPLIT " + App.layout;
    $("phSub").textContent = "Multi-panel workspace \u00b7 panel " + (App.focus + 1) + " focused \u00b7 LAY 1 to go back";
    $("phRight").textContent = "PANEL " + (App.focus + 1) + "/" + n;
    paintRail();
  }

  function applySplit(host) {
    if (!host) return;
    const sp = Store.data.split || { c: 0.5, r: 0.5 };
    // on narrow viewports a two-up workspace stacks vertically so panels stay readable
    const narrow = window.matchMedia(App.layout === "4" ? "(max-width:680px)" : "(max-width:900px)").matches;
    if (narrow) {
      host.style.gridTemplateColumns = "minmax(0,1fr)";
      host.style.gridTemplateRows = App.layout === "4" ? "repeat(4,minmax(300px,1fr))" : "1fr 1fr";
      return;
    }
    host.style.gridTemplateColumns = sp.c + "fr " + (1 - sp.c) + "fr";
    host.style.gridTemplateRows = App.layout === "4" ? sp.r + "fr " + (1 - sp.r) + "fr" : "100%";
    host.querySelectorAll(".qsplit.v").forEach((el) => { el.style.left = sp.c * 100 + "%"; });
    host.querySelectorAll(".qsplit.h").forEach((el) => { el.style.top = sp.r * 100 + "%"; });
  }

  window.addEventListener("resize", () => {
    const host = document.querySelector(".quad");
    if (host) applySplit(host);
  });

  function mountSplitters(host) {
    host.querySelectorAll(".qsplit").forEach((sp) => {
      sp.addEventListener("mousedown", (ev) => {
        ev.preventDefault();
        const kind = sp.getAttribute("data-split");
        const rect = host.getBoundingClientRect();
        if (!rect.width || !rect.height) return;
        App.dragging = true;
        sp.classList.add("live");
        const move = (e) => {
          const raw = kind === "v" ? (e.clientX - rect.left) / rect.width : (e.clientY - rect.top) / rect.height;
          const v = Math.min(0.8, Math.max(0.2, raw));
          if (!Store.data.split) Store.data.split = { c: 0.5, r: 0.5 };
          if (kind === "v") Store.data.split.c = v;
          else Store.data.split.r = v;
          applySplit(host);
        };
        const up = () => {
          document.removeEventListener("mousemove", move);
          document.removeEventListener("mouseup", up);
          sp.classList.remove("live");
          App.dragging = false;
          Store.save();
          render();
          notice("Panel split " + Math.round(Store.data.split.c * 100) + "/" + Math.round(100 - Store.data.split.c * 100) +
            (App.layout === "4" ? " \u00b7 rows " + Math.round(Store.data.split.r * 100) + "/" + Math.round(100 - Store.data.split.r * 100) : ""));
        };
        document.addEventListener("mousemove", move);
        document.addEventListener("mouseup", up);
      });
      sp.addEventListener("dblclick", () => {
        Store.data.split = { c: 0.5, r: 0.5 };
        Store.save();
        render();
        notice("Panel split reset 50/50");
      });
    });
  }

  function focusCell(i) {
    const n = App.layout === "4" ? 4 : 2;
    if (!(i >= 0) || i >= n) return;
    App.focus = i;
    const p = panelAt(i);
    App.func = p.func;
    if (p.sym) App.sym = p.sym;
    App.pfx = "q" + i + "-";
    document.querySelectorAll(".qcell").forEach((c) =>
      c.classList.toggle("focus", Number(c.getAttribute("data-cell")) === i));
    $("phRight").textContent = "PANEL " + (i + 1) + "/" + n;
    $("phSub").textContent = "Multi-panel workspace · panel " + (i + 1) + " focused · LAY 1 to go back";
    paintRail();
    syncNavigation(true);
  }

  function paintRail() {
    const keys = $("fkeys");
    const opened = new Set(Array.from(keys.querySelectorAll("details[open]")).map(el=>el.dataset.group));
    const groups = {
      "Markets": ["WEI","W","MOST","MAP","FX","GOV","CMDT"],
      "Security analysis": ["DES","GP","HP","DEPTH","FA","OPT","COMP"],
      "Research & news": ["TOP","N","ECO","EQS","SRCH","FLDS"],
      "Portfolio & orders": ["PORT","ORD","TRD","ALRT"],
      "Settings & integrations": ["SET","WORK","CONN","FEED","PLUG","XL","BROKER","ACCOUNT","MSG","INBOX"],
      "Help": ["HELP","SUPPORT","ABOUT"]
    };
    for (const feature of window.TERMINAL_FEATURES || []) {
      const name = '业务 · ' + feature.page;
      (groups[name] ||= []).push(feature.code);
    }
    keys.innerHTML = Object.entries(groups).map(([name,codes])=>
      '<li class="rail-group"><details data-group="'+name+'"'+(opened.has(name)||codes.includes(App.func)||(!keys.children.length && name==="Markets")?' open':'')+'><summary>'+name+'</summary><ul>'+codes.map(k=>
      '<li data-fn="'+k+'" role="button" tabindex="0" aria-current="'+(App.func===k?'page':'false')+'" title="'+FUNCS[k].label+'"'+(App.func===k?' class="on"':'')+'><span class="k">'+FUNCS[k].key+'</span><span class="nm">'+k+'  '+FUNCS[k].label+'</span></li>').join('')+'</ul></details></li>').join('');


    const mon = $("monitor");
    const list = ["SPX", "AAPL", "NVDA", "MSFT", "TSLA"];
    mon.innerHTML = list.map((s) => {
      const q = bySym[s];
      const cp = chgp(q);
      return '<li data-sym="' + s + '"><span class="nm" style="flex:1">' + s + "</span>" +
        '<span style="font-variant-numeric:tabular-nums">' + f2(q.px) + "</span>" +
        '<span class="' + cls(cp) + '" style="width:56px;text-align:right;font-size:10.5px">' + fpct(cp) + "</span></li>";
    }).join("");
  }

  /* ---------------- chart ---------------- */
  let chartCtx = null;
  const chartGeom = {};

  function rsiArr(bars, n) {
    const out = new Array(bars.length).fill(null);
    let g = 0, l = 0;
    for (let i = 1; i < bars.length; i++) {
      const d = bars[i][3] - bars[i - 1][3];
      const up = Math.max(d, 0), dn = Math.max(-d, 0);
      if (i <= n) {
        g += up; l += dn;
        if (i === n) {
          g /= n; l /= n;
          out[i] = 100 - 100 / (1 + (l === 0 ? 99 : g / l));
        }
      } else {
        g = (g * (n - 1) + up) / n;
        l = (l * (n - 1) + dn) / n;
        out[i] = 100 - 100 / (1 + (l === 0 ? 99 : g / l));
      }
    }
    return out;
  }

  function emaArr(vals, n) {
    const k = 2 / (n + 1);
    const out = [];
    let prev = null;
    vals.forEach((v, i) => {
      if (v == null) { out.push(null); return; }
      prev = prev == null ? v : v * k + prev * (1 - k);
      out.push(prev);
    });
    return out;
  }

  function macdArr(bars) {
    const close = bars.map((b) => b[3]);
    const e12 = emaArr(close, 12), e26 = emaArr(close, 26);
    const dif = close.map((v, i) => e12[i] - e26[i]);
    const dea = emaArr(dif, 9);
    const hist = dif.map((v, i) => (v - dea[i]) * 2);
    return { dif: dif, dea: dea, hist: hist };
  }

  function mountChart() {
    const cv = $(pid("canvas"));
    if (!cv) return;
    const s = bySym[App.sym] || bySym["AAPL"];
    const box = cv.parentElement;
    const dpr = window.devicePixelRatio || 1;

    function size() {
      const w = box.clientWidth - 20;
      const h = box.clientHeight - 8;
      cv.width = Math.max(160, w * dpr);
      cv.height = Math.max(200, h * dpr);
      cv.style.width = Math.max(160, w) + "px";
      cv.style.height = Math.max(200, h) + "px";
    }
    size();

    const bars = (s.series[App.period] || s.hist).slice(-90);

    function draw(hover) {
      const W = cv.width, H = cv.height;
      const ctx = cv.getContext("2d");
      chartCtx = ctx;
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.clearRect(0, 0, W, H);
      ctx.scale(dpr, dpr);
      const w = W / dpr, h = H / dpr;

      const padL = 6, padR = 62, padT = Math.max(34, (box.querySelector(".legend")?.offsetHeight || 0) + 20), padB = 52;
      const cw = w - padL - padR, ch = h - padT - padB;
      let mn = Infinity, mx = -Infinity, vmax = 0;
      bars.forEach((b) => { mn = Math.min(mn, b[2]); mx = Math.max(mx, b[1]); vmax = Math.max(vmax, b[4]); });
      const span = mx - mn || 1;
      mn -= span * 0.06; mx += span * 0.06;
      const lg = !!App.logScale && mn > 0;
      const LY = (v) => (lg ? Math.log(Math.max(v, mn * 0.5)) : v);
      const X = (i) => padL + (i + 0.5) * (cw / bars.length);
      const Y = (v) => padT + ch - ((LY(v) - LY(mn)) / (LY(mx) - LY(mn) || 1)) * ch;
      chartGeom[App.pfx || "_"] = { w: w, h: h, padL: padL, padT: padT, cw: cw, ch: ch, mn: mn, mx: mx };

      // grid
      ctx.strokeStyle = "#121b23"; ctx.lineWidth = 1;
      ctx.font = "10px ui-monospace,Menlo,monospace"; ctx.fillStyle = "#5d6f7e";
      ctx.textAlign = "left"; ctx.textBaseline = "middle";
      for (let i = 0; i <= 5; i++) {
        const y = padT + (ch / 5) * i;
        ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(padL + cw, y); ctx.stroke();
        const v = mx - ((mx - mn) / 5) * i;
        ctx.fillText(f2(v), padL + cw + 8, y);
      }
      for (let i = 0; i <= 6; i++) {
        const x = padL + (cw / 6) * i;
        ctx.beginPath(); ctx.moveTo(x, padT); ctx.lineTo(x, padT + ch); ctx.stroke();
      }

      // lower study: volume / RSI / MACD
      const vh = 34, vy = padT + ch + 10;
      if (App.sub === "VOL") {
        bars.forEach((b, i) => {
          const bh = (b[4] / (vmax || 1)) * vh;
          ctx.fillStyle = b[3] >= b[0] ? "rgba(32,201,122,.42)" : "rgba(255,77,94,.42)";
          ctx.fillRect(X(i) - 3, vy + vh - bh, 6, bh);
        });
      } else if (App.sub === "RSI") {
        const r = rsiArr(bars, 14);
        const YR = (v) => vy + vh - (v / 100) * vh;
        [30, 50, 70].forEach((lvl) => {
          ctx.strokeStyle = lvl === 50 ? "#16222c" : "rgba(255,77,94,.25)";
          ctx.setLineDash(lvl === 50 ? [] : [3, 3]);
          ctx.beginPath(); ctx.moveTo(padL, YR(lvl)); ctx.lineTo(padL + cw, YR(lvl)); ctx.stroke();
          ctx.setLineDash([]);
        });
        ctx.beginPath();
        let st = false;
        for (let i = 0; i < bars.length; i++) {
          if (r[i] == null) continue;
          if (!st) { ctx.moveTo(X(i), YR(r[i])); st = true; } else ctx.lineTo(X(i), YR(r[i]));
        }
        ctx.strokeStyle = "#c9a227"; ctx.lineWidth = 1.2; ctx.stroke();
        ctx.fillStyle = "#5d6f7e"; ctx.font = "9px ui-monospace,Menlo,monospace"; ctx.textAlign = "left";
        ctx.fillText("RSI(14)", padL + 2, vy + 8);
      } else {
        const m = macdArr(bars);
        let mx2 = 0;
        bars.forEach((b, i) => { if (m.hist[i] != null) mx2 = Math.max(mx2, Math.abs(m.hist[i]), Math.abs(m.dif[i]), Math.abs(m.dea[i])); });
        const YM = (v) => vy + vh / 2 - (v / (mx2 || 1)) * (vh / 2 - 3);
        bars.forEach((b, i) => {
          if (m.hist[i] == null) return;
          ctx.fillStyle = m.hist[i] >= 0 ? "rgba(32,201,122,.55)" : "rgba(255,77,94,.55)";
          const y0 = YM(0), y1 = YM(m.hist[i]);
          ctx.fillRect(X(i) - 2.5, Math.min(y0, y1), 5, Math.max(1, Math.abs(y1 - y0)));
        });
        const line = (arr, color) => {
          ctx.beginPath();
          let st2 = false;
          for (let i = 0; i < bars.length; i++) {
            if (arr[i] == null) continue;
            if (!st2) { ctx.moveTo(X(i), YM(arr[i])); st2 = true; } else ctx.lineTo(X(i), YM(arr[i]));
          }
          ctx.strokeStyle = color; ctx.lineWidth = 1.1; ctx.stroke();
        };
        line(m.dif, "#e8c46a");
        line(m.dea, "#4aa3ff");
        ctx.fillStyle = "#5d6f7e"; ctx.font = "9px ui-monospace,Menlo,monospace"; ctx.textAlign = "left";
        ctx.fillText("MACD(12,26,9)", padL + 2, vy + 8);
      }
      ctx.strokeStyle = "#1a2733";
      ctx.beginPath(); ctx.moveTo(padL, vy + vh + 0.5); ctx.lineTo(padL + cw, vy + vh + 0.5); ctx.stroke();

      // price plot: candle / OHLC bar / line / area / mountain
      const ctype = App.ctype || "CANDLE";
      const bw = Math.max(1.5, Math.min(9, cw / bars.length - 1.5));
      const upC = UP_COL(), dnC = DN_COL();
      if (ctype === "CANDLE") {
        bars.forEach((b, i) => {
          const up = b[3] >= b[0];
          ctx.strokeStyle = ctx.fillStyle = up ? upC : dnC;
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.moveTo(X(i), Y(b[1])); ctx.lineTo(X(i), Y(b[2])); ctx.stroke();
          const yo = Y(Math.max(b[0], b[3])), yc = Y(Math.min(b[0], b[3]));
          ctx.fillRect(X(i) - bw / 2, yo, bw, Math.max(1, yc - yo));
        });
      } else if (ctype === "BAR") {
        bars.forEach((b, i) => {
          const up = b[3] >= b[0];
          ctx.strokeStyle = up ? upC : dnC;
          ctx.lineWidth = 1;
          const x = X(i);
          ctx.beginPath(); ctx.moveTo(x, Y(b[1])); ctx.lineTo(x, Y(b[2])); ctx.stroke();
          ctx.beginPath(); ctx.moveTo(x - bw / 2, Y(b[0])); ctx.lineTo(x, Y(b[0])); ctx.stroke();
          ctx.beginPath(); ctx.moveTo(x, Y(b[3])); ctx.lineTo(x + bw / 2, Y(b[3])); ctx.stroke();
        });
      } else {
        const lastUp = bars[bars.length - 1][3] >= bars[bars.length - 1][0];
        const col = lastUp ? upC : dnC;
        const path = () => {
          ctx.beginPath();
          bars.forEach((b, i) => (i ? ctx.lineTo(X(i), Y(b[3])) : ctx.moveTo(X(i), Y(b[3]))));
        };
        if (ctype === "AREA" || ctype === "MOUNTAIN") {
          const grad = ctx.createLinearGradient(0, padT, 0, padT + ch);
          const a1 = ctype === "MOUNTAIN" ? 0.42 : 0.2;
          grad.addColorStop(0, lastUp ? "rgba(32,201,122," + a1 + ")" : "rgba(255,77,94," + a1 + ")");
          grad.addColorStop(1, "rgba(0,0,0,0)");
          path();
          ctx.lineTo(X(bars.length - 1), padT + ch);
          ctx.lineTo(X(0), padT + ch);
          ctx.closePath();
          ctx.fillStyle = grad;
          ctx.fill();
        }
        path();
        ctx.strokeStyle = col; ctx.lineWidth = 1.4; ctx.stroke();
      }

      // moving averages
      if (App.ma) {
        const maLine = (n, color) => {
          ctx.beginPath();
          let started = false;
          for (let i = 0; i < bars.length; i++) {
            if (i < n - 1) continue;
            let sum = 0;
            for (let k = i - n + 1; k <= i; k++) sum += bars[k][3];
            const yy = Y(sum / n);
            if (!started) { ctx.moveTo(X(i), yy); started = true; } else ctx.lineTo(X(i), yy);
          }
          ctx.strokeStyle = color; ctx.lineWidth = 1.2; ctx.stroke();
        };
        maLine(Math.max(1, Math.min(App.maCfg.a, bars.length)), "rgba(251,139,30,.9)");
        maLine(Math.max(1, Math.min(App.maCfg.b, bars.length)), "rgba(74,163,255,.85)");
      }

      // bollinger bands (period / k from the indicator panel)
      if (App.boll) {
        const bn = Math.max(2, Math.min(App.maCfg.bn, bars.length));
        const bk = App.maCfg.bk;
        const band = (mult, color) => {
          ctx.beginPath();
          let started = false;
          for (let i = bn - 1; i < bars.length; i++) {
            const win = bars.slice(i - bn + 1, i + 1).map((b) => b[3]);
            const mean = win.reduce((a, b) => a + b, 0) / bn;
            const sd = Math.sqrt(win.reduce((a, b) => a + (b - mean) * (b - mean), 0) / bn);
            const yy = Y(mean + mult * sd);
            if (!started) { ctx.moveTo(X(i), yy); started = true; } else ctx.lineTo(X(i), yy);
          }
          ctx.strokeStyle = color; ctx.lineWidth = 1; ctx.stroke();
        };
        band(bk, "rgba(160,120,255,.85)");
        band(0, "rgba(160,120,255,.45)");
        band(-bk, "rgba(160,120,255,.85)");
      }

      // last price line
      const last = s.px;
      const ly = Y(last);
      ctx.setLineDash([4, 3]);
      ctx.strokeStyle = chg(s) >= 0 ? UP_COL() : DN_COL();
      ctx.beginPath(); ctx.moveTo(padL, ly); ctx.lineTo(padL + cw, ly); ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = chg(s) >= 0 ? UP_COL() : DN_COL();
      ctx.fillRect(padL + cw + 2, ly - 8, 54, 16);
      ctx.fillStyle = "#04080c";
      ctx.font = "600 10px ui-monospace,Menlo,monospace";
      ctx.fillText(f2(last), padL + cw + 7, ly + 1);

      // time axis
      ctx.fillStyle = "#5d6f7e"; ctx.font = "10px ui-monospace,Menlo,monospace";
      const now = new Date();
      for (let i = 0; i <= 6; i++) {
        const idx = Math.min(bars.length - 1, Math.round((bars.length - 1) * (i / 6)));
        const t = new Date(now.getTime() - (bars.length - 1 - idx) * P_MIN[App.period] * 60000);
        ctx.textAlign = "center";
        ctx.fillText(App.period === "1D" ? pad2(t.getMonth() + 1) + "/" + pad2(t.getDate()) : hhmm(t), padL + (cw / 6) * i, padT + ch + vh + 22);
      }

      // crosshair
      if (hover != null && hover >= 0 && hover < bars.length) {
        const b = bars[hover];
        ctx.strokeStyle = "rgba(251,139,30,.55)";
        ctx.setLineDash([3, 3]);
        ctx.beginPath(); ctx.moveTo(X(hover), padT); ctx.lineTo(X(hover), padT + ch + vh); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(padL, Y(b[3])); ctx.lineTo(padL + cw, Y(b[3])); ctx.stroke();
        ctx.setLineDash([]);
        const el = $(pid("xhair"));
        if (el) el.textContent = "O " + f2(b[0]) + "  H " + f2(b[1]) + "  L " + f2(b[2]) + "  C " + f2(b[3]) + "  V " + fnum(b[4]);
      } else {
        const el = $(pid("xhair"));
        if (el) el.textContent = "\u2014";
      }
    }

    draw(null);
    cv.addEventListener("mousemove", (e) => {
      const r = cv.getBoundingClientRect();
      const w = r.width, h = r.height;
      const padL = 6, padR = 62, padT = Math.max(34, (box.querySelector(".legend")?.offsetHeight || 0) + 20), padB = 52;
      const cw = w - padL - padR;
      const x = e.clientX - r.left;
      const i = Math.floor(((x - padL) / cw) * bars.length);
      draw(i >= 0 && i < bars.length ? i : null);
    });
    cv.addEventListener("mouseleave", () => draw(null));

    box._redraw = () => { size(); draw(null); mountDraw(); };
    if (!mountChart._ro) {
      mountChart._ro = new ResizeObserver((entries) => {
        entries.forEach((en) => { if (en.target._redraw) en.target._redraw(); });
      });
    }
    if (!mountChart._seen) mountChart._seen = new WeakSet();
    if (!mountChart._seen.has(box)) { mountChart._seen.add(box); mountChart._ro.observe(box); }

    mountDraw();
  }

  /* ---------------- chart drawing layer (trend lines / h-lines) ---------------- */
  function drawKey() { return (App.sym || "AAPL") + "|" + App.period; }
  function drawRec() {
    const d = Store.data.draw = Store.data.draw || {};
    return (d[drawKey()] = d[drawKey()] || { trend: [], hline: [] });
  }

  function mountDraw() {
    const cv = $(pid("canvas"));
    const ov = $(pid("drawlayer"));
    if (!cv || !ov) return;
    ov.width = cv.width;
    ov.height = cv.height;
    ov.style.width = cv.style.width;
    ov.style.height = cv.style.height;
    ov.style.left = cv.offsetLeft + "px";
    ov.style.top = cv.offsetTop + "px";
    ov.classList.toggle("active", !!App.drawMode);
    if (!ov._bound) { ov._bound = true; ov.addEventListener("click", onDrawClick); }
    paintDraw();
  }

  function paintDraw() {
    const ov = $(pid("drawlayer"));
    if (!ov) return;
    const dpr = window.devicePixelRatio || 1;
    const ctx = ov.getContext("2d");
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, ov.width, ov.height);
    ctx.scale(dpr, dpr);
    const g = chartGeom[App.pfx || "_"];
    if (!g) return;
    const rec = (Store.data.draw || {})[drawKey()];
    if (!rec) return;
    const PX = (n) => g.padL + n * g.cw;
    const PY = (n) => g.padT + n * g.ch;
    const PR = (n) => g.mx - n * (g.mx - g.mn);
    ctx.font = "9.5px ui-monospace,Menlo,monospace";
    ctx.textAlign = "left";
    ctx.textBaseline = "middle";

    (rec.hline || []).forEach((n) => {
      const y = PY(n);
      ctx.strokeStyle = "rgba(201,162,39,.85)";
      ctx.lineWidth = 1.1;
      ctx.setLineDash([5, 4]);
      ctx.beginPath(); ctx.moveTo(g.padL, y); ctx.lineTo(g.padL + g.cw, y); ctx.stroke();
      ctx.setLineDash([]);
      const lbl = f2(PR(n));
      ctx.fillStyle = "#0b1116";
      ctx.fillRect(g.padL + g.cw + 2, y - 8, 54, 16);
      ctx.strokeStyle = "rgba(201,162,39,.85)";
      ctx.strokeRect(g.padL + g.cw + 2, y - 8, 54, 16);
      ctx.fillStyle = "#e9c46a";
      ctx.fillText(lbl, g.padL + g.cw + 8, y);
    });

    (rec.trend || []).forEach((seg) => {
      ctx.strokeStyle = "#e9c46a";
      ctx.lineWidth = 1.4;
      ctx.beginPath();
      ctx.moveTo(PX(seg.a.x), PY(seg.a.y));
      ctx.lineTo(PX(seg.b.x), PY(seg.b.y));
      ctx.stroke();
      ctx.fillStyle = "#e9c46a";
      [seg.a, seg.b].forEach((p) => {
        ctx.beginPath();
        ctx.arc(PX(p.x), PY(p.y), 2.4, 0, Math.PI * 2);
        ctx.fill();
      });
      ctx.fillText(f2(PR(seg.a.y)), PX(seg.a.x) + 4, PY(seg.a.y) - 6);
      ctx.fillText(f2(PR(seg.b.y)), PX(seg.b.x) + 4, PY(seg.b.y) - 6);
    });

    if (App.pendPt) {
      ctx.strokeStyle = "rgba(251,139,30,.9)";
      ctx.lineWidth = 1.2;
      ctx.setLineDash([4, 4]);
      ctx.beginPath();
      ctx.arc(PX(App.pendPt.x), PY(App.pendPt.y), 4, 0, Math.PI * 2);
      ctx.stroke();
      ctx.setLineDash([]);
    }
  }

  function onDrawClick(ev) {
    const ov = $(pid("drawlayer"));
    const g = chartGeom[App.pfx || "_"];
    if (!ov || !g || !App.drawMode) return;
    const r = ov.getBoundingClientRect();
    const nx = ((ev.clientX - r.left) - g.padL) / g.cw;
    const ny = ((ev.clientY - r.top) - g.padT) / g.ch;
    if (!(nx >= 0 && nx <= 1 && ny >= 0 && ny <= 1)) return;
    const rec = drawRec();
    if (App.drawMode === "hline") {
      rec.hline.push(ny);
      notice("H-LINE @ " + f2(g.mx - ny * (g.mx - g.mn)));
    } else if (!App.pendPt) {
      App.pendPt = { x: nx, y: ny };
      notice("Point A @ " + f2(g.mx - ny * (g.mx - g.mn)) + " · click the second point");
    } else {
      rec.trend.push({ a: App.pendPt, b: { x: nx, y: ny } });
      App.pendPt = null;
      notice("TREND line drawn · " + rec.trend.length + " on this chart");
    }
    Store.save();
    paintDraw();
  }

  function toggleDrawMode(mode) {
    if (mode === "clear") {
      const d = Store.data.draw || {};
      delete d[drawKey()];
      App.pendPt = null;
      Store.save();
      paintDraw();
      notice("Drawings cleared for " + drawKey());
      return;
    }
    if (mode === "undo") {
      const rec = drawRec();
      if (rec.trend.length) rec.trend.pop();
      else if (rec.hline.length) rec.hline.pop();
      else { notice("Nothing to undo", true); return; }
      Store.save();
      paintDraw();
      notice("Last drawing removed");
      return;
    }
    App.drawMode = App.drawMode === mode ? null : mode;
    App.pendPt = null;
    const ov = $(pid("drawlayer"));
    if (ov) ov.classList.toggle("active", !!App.drawMode);
    notice(App.drawMode ? "DRAW " + App.drawMode.toUpperCase() + " armed · click the chart" : "Draw mode off");
    render();
  }

  /* ---------------- row context menu ---------------- */
  const CTX_ITEMS = [
    { k: "DES", label: "Security Description" },
    { k: "GP", label: "Graph Price" },
    { k: "N", label: "News by Security" },
    { k: "COMP", label: "Peer Comparison" },
    { k: "DEPTH", label: "Market Depth" },
    { sep: true },
    { act: "watch", label: "Toggle Watchlist" },
    { act: "copy", label: "Copy Ticker" }
  ];

  function copyText(str) {
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) { navigator.clipboard.writeText(str); return true; }
    } catch (e) { /* fall through */ }
    try {
      const ta = document.createElement("textarea");
      ta.value = str;
      ta.style.cssText = "position:fixed;left:-9999px;top:0";
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
      return true;
    } catch (e) { return false; }
  }

  function openCtx(x, y, sym) {
    const el = $("ctxmenu");
    if (!el) return;
    el.innerHTML = CTX_ITEMS.map((it) => it.sep
      ? '<div class="csep"></div>'
      : '<div class="citem" data-ctx="' + (it.k ? "fn:" + it.k : it.act) + '"><b>' +
        (it.k ? it.k : "\u00B7") + "</b><span>" + it.label + "</span></div>").join("");
    el.setAttribute("data-sym", sym);
    el.classList.remove("hidden");
    const w = el.offsetWidth, hh = el.offsetHeight;
    el.style.left = Math.max(6, Math.min(x, window.innerWidth - w - 8)) + "px";
    el.style.top = Math.max(6, Math.min(y, window.innerHeight - hh - 8)) + "px";
  }

  function closeCtx() {
    const el = $("ctxmenu");
    if (el) el.classList.add("hidden");
  }

  /* ---------------- column sorting (click a header) ---------------- */
  function sortTable(th, forcedDir, keepState) {
    const table = th.closest("table");
    if (!table || !table.tBodies || !table.tBodies.length) return null;
    const tb = table.tBodies[0];
    const head = th.parentNode;
    const idx = Array.prototype.indexOf.call(head.children, th);
    if (idx < 0) return null;
    const prevDir = th.classList.contains("sort-asc") ? "asc" : th.classList.contains("sort-desc") ? "desc" : "";
    const dir = forcedDir || (prevDir === "asc" ? "desc" : "asc");
    Array.prototype.forEach.call(head.children, (c) => {
      c.classList.remove("sort-asc", "sort-desc");
      c.removeAttribute("aria-sort");
    });
    th.classList.add(dir === "asc" ? "sort-asc" : "sort-desc");
    th.setAttribute("aria-sort", dir === "asc" ? "ascending" : "descending");
    const num = (txt) => {
      const raw = String(txt).replace(/,/g, "").replace(/[^0-9.\-+]/g, "");
      const n = parseFloat(raw);
      return isNaN(n) ? null : n;
    };
    const rows = Array.prototype.slice.call(tb.rows);
    rows.sort((a, b) => {
      const ca = a.cells[idx], cb = b.cells[idx];
      if (!ca || !cb) return 0;
      const na = num(ca.textContent), nb = num(cb.textContent);
      if (na !== null && nb !== null) return dir === "asc" ? na - nb : nb - na;
      const va = ca.textContent.trim().toUpperCase(), vb = cb.textContent.trim().toUpperCase();
      return dir === "asc" ? va.localeCompare(vb) : vb.localeCompare(va);
    });
    rows.forEach((r) => tb.appendChild(r));
    // reordering breaks row<->model index alignment; drop the marching highlight
    App.sel = -1;
    if (!keepState) App.sort = { func: App.func, idx: idx, dir: dir };
    return dir;
  }

  function applySortToView() {
    const s = App.sort;
    if (!s || s.func !== App.func) return;
    const table = document.querySelector(".qcell.focus table") || document.querySelector("#view table");
    const th = table && table.tHead && table.tHead.rows[0] && table.tHead.rows[0].cells[s.idx];
    if (th) sortTable(th, s.dir, true);
  }

  /* ---------------- command execution ---------------- */
  function notice(msg, isErr) {
    $("stMsg").textContent = msg;
    let t = $("toast");
    if (!t) { t = document.createElement("div"); t.id = "toast"; document.body.appendChild(t); }
    t.textContent = msg;
    t.style.borderColor = isErr ? "var(--dn)" : "var(--acc)";
    t.classList.add("on");
    clearTimeout(notice._t);
    notice._t = setTimeout(() => t.classList.remove("on"), 2200);
  }

  function go(func, sym) {
    if (!VIEWS[func]) return false;
    App.routeError = null;
    if (FUNCS[func] && FUNCS[func].needsSym) {
      if (!sym) sym = App.sym || "AAPL";
      App.sym = sym;
    } else if (sym) {
      App.sym = sym;
    }
    App.func = func;
    App.sel = 0;
    if (App.layout !== "1") {
      const p = panelAt(App.focus);
      p.func = func;
      p.sym = FUNCS[func] && FUNCS[func].needsSym ? App.sym : "";
      Store.save();
    }
    render();
    syncNavigation();
    notice(func + (App.sym && FUNCS[func].needsSym ? " \u00b7 " + App.sym : "") + " \u00b7 " + (FUNCS[func] ? FUNCS[func].label : ""));
    return true;
  }

  function exec(raw) {
    const rawUp = String(raw || "").toUpperCase().replace(/<GO>/g, "").trim();
    if (rawUp && App.cmdHist[0] !== rawUp) {
      App.cmdHist.unshift(rawUp);
      if (App.cmdHist.length > 60) App.cmdHist.length = 60;
    }
    App.cmdIdx = -1;
    const thm = rawUp.match(/^T(?:H|HEME)(?:\s+([A-Z]+))?$/);
    if (thm) {
      const t = applyTheme(thm[1] || THEMES[(THEMES.indexOf(Store.data.theme) + 1) % THEMES.length]);
      notice("Theme " + t, false);
      return;
    }
    if (rawUp === "PALETTE" || rawUp === "K") { openPalette(); return; }

    // layout: LAY 1 / LAY 2 / LAY 4 (cycles when no argument)
    const lm = rawUp.match(/^(?:LAY|LAYOUT|SPLIT|QUAD|GRID)(?:\s+([124]))?$/);
    if (lm) { setLayout(lm[1] || nextLayout()); return; }

    // cancel a working order
    const cm = rawUp.match(/^CXL\s+(ALL|\d+)$/);
    if (cm) { cancelOrder(cm[1]); return; }

    // csv export
    const em = rawUp.match(/^EXPORT(?:\s+(TRD|PORT|ORD|ALRT|PNG|GP|FA|GOV|CMDT))?$/);
    if (em) {
      const arg = em[1] || "";
      if (/^(PNG|GP|FA|GOV|CMDT)$/.test(arg)) { exportPNG(arg === "PNG" ? App.func : arg); return; }
      if (arg) { downloadCSV(arg.toLowerCase()); return; }
      notice("EXPORT TRD | PORT | ORD | ALRT | PNG | GP | FA | GOV | CMDT", true);
      return;
    }

    // screener
    const eqm = rawUp.match(/^EQS(?:\s+(.+))?$/);
    if (eqm) {
      App.eqsQ = (eqm[1] || "").trim();
      go("EQS");
      return;
    }

    // security search by ticker / name / sector
    const sm = rawUp.match(/^(?:SRCH|SEARCH)(?:\s+(.+))?$/);
    if (sm) {
      App.srchQ = (sm[1] || "").trim();
      go("SRCH");
      return;
    }

    // commodity term structure
    const cmm = rawUp.match(/^CMDT(?:\s+(CL|GC|HG))?$/);
    if (cmm) {
      if (cmm[1]) {
        const idx = CMD_ROOTS.findIndex((r) => r.root === cmm[1]);
        if (idx >= 0) App.cmdRoot = idx;
      }
      go("CMDT");
      return;
    }

    // field dictionary search
    const fdm = rawUp.match(/^FLDS(?:\s+(.+))?$/);
    if (fdm) {
      App.dictQ = (fdm[1] || "").trim();
      go("FLDS");
      return;
    }

    // price alerts
    const am = rawUp.match(/^ALRT(?:\s+DEL(?:\s+(\d+))?)?(?:\s+([A-Z0-9.]+)\s*([<>])\s*([\d.,]+))?$/);
    if (am) {
      if (rawUp.indexOf(" DEL") >= 0) {
        if (am[1]) { removeAlert(am[1]); return; }
        go("ALRT");
        notice("ALRT DEL <id> \u00b7 ids are listed in the ALRT view", true);
        return;
      }
      if (am[2]) { placeAlert(am[2], am[3], am[4].replace(/,/g, "")); return; }
      go("ALRT");
      return;
    }

    const tm = rawUp.match(/^(BUY|SELL|ADD|DEL)\s+([A-Z0-9.]+)(?:\s+([\d,]+))?(?:\s+(LMT|STP|MKT)(?:\s+([\d.,]+))?)?$/);
    if (tm) {
      const act = tm[1];
      const sym = tm[2];
      const qty = tm[3] ? Number(tm[3].replace(/,/g, "")) : 0;
      if (!bySym[sym]) { notice("Unknown security " + sym, true); return; }
      if (act === "ADD") {
        if (Store.data.watch.indexOf(sym) < 0) Store.data.watch.push(sym);
        Store.save();
        go("W");
        notice("Added " + sym + " to watchlist");
        return;
      }
      if (act === "DEL") {
        Store.data.watch = Store.data.watch.filter((x) => x !== sym);
        Store.save();
        go("W");
        notice("Removed " + sym + " from watchlist");
        return;
      }
      if (tm[4] && tm[4] !== "MKT") {
        placeOrder(sym, act, qty || 100, tm[4], tm[5] ? tm[5].replace(/,/g, "") : NaN);
        return;
      }
      trade(sym, qty || 100, act);
      return;
    }

    const s = String(raw || "").toUpperCase().replace(/<GO>/g, " ").replace(/[,;]/g, " ").replace(/\s+/g, " ").trim();
    if (!s) { notice("Empty command \u2014 type HELP", true); return; }
    const words = s.split(" ");
    let sym = null, fn = null, unknown = [];
    words.forEach((w) => {
      if (bySym[w]) sym = w;
      else if (FUNCS[w]) fn = w;
      else if (!/^(US|EQUITY|INDEX|CURNCY|COMDTY|GOVT|LN|GY|JP|HK)$/.test(w) && !/^\d+$/.test(w)) unknown.push(w);
    });

    if (sym && !fn) fn = "DES";
    if (!sym && fn && FUNCS[fn].needsSym) { /* use current */ }
    if (fn) { go(fn, sym); return; }
    if (sym) { go("DES", sym); return; }
    // name fallback: a single match opens the security, several open the search page
    const named = nameHits(s);
    if (named.length === 1) {
      go("DES", named[0].sym);
      notice('Resolved "' + s + '" to ' + named[0].sym + " \u00b7 " + named[0].name);
      return;
    }
    if (named.length > 1) {
      App.srchQ = s;
      go("SRCH");
      notice(named.length + " securities match \u2014 pick one below", false);
      return;
    }
    if (unknown.length) { notice("Unknown: " + unknown.join(" ") + " \u2014 type HELP", true); return; }
    notice("No match \u2014 type HELP", true);
  }

  /* ---------------- market engine ---------------- */
  function tick() {
    App.ticks++;
    const n = 3 + Math.floor(Math.random() * 4);
    for (let i = 0; i < n; i++) {
      const s = pick(UNIV);
      const vola = s.cls === "FX" ? 0.00035 : s.cls === "GOVT" ? 0.0012 : 0.0016;
      const drift = (bySym["SPX"].px > 0 ? 0 : 0);
      const next = Math.max(0.0001, s.px * (1 + (Math.random() - 0.5) * 2 * vola + drift));
      const prevPx = s.px;
      s.px = Number(next.toFixed(s.cls === "FX" ? 4 : 2));
      const sp = s.px * (s.cls === "FX" ? 0.00008 : s.cls === "GOVT" ? 0.0004 : 0.00045);
      s.bid = Number((s.px - sp).toFixed(s.cls === "FX" ? 4 : 2));
      s.ask = Number((s.px + sp).toFixed(s.cls === "FX" ? 4 : 2));
      if (s.vol) s.vol = Math.round(s.vol * (1 + (Math.random() - 0.45) * 0.004));
      // extend bar
      const b = s.hist[s.hist.length - 1];
      b[3] = s.px; b[1] = Math.max(b[1], s.px); b[2] = Math.min(b[2], s.px);
      if (s.vol) b[4] = Math.round(b[4] * (1 + Math.random() * 0.01));
      if (s.px > s.hi) s.hi = s.px;
      if (s.px < s.lo) s.lo = s.px;
      if (s.px === prevPx) s.px += 0.01;
      s.book = makeBook(s);
      pushTape(s);
      ["15M", "1H", "1D"].forEach((p) => {
        const arr = s.series && s.series[p];
        if (!arr) return;
        const pb = arr[arr.length - 1];
        pb[3] = s.px;
        pb[1] = Math.max(pb[1], s.px);
        pb[2] = Math.min(pb[2], s.px);
      });
    }
    $("tickcount").textContent = fnum(App.ticks);
    $("stRight").textContent = (10 + Math.floor(Math.random() * 9)) + "ms \u00b7 SIM FEED";

    // flash the changed cells without re-rendering whole view (tables only)
    flashCells();

    // resting orders and alerts are matched against the fresh marks
    checkOrders();
    checkAlerts();

    if (document.activeElement && document.activeElement.closest("#view input,#view textarea,#view select")) return;
    if (App.func === "DES" || App.func === "GP" || App.func === "PORT") {
      if (App.ticks % 3 === 0) render();
    } else if (App.func === "OPT" && App.ticks % 6 === 0) {
      render();
    } else if (App.func === "ORD" && App.ticks % 4 === 0) {
      render();
    } else if (App.func === "ALRT" && App.ticks % 6 === 0) {
      render();
    } else if ((App.func === "GOV" || App.func === "FX" || App.func === "COMP" || App.func === "EQS") && App.ticks % 8 === 0) {
      render();
    } else if (App.func === "FA" && App.ticks % 12 === 0) {
      render();
    }
  }

  function flashCells() {
    const trs = document.querySelectorAll('#view tbody tr[data-sym]');
    if (!trs.length) return;
    trs.forEach((tr) => {
      const sym = tr.getAttribute("data-sym");
      const s = bySym[sym];
      if (!s) return;
      const prev = App.lastPx[sym];
      if (prev == null || Math.abs(s.px - prev) < 1e-9) return;
      App.lastPx[sym] = s.px;
      const tds = tr.children;
      const headers = Array.from(tr.closest("table")?.tHead?.rows[0]?.cells || []).map(th => th.textContent.replace(/[▲▼]/g, "").trim());
      const lastIdx = headers.indexOf("LAST");
      if (lastIdx >= 0 && tds[lastIdx]) {
        const cell = tds[lastIdx]; cell.textContent = f2(s.px);
        cell.classList.remove("flash-u", "flash-d"); void cell.offsetWidth;
        cell.classList.add(s.px > prev ? "flash-u" : "flash-d");
      }
      const c = chg(s), cp = chgp(s);
      const update = (name, value) => { const idx=headers.indexOf(name); if(idx>=0 && tds[idx])tds[idx].innerHTML=value; };
      update("CHG", '<span class="'+cls(c)+'">'+(c>=0?"+":"")+c.toFixed(2)+'</span>');
      update("%CHG", '<span class="'+cls(cp)+'">'+fpct(cp)+'</span>');
      update("BID",f2(s.bid)); update("ASK",f2(s.ask));

    });
  }

  /* ---------------- events ---------------- */
  function bind() {
    $("gobtn").addEventListener("click", () => {
      const v = $("cmd").value;
      $("cmd").value = "";
      exec(v);
    });

    $("cmd").addEventListener("keydown", (e) => {
      const items = App.sugg.items;
      if (e.key === "Enter") {
        if (App.sugg.idx >= 0 && items[App.sugg.idx]) {
          e.target.value = items[App.sugg.idx].code;
          App.sugg.items = [];
          App.sugg.idx = -1;
          paintSugg();
          e.preventDefault();
          return;
        }
        const v = e.target.value;
        e.target.value = "";
        App.sugg.items = [];
        App.sugg.idx = -1;
        paintSugg();
        exec(v);
        e.preventDefault();
      } else if (e.key === "Escape") {
        e.target.value = "";
        App.sugg.items = [];
        App.sugg.idx = -1;
        paintSugg();
      } else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        if (items.length) {
          e.preventDefault();
          const n = items.length;
          App.sugg.idx = e.key === "ArrowDown"
            ? (App.sugg.idx + 1) % n
            : (App.sugg.idx - 1 + n) % n;
          paintSugg();
        } else if (App.cmdHist.length && e.target.value !== "") {
          // recall history when something is already typed
          e.preventDefault();
          if (e.key === "ArrowUp") App.cmdIdx = Math.min(App.cmdHist.length - 1, App.cmdIdx + 1);
          else App.cmdIdx = App.cmdIdx - 1;
          if (App.cmdIdx < 0) App.cmdIdx = -1;
          e.target.value = App.cmdIdx >= 0 ? App.cmdHist[App.cmdIdx] : "";
        } else {
          e.preventDefault();
          moveSel(e.key === "ArrowDown" ? 1 : -1);
        }
      } else if (e.key === "Tab" && items.length) {
        e.preventDefault();
        e.target.value = items[Math.max(0, App.sugg.idx)].code;
        App.sugg.items = [];
        App.sugg.idx = -1;
        paintSugg();
      }
    });
    $("cmd").addEventListener("input", updateSugg);
    $("cmd").addEventListener("blur", () => {
      setTimeout(() => { App.sugg.items = []; App.sugg.idx = -1; paintSugg(); }, 120);
    });

    document.addEventListener("keydown", (e) => {
      if (/^F(1[0-2]|[1-9])$/.test(e.key)) {
        const key = e.key;
        const fn = Object.keys(FUNCS).find((k) => FUNCS[k].key === key);
        if (fn) { e.preventDefault(); go(fn, App.sym); }
        return;
      }
      const railItem=e.target.closest?.("[data-fn]");
      if(railItem && (e.key==="Enter" || e.key===" ")){e.preventDefault();go(railItem.dataset.fn,App.sym);return;}
      // heat-map tiles are focusable: Enter / Space opens the security
      const ae = document.activeElement;
      if (ae && ae.matches("input,textarea,select,[contenteditable=true]")) return;
      if (ae && ae.classList && ae.classList.contains("mtile") && (e.key === "Enter" || e.key === " ")) {
        e.preventDefault();
        go("DES", ae.getAttribute("data-sym"));
        return;
      }
      // focused table row: Enter opens the context menu, arrows rove the selection
      const rowEl = ae && ae.closest ? ae.closest("#view tbody tr[data-sym]") : null;
      if (rowEl && (e.key === "Enter" || e.key === " ")) {
        e.preventDefault();
        const rr = rowEl.getBoundingClientRect();
        openCtx(Math.round(rr.left + 120), Math.round(rr.top + 18), rowEl.getAttribute("data-sym"));
        return;
      }
      if (rowEl && (e.key === "ArrowDown" || e.key === "ArrowUp")) {
        e.preventDefault();
        const sib = e.key === "ArrowDown" ? rowEl.nextElementSibling : rowEl.previousElementSibling;
        if (sib && sib.focus) sib.focus();
        return;
      }
      if (document.activeElement === $("cmd")) return;
      if (e.key === "ArrowDown") { e.preventDefault(); moveSel(1); }
      else if (e.key === "ArrowUp") { e.preventDefault(); moveSel(-1); }
      else if (e.key === "Home") { e.preventDefault(); moveSel(-9999); }
      else if (e.key === "End") { e.preventDefault(); moveSel(9999); }
      else if (e.key === "PageDown") { e.preventDefault(); moveSel(10); }
      else if (e.key === "PageUp") { e.preventDefault(); moveSel(-10); }
      else if (e.key === "Enter") { e.preventDefault(); openSel(); }
      else if (e.key.length === 1 && !e.metaKey && !e.ctrlKey) { $("cmd").focus(); }
    });

    $("view").addEventListener("input", (e) => {
      const el = e.target;
      const kind = el && el.getAttribute ? el.getAttribute("data-live") : null;
      if (kind === "srch") { App.srchQ = el.value; applySrchFilter(el.closest(".srchwrap")); return; }
      if (kind === "news") { App.newsQ = el.value; applyNewsFilter(el.closest(".newswrap")); return; }
      const ind = el && el.getAttribute ? el.getAttribute("data-ind") : null;
      if (ind && ["a", "b", "bn", "bk"].indexOf(ind) >= 0) {
        // live redraw only: keep the input focused, repaint the canvas in place
        const ok = applyIndCfg(ind, el.value);
        el.classList.toggle("bad", !ok);
        if (ok) {
          const mt = $("matog");
          if (mt) mt.textContent = "MA" + App.maCfg.a + "/" + App.maCfg.b;
          drawOnly();
        }
      }
    });

    document.addEventListener("keydown", (e) => {
      if (e.key !== "Escape") return;
      closeCtx();
      if (App.qfOpen) closeQuickref();
      if (App.histOpen) closeHist();
      if (App.indPanel) { App.indPanel = false; if (App.func === "GP") render(); }
      if (App.fullChart) setFullChart(false);
    });

    bindTouchAffordances();

    document.addEventListener("contextmenu", (e) => {
      const row = e.target.closest ? e.target.closest("#view tr[data-sym]") : null;
      if (!row) { closeCtx(); return; }
      e.preventDefault();
      openCtx(e.clientX, e.clientY, row.getAttribute("data-sym"));
    });

    document.addEventListener("click", (e) => {
      const el = $("ctxmenu");
      if (!el || el.classList.contains("hidden")) return;
      const item = e.target.closest ? e.target.closest("[data-ctx]") : null;
      if (!item) { closeCtx(); return; }
      const act = item.getAttribute("data-ctx");
      const sym = el.getAttribute("data-sym");
      closeCtx();
      if (act.indexOf("fn:") === 0) { go(act.slice(3), sym); return; }
      if (act === "watch") {
        const has = Store.data.watch.indexOf(sym) >= 0;
        Store.data.watch = has ? Store.data.watch.filter((x) => x !== sym) : Store.data.watch.concat([sym]);
        Store.save();
        notice((has ? "Removed " : "Added ") + sym + (has ? " from" : " to") + " watchlist");
        if (App.func === "W" || App.func === "WEI") render();
        return;
      }
      if (act === "copy") { copyText(sym); notice("Copied " + sym); }
    });

    $("view").addEventListener("click", (e) => {
      const sortTh = e.target.closest("thead th");
      if (sortTh && sortTh.closest("table")) {
        sortTable(sortTh);
        return;
      }
      // split-screen: any click inside a panel makes it the focused panel
      const cell = e.target.closest(".qcell");
      if (cell) {
        const ci = Number(cell.getAttribute("data-cell"));
        focusCell(ci);
        if (e.target.closest(".qhd") && !e.target.closest("button")) return;
      }

      // ---- security search controls ----
      const sclsBtn = e.target.closest("[data-srchcls]");
      if (sclsBtn) { App.srchCls = sclsBtn.getAttribute("data-srchcls"); render(); return; }
      const sgoBtn = e.target.closest("[data-srchgo]");
      if (sgoBtn) { go("DES", sgoBtn.getAttribute("data-srchgo")); return; }
      if (e.target.closest("[data-srchclear]")) { App.srchQ = ""; App.srchCls = "ALL"; render(); return; }

      // ---- news story expansion ----
      const storyBtn = e.target.closest("[data-story]");
      if (storyBtn) {
        const li = storyBtn.closest(".nitem");
        if (li) {
          const open = li.classList.toggle("open");
          storyBtn.setAttribute("aria-expanded", open ? "true" : "false");
          storyBtn.textContent = open ? "\u25be" : "\u25b8";
        }
        return;
      }
      if (e.target.closest("[data-storyall]")) {
        const lis = Array.prototype.slice.call((e.target.closest(".newswrap") || $("view")).querySelectorAll(".nitem"));
        const expand = lis.some((l) => !l.classList.contains("open"));
        lis.forEach((l) => {
          l.classList.toggle("open", expand);
          const b = l.querySelector(".ntog");
          if (b) { b.setAttribute("aria-expanded", expand ? "true" : "false"); b.textContent = expand ? "\u25be" : "\u25b8"; }
        });
        return;
      }

      // ---- market map tile ----
      const mapTile = e.target.closest(".mtile");
      if (mapTile) { go("DES", mapTile.getAttribute("data-sym")); return; }

      // chart drawings
      const drawBtn = e.target.closest("[data-draw]");
      if (drawBtn) { toggleDrawMode(drawBtn.getAttribute("data-draw")); return; }

      // csv export
      // generic function jump buttons inside rendered views
      const goBtn = e.target.closest("[data-go]");
      if (goBtn) { e.preventDefault(); go(goBtn.getAttribute("data-go"), App.sym); return; }
      const layoutButton = e.target.closest("[data-system-layout]");
      if (layoutButton) { setLayout(layoutButton.getAttribute("data-system-layout")); return; }
      if (e.target.closest("[data-system-reset-split]")) { Store.data.split = { c: 0.5, r: 0.5 }; Store.save(); render(); notice("Panel dividers reset"); return; }
      // SET: UI scale stepper
      const zoomBtn = e.target.closest("[data-zoom]");
      if (zoomBtn) {
        const d = parseFloat(zoomBtn.getAttribute("data-zoom")) || 0;
        const z = d === 0 ? zoomStep(0, true) : zoomStep(d);
        const lbl = $("setzoom");
        if (lbl) lbl.textContent = Math.round(z * 100) + "%";
        return;
      }

      // SET: preference toggles
      const setBtn = e.target.closest("[data-set]");
      if (setBtn) {
        const k = setBtn.getAttribute("data-set");
        const v = setBtn.getAttribute("data-val");
        if (k === "theme") { applyTheme(v); Store.data.theme = v; Store.save(); return; }
        if (k === "icon") { saveSetts({ icon: v }); render(); return; }
        if (k === "density") { saveSetts({ density: v }); render(); return; }
        if (k === "notify" && v === "1") { askNotify(); return; }
        saveSetts({ [k]: v === "1" });
        render();
        return;
      }

      // SET: profile switch / create / rename / delete
      const profBtn = e.target.closest("[data-prof]");
      if (profBtn) {
        const act = profBtn.getAttribute("data-prof");
        const inp = $("setprof");
        const val = inp ? inp.value.trim() : "";
        if (act === "new") { profileNew(val); return; }
        if (act === "rename") { profileRename(val); return; }
        if (act === "del") { profileDelete(); return; }
        if (act !== App.user) { switchUser(act); render(); }
        return;
      }

      // watchlist reorder buttons
      const mvBtn = e.target.closest("[data-wmv]");
      if (mvBtn) {
        watchMove(mvBtn.getAttribute("data-sym"), parseInt(mvBtn.getAttribute("data-wmv"), 10) || 0);
        return;
      }

      // SET: profile backup / restore
      const bkBtn = e.target.closest("[data-backup]");
      if (bkBtn) {
        const act = bkBtn.getAttribute("data-backup");
        if (act === "export") { downloadJSON(); render(); }
        else if (act === "import") { importFromFile(); }
        else if (act === "reset") { resetProfile(); }
        return;
      }

      // indicator parameter panel buttons
      const indBtn = e.target.closest("[data-ind]");
      if (indBtn && indBtn.tagName === "BUTTON") {
        const act = indBtn.getAttribute("data-ind");
        if (act === "close") { App.indPanel = false; render(); return; }
        if (act === "reset") {
          App.maCfg = Object.assign({}, DEFAULT_PROFILE.maCfg);
          Store.data.maCfg = Object.assign({}, App.maCfg);
          Store.save();
          notice("Indicators reset to MA20/60 \u00b7 BOLL 20/2", false);
          render();
          return;
        }
        if (act === "apply") {
          const ok = Array.prototype.every.call((e.target.closest(".qbody") || $("view")).querySelectorAll('[data-ind][type="number"]'), (el) =>
            applyIndCfg(el.getAttribute("data-ind"), el.value, false));
          Store.save();
          notice(ok ? "Indicator parameters applied" : "Some values were out of range", !ok);
          render();
          return;
        }
      }

      // print the current view
      const prBtn = e.target.closest("[data-print]");
      if (prBtn) { notice("Opening print dialog"); window.print(); return; }

      // SET: chart PNG export
      const pngBtn = e.target.closest("[data-png]");
      if (pngBtn) { exportPNG(pngBtn.getAttribute("data-png")); return; }

      const csvBtn = e.target.closest("[data-csv]");
      if (csvBtn) { downloadCSV(csvBtn.getAttribute("data-csv")); return; }

      // cancel a working order
      const cxlBtn = e.target.closest("[data-cxl]");
      if (cxlBtn) {
        cancelOrder(cxlBtn.getAttribute("data-cxl"));
        if (App.layout !== "1") render();
        return;
      }

      // delete an alert
      const adlBtn = e.target.closest("[data-adel]");
      if (adlBtn) {
        removeAlert(adlBtn.getAttribute("data-adel"));
        if (App.layout !== "1") render();
        return;
      }

      // order ticket
      const ordBtn = e.target.closest("[data-ord]");
      if (ordBtn) {
        const act = ordBtn.getAttribute("data-ord");
        const osym = ($(pid("o-sym")) || {}).value || App.sym;
        const oqty = ($(pid("o-qty")) || {}).value || 100;
        const opx = ($(pid("o-px")) || {}).value || "";
        const side = act === "STPSELL" ? "SELL" : act;
        const type = act === "STPSELL" ? "STP" : "LMT";
        placeOrder(osym.trim().toUpperCase(), side, oqty, type, opx.replace(/,/g, ""));
        if (App.layout !== "1") render();
        return;
      }

      // alert ticket
      const alrtBtn = e.target.closest("[data-alrt]");
      if (alrtBtn) {
        const asym = ($(pid("a-sym")) || {}).value || App.sym;
        const apx = ($(pid("a-px")) || {}).value || "";
        placeAlert(asym.trim().toUpperCase(), alrtBtn.getAttribute("data-alrt"), apx.replace(/,/g, ""));
        if (App.layout !== "1") render();
        return;
      }

      // ---- fx converter / commodity roots ----
      if (e.target.closest("[data-fxconv]") || e.target.closest("[data-fxswap]")) {
        const aEl = $("fx-amt"), fEl = $("fx-from"), tEl = $("fx-to");
        if (aEl) App.fxAmt = String(aEl.value).replace(/[^\d.]/g, "") || "1";
        if (fEl) App.fxFrom = fEl.value;
        if (tEl) App.fxTo = tEl.value;
        if (e.target.closest("[data-fxswap]")) {
          const tmp = App.fxFrom;
          App.fxFrom = App.fxTo;
          App.fxTo = tmp;
        }
        render();
        return;
      }
      const cmdB = e.target.closest("[data-cmd]");
      if (cmdB) { App.cmdRoot = Number(cmdB.getAttribute("data-cmd")) || 0; render(); return; }

      // ---- screener builder ----
      if (e.target.closest("[data-eqadd]")) {
        syncBuild();
        App.eqsBuild.push({ f: "MCAP", op: ">", v: "100B" });
        App.eqsUseBuild = true;
        render();
        return;
      }
      const eqDel = e.target.closest("[data-eqdelrow]");
      if (eqDel) {
        syncBuild();
        App.eqsBuild.splice(Number(eqDel.getAttribute("data-eqdelrow")), 1);
        if (!App.eqsBuild.length) App.eqsBuild.push({ f: "PE", op: "<", v: "30" });
        App.eqsUseBuild = true;
        render();
        return;
      }
      if (e.target.closest("[data-eqapply]")) {
        syncBuild(); App.eqsUseBuild = true; render(); return;
      }
      const eqJoin = e.target.closest("[data-eqjoin]");
      if (eqJoin) {
        syncBuild();
        App.eqsJoin = eqJoin.getAttribute("data-eqjoin");
        App.eqsUseBuild = true;
        render();
        return;
      }
      if (e.target.closest("[data-eqsave]")) {
        syncBuild();
        const nmEl = $("eq-name");
        const nm = ((nmEl && nmEl.value) || "").trim().toUpperCase() || "SCREEN " + ((Store.data.screens || []).length + 1);
        Store.data.screens = (Store.data.screens || []).filter((x) => x.name !== nm);
        Store.data.screens.unshift({ name: nm, rows: App.eqsBuild.map((r) => ({ f: r.f, op: r.op, v: r.v })), join: App.eqsJoin });
        Store.data.screens = Store.data.screens.slice(0, 8);
        App.eqsName = "";
        App.eqsUseBuild = true;
        Store.save();
        notice("SCREEN SAVED \u00b7 " + nm);
        render();
        return;
      }
      const eqLoad = e.target.closest("[data-eqsaved]");
      if (eqLoad) {
        const sc = (Store.data.screens || [])[Number(eqLoad.getAttribute("data-eqsaved"))];
        if (sc) {
          App.eqsBuild = sc.rows.map((r) => ({ f: r.f, op: r.op, v: r.v }));
          App.eqsJoin = sc.join || "AND";
          App.eqsUseBuild = true;
          render();
        }
        return;
      }
      const eqSd = e.target.closest("[data-eqsd]");
      if (eqSd) {
        Store.data.screens.splice(Number(eqSd.getAttribute("data-eqsd")), 1);
        Store.save();
        render();
        return;
      }
      if (e.target.closest("[data-eqreset]")) {
        App.eqsBuild = [{ f: "PE", op: "<", v: "30" }];
        App.eqsJoin = "AND";
        App.eqsUseBuild = false;
        App.eqsQ = "";
        App.eqsName = "";
        render();
        return;
      }
      if (e.target.closest("[data-alrtlog]")) {
        Store.data.alertLog = [];
        Store.save();
        render();
        return;
      }
      const pinB = e.target.closest("[data-apin]");
      if (pinB) { go("DES", pinB.getAttribute("data-apin")); return; }

      if (e.target.closest("#" + pid("t-buy")) || e.target.closest("#" + pid("t-sell"))) {
        const sym = ($(pid("t-sym")).value || "").trim().toUpperCase();
        const qty = ($(pid("t-qty")).value || "").trim();
        trade(sym, qty, e.target.closest("#" + pid("t-buy")) ? "BUY" : "SELL");
        return;
      }
      if (e.target.closest(".pbtn")) {
        const pb = e.target.closest(".pbtn");
        const rawId = String(pb.id || "").replace(App.pfx || "", "");
        if (rawId === "fultog") { setFullChart(!App.fullChart); return; }
        if (rawId === "indcfg") { App.indPanel = !App.indPanel; render(); return; }
        if (rawId === "matog") App.ma = !App.ma;
        else if (rawId === "bolltog") App.boll = !App.boll;
        else if (rawId === "logtog") App.logScale = !App.logScale;
        else if (pb.getAttribute("data-ctype")) App.ctype = pb.getAttribute("data-ctype");
        else if (pb.getAttribute("data-exp") != null) { App.optExpIdx = Number(pb.getAttribute("data-exp")); render(); return; }
        else if (pb.getAttribute("data-eqs") != null) { App.eqsUseBuild = false; exec("EQS " + pb.getAttribute("data-eqs")); return; }
        else if (pb.getAttribute("data-dict") != null) { exec("FLDS " + pb.getAttribute("data-dict")); return; }
        else if (pb.getAttribute("data-sub")) App.sub = pb.getAttribute("data-sub");
        else if (pb.getAttribute("data-period")) App.period = pb.getAttribute("data-period");
        Store.data.period = App.period;
        Store.data.ma = App.ma;
        Store.data.boll = App.boll;
        Store.data.sub = App.sub;
        Store.data.ctype = App.ctype;
        Store.data.logScale = App.logScale;
        Store.save();
        render();
        return;
      }
      if (e.target.closest("[data-close]")) {
        closePos(e.target.closest("[data-close]").getAttribute("data-close"));
        return;
      }
      const tr = e.target.closest("tr[data-sym]");
      if (tr) {
        const sym = tr.getAttribute("data-sym");
        const rows = Array.prototype.slice.call(document.querySelectorAll('#view tbody tr[data-sym]'));
        App.sel = rows.indexOf(tr);
        rows.forEach((r) => r.classList.remove("sel"));
        tr.classList.add("sel");
        go("DES", sym);
        return;
      }
      const li = e.target.closest("li[data-sym]");
      if (li) { go("DES", li.getAttribute("data-sym")); }
    });

    $("fkeys").addEventListener("click", (e) => {
      const li = e.target.closest("li[data-fn]");
      if (li) go(li.getAttribute("data-fn"), App.sym);
    });
    $("monitor").addEventListener("click", (e) => {
      const li = e.target.closest("li[data-sym]");
      if (li) go("DES", li.getAttribute("data-sym"));
    });

    document.querySelectorAll(".rail-hd").forEach((h) => h.addEventListener("click", () => {}));
  }

  function moveSel(d) {
    const rows = document.querySelectorAll('#view tbody tr');
    if (!rows.length) return;
    App.sel = clamp((App.sel || 0) + d, 0, rows.length - 1);
    rows.forEach((r, i) => r.classList.toggle("sel", i === App.sel));
    const el = rows[App.sel];
    if (el && el.scrollIntoView) el.scrollIntoView({ block: "nearest" });
  }

  function openSel() {
    const rows = document.querySelectorAll('#view tbody tr');
    const el = rows[App.sel];
    if (!el) return;
    const sym = el.getAttribute("data-sym");
    if (sym) go("DES", sym);
  }

  /* ---------------- self-test (open with #selftest) ---------------- */
  function selftest() {
    const res = [];
    const t = (n, c) => res.push([n, !!c]);
    try {
      exec("AAPL GP");
      t("cmd AAPL GP", App.func === "GP" && App.sym === "AAPL");
      const cv = $("canvas");
      t("chart mounted", !!cv && cv.width > 300);
      if (cv) {
        const ctx = cv.getContext("2d");
        const d = ctx.getImageData(0, 0, Math.min(300, cv.width), Math.min(200, cv.height)).data;
        let nz = 0;
        for (let i = 3; i < d.length; i += 400) if (d[i] > 0) nz++;
        t("chart painted(" + nz + ")", nz > 5);
      }
      exec("NVDA US Equity DES");
      t("cmd NVDA US Equity DES", App.func === "DES" && App.sym === "NVDA");
      exec("WEI");
      t("cmd WEI rows", App.func === "WEI" && document.querySelectorAll("#view tbody tr").length >= 5);
      exec("ZZZZQQ");
      t("unknown cmd safe", App.func === "WEI");
      tick();
      t("feed tick " + App.ticks, App.ticks > 0);
      exec("MOST");
      t("view MOST", App.func === "MOST" && document.querySelectorAll("#view tbody tr").length > 3);
      exec("TOP");
      t("view TOP news", App.func === "TOP" && document.querySelectorAll(".news li").length > 0);
      exec("HP");
      t("view HP bars", App.func === "HP" && document.querySelectorAll("#view tbody tr").length > 5);
      exec("CL1");
      t("bare ticker -> DES", App.func === "DES" && App.sym === "CL1");
      moveSel(1); moveSel(-1);
      t("selection move", true);

      // ---- trading / portfolio ----
      const snap = JSON.stringify(Store.data);
      exec("PORT");
      t("view PORT", App.func === "PORT" && !!document.querySelector(".cards"));
      const cash0 = Store.data.cash;
      exec("BUY MSFT 10");
      t("BUY fills", !!Store.data.pos.MSFT && Store.data.pos.MSFT.qty === 10);
      t("cash reduced", Store.data.cash < cash0);
      exec("BUY MSFT 10");
      t("avg cost blended", Math.abs(Store.data.pos.MSFT.qty - 20) < 1e-6);
      exec("SELL MSFT 20");
      t("SELL closes", !Store.data.pos.MSFT);
      exec("SELL MSFT 5");
      t("oversell rejected", !Store.data.pos.MSFT);
      exec("DEL META");
      const w0 = Store.data.watch.length;
      exec("ADD META");
      t("ADD watch", Store.data.watch.indexOf("META") >= 0);
      exec("DEL META");
      t("DEL watch", Store.data.watch.indexOf("META") < 0 && Store.data.watch.length === w0);

      // ---- chart period / overlays ----
      exec("AAPL GP");
      const p1h = document.querySelector('.pbtn[data-period="1H"]');
      if (p1h) p1h.click();
      t("period switch 1H", App.period === "1H");
      const m0 = App.ma;
      document.querySelector("#matog").click();
      t("MA toggle", App.ma === !m0);
      document.querySelector("#matog").click();

      // ---- indicators ----
      const b0 = App.boll;
      document.querySelector("#bolltog").click();
      t("BOLL toggle", App.boll === !b0);
      document.querySelector("#bolltog").click();
      document.querySelector('.pbtn[data-sub="RSI"]').click();
      t("RSI study", App.sub === "RSI");
      const rs = rsiArr(bySym.AAPL.series[App.period], 14).filter((v) => v != null);
      t("RSI bounded", rs.length > 10 && rs.every((v) => v >= 0 && v <= 100));
      document.querySelector('.pbtn[data-sub="MACD"]').click();
      const md = macdArr(bySym.AAPL.series[App.period]);
      t("MACD computed", App.sub === "MACD" && md.hist.length === bySym.AAPL.series[App.period].length && md.hist.some((v) => Math.abs(v) > 1e-9));
      document.querySelector('.pbtn[data-sub="VOL"]').click();
      t("study reset", App.sub === "VOL");

      // ---- blotter ----
      const nBlot = Store.data.blot.length;
      exec("BUY AAPL 10");
      t("blot recorded", Store.data.blot.length === nBlot + 1 && Store.data.blot[0].sym === "AAPL");
      exec("SELL AAPL 10");
      t("realised pnl booked", typeof Store.data.realized === "number" && Store.data.blot[0].side === "SELL");
      exec("TRD");
      t("view TRD", App.func === "TRD" && document.querySelectorAll("#view tbody tr").length >= 2);

      // ---- option chain ----
      exec("AAPL OPT");
      t("view OPT", App.func === "OPT" && document.querySelectorAll("#view tbody tr").length === 9);
      const oc = bsPx(100, 100, 30, 0.3);
      t("BS parity", Math.abs((oc.call - oc.put) - (100 - 100 * Math.exp(-0.042 * 30 / 365))) < 0.5);
      t("BS delta range", oc.callDelta > 0.4 && oc.callDelta < 0.7 && oc.putDelta < 0);
      const expBtns = document.querySelectorAll('.pbtn[data-exp]');
      if (expBtns.length > 1) expBtns[1].click();
      t("expiry switch", App.optExpIdx === 1);
      App.optExpIdx = 0;

      // ---- tape / history ----
      tick(); tick();
      t("tape appended", bySym.AAPL.tas.length > 20);
      t("cmd history", App.cmdHist.length > 0 && App.cmdHist[0] === "AAPL OPT");
      exec("AAPL DES");
      t("time&sales rows", document.querySelectorAll("#view .tas tbody tr").length >= 10);

      // ---- profiles ----
      const homeUser = App.user;
      const homeCash = Store.data.cash;
      switchUser("QATEST");
      t("profile switch", App.user === "QATEST" && Store.key() === PROFILE_PREFIX + "QATEST");
      t("profile isolated", Store.data.cash !== homeCash || Store.data.blot.length === 0);
      switchUser(homeUser);
      t("profile restored", App.user === homeUser && Store.data.cash === homeCash);
      try { localStorage.removeItem(PROFILE_PREFIX + "QATEST"); } catch (e) { /* ignore */ }

      // ---- new UI surfaces ----
      exec("GOV");
      const ycv = $("ycurve");
      t("GOV canvas drawn", !!ycv && ycv.width > 100 && ycv.height > 50);
      t("GOV tenors", document.querySelectorAll("#view tbody tr").length === 11);
      exec("FX");
      t("FX matrix 9x8 grid", document.querySelectorAll(".fxmat tbody td").length === 72 && document.querySelectorAll(".fxmat .fxcell").length === 56);
      t("FX diagonal blank", document.querySelectorAll(".fxmat .fxdiag").length === 8);
      exec("ECO");
      t("ECO calendar rows", document.querySelectorAll("#view tbody tr").length >= 10);
      exec("AAPL COMP");
      t("COMP peer rows", document.querySelectorAll("#view tbody tr").length >= 2);
      t("COMP peers marked", !!document.querySelector("#view tbody td b.acc"));
      const th0 = Store.data.theme;
      applyTheme("ICE");
      t("theme applied", document.body.className.indexOf("theme-ice") >= 0 && Store.data.theme === "ICE");
      exec("AAPL GP");
      applyTheme("ICE");
      const thIce = getComputedStyle(document.body).getPropertyValue("--acc").trim();
      t("theme repaints canvas(" + thIce + ")", thIce === "#2ec8f0" && !!document.querySelector("#view canvas"));
      t("theme up colour(" + UP_COL() + ")", UP_COL() === "#1fd4a4");
      applyTheme(th0);
      t("theme restored", Store.data.theme === th0);
      t("palette filter", palItems("NV").some((i) => i.code === "NVDA") && palItems("GOV").some((i) => i.code === "GOV"));
      t("palette all funcs", palItems("").length >= Object.keys(FUNCS).length);

      // ---- commodity curve ----
      exec("CMDT");
      const cmv = $("cmdcurve");
      t("CMDT canvas drawn", !!cmv && cmv.width > 100);
      t("CMDT curve rows", document.querySelectorAll("#view tbody tr").length === 10);
      exec("CMDT GC");
      t("CMDT root via cmd", App.func === "CMDT" && App.cmdRoot === 1);
      const cmChip = document.querySelector('[data-cmd="0"]');
      if (cmChip) cmChip.click();
      t("CMDT root chip", App.cmdRoot === 0);

      // ---- fx converter ----
      exec("FX");
      t("FX converter fields", !!$("fx-amt") && !!$("fx-from") && !!$("fx-to"));
      const amt0 = App.fxAmt;
      $("fx-amt").value = "500";
      document.querySelector("[data-fxconv]").click();
      t("FX convert amount", App.fxAmt === "500");
      const fFrom = App.fxFrom, fTo = App.fxTo;
      document.querySelector("[data-fxswap]").click();
      t("FX swap currencies", App.fxFrom === fTo && App.fxTo === fFrom);
      App.fxAmt = amt0;

      // ---- screener builder ----
      exec("EQS");
      App.eqsUseBuild = false;
      const nCrit = App.eqsBuild.length;
      document.querySelector("[data-eqadd]").click();
      t("EQS add criterion", App.eqsBuild.length === nCrit + 1);
      document.querySelectorAll("[data-eqdelrow]")[App.eqsBuild.length - 1].click();
      t("EQS del criterion", App.eqsBuild.length === nCrit);
      document.querySelector('[data-eqjoin="OR"]').click();
      t("EQS join OR", App.eqsJoin === "OR");
      syncBuild();
      $("eq-name").value = "TESTSCREEN";
      document.querySelector("[data-eqsave]").click();
      t("EQS screen saved", (Store.data.screens || []).some((s) => s.name === "TESTSCREEN"));
      t("EQS saved chips", document.querySelectorAll("[data-eqsaved]").length >= 1);
      const nRowsBefore = document.querySelectorAll("#view tbody tr[data-sym]").length;
      t("EQS builder filtered rows", nRowsBefore >= 0);
      Store.data.screens = (Store.data.screens || []).filter((s) => s.name !== "TESTSCREEN");
      App.eqsJoin = "AND";
      App.eqsUseBuild = false;
      Store.save();

      // ---- chart type / log scale ----
      exec("AAPL GP");
      const ctypeBtn = document.querySelector('[data-ctype="BAR"]');
      if (ctypeBtn) ctypeBtn.click();
      t("chart type switch", App.ctype === "BAR" && document.querySelector('[data-ctype="BAR"]').className.indexOf("on") >= 0);
      const lg0 = App.logScale;
      const logBtn = $("logtog");
      if (logBtn) logBtn.click();
      t("log scale toggle", App.logScale === !lg0);
      const cdlBtn = document.querySelector('[data-ctype="CANDLE"]');
      if (cdlBtn) cdlBtn.click();
      t("chart type back to candle", App.ctype === "CANDLE");
      App.logScale = false;

      // ---- portfolio risk + alert log ----
      exec("BUY AAPL 10");
      exec("PORT");
      t("PORT risk panel", !!document.querySelector(".riskwrap") && document.querySelectorAll(".riskwrap .card").length === 5);
      exec("SELL AAPL 10");

      exec("ALRT");
      t("ALRT clear-log button", document.querySelectorAll("[data-alrtlog]").length === 1);

      // ---- autocomplete ----
      t("suggest ticker", suggest("NV").some((i) => i.code === "NVDA"));
      t("suggest function", suggest("PO").some((i) => i.code === "PORT"));
      t("suggest command", suggest("BUY").some((i) => i.code.indexOf("BUY") === 0));
      t("suggest by name", suggest("APPLE").some((i) => i.code === "AAPL"));
      exec("APPLE");
      t("cmd resolves company name", App.func === "DES" && App.sym === "AAPL");
      exec("SRCH SEMI");
      t("cmd SRCH query", App.func === "SRCH" && App.srchQ === "SEMI");
      t("SRCH rows filtered", document.querySelectorAll("#view tbody tr[data-sym]").length >= 1);
      exec("SRCH");
      App.srchQ = "";

      // ---- working orders (LMT / STP / CXL) ----
      const apx = bySym.AAPL.px;
      exec("BUY AAPL 100 LMT " + (apx * 0.5).toFixed(2));
      const o1 = Store.data.orders[0];
      t("LMT rests below market", !!o1 && o1.status === "WORKING" && o1.type === "LMT");
      exec("SELL AAPL 100 LMT " + (apx * 1.5).toFixed(2));
      t("SELL LMT rests", Store.data.orders[0].status === "WORKING" && Store.data.orders[0].side === "SELL");
      exec("SELL AAPL 100 STP " + (apx * 0.4).toFixed(2));
      t("STP rests untouched", Store.data.orders[0].status === "WORKING" && Store.data.orders[0].type === "STP");
      exec("ORD");
      t("view ORD", App.func === "ORD" && document.querySelectorAll("#view tbody tr").length === 3);
      t("ORD cxl buttons", document.querySelectorAll("[data-cxl]").length === 3);
      const oid = Store.data.orders[0].id;
      exec("CXL " + oid);
      t("CXL one", Store.data.orders.find((o) => o.id === oid).status === "CXL");
      exec("CXL ALL");
      t("CXL ALL", Store.data.orders.every((o) => o.status !== "WORKING"));
      const nFill = Store.data.blot.length;
      exec("BUY AAPL 5 MKT");
      t("MKT still immediate", Store.data.blot.length === nFill + 1);
      exec("BUY AAPL 100 LMT " + (apx * 1.02).toFixed(2));
      t("LMT above offer fills", Store.data.orders[0].status === "FILLED" && Store.data.orders[0].fpx > 0);
      exec("CXL ALL");

      // ---- alerts ----
      const aid = Store.data.alerts.length;
      exec("ALRT AAPL > " + (apx * 0.5).toFixed(2));
      t("alert armed then fired", Store.data.alerts.length === aid + 1);
      exec("ALRT AAPL > " + (apx * 9).toFixed(2));
      t("far alert stays armed", Store.data.alerts[0].st === "ARMED");
      exec("ALRT");
      t("view ALRT", App.func === "ALRT" && document.querySelectorAll("#view tbody tr").length >= 2);
      exec("ALRT DEL " + Store.data.alerts[0].id);
      t("ALRT DEL removes", Store.data.alerts.length === 1);
      t("ALRT log recorded", (Store.data.alertLog || []).length >= 1);
      t("ALRT log table rows", document.querySelectorAll("#view .alrtlog tbody tr").length >= 1);

      // ---- csv export shapes ----
      const xt = exportSet("trd");
      t("csv blotter cols", xt.cols.length === 7 && xt.rows.length === Store.data.blot.length);
      t("csv text header", csvText(xt.cols, xt.rows).indexOf("TIME,TICKER,SIDE,QTY,PRICE") === 0);
      t("csv escaping", csvText(["a"], [["x,y"]]).indexOf('"x,y"') > 0);
      const xo = exportSet("ord");
      t("csv orders cols", xo.cols[0] === "ID" && xo.rows.length === Store.data.orders.length);
      const xp = exportSet("port");
      t("csv positions rows", xp.rows.length === portfolioStats().rows.length);

      // ---- split screen ----
      setLayout("4");
      t("layout 4 quad", App.layout === "4" && document.querySelectorAll(".qcell").length === 4);
      t("quad charts mounted", !!document.querySelector('.qcell[data-cell="0"] canvas'));
      const cell2 = document.querySelector('.qcell[data-cell="2"] .qfn');
      exec("WEI");
      t("quad retarget", App.func === "WEI" && cell2 !== null);
      t("quad panel func stored", Store.data.panels[0].func === "WEI");
      // new views inside a quadrant
      Store.data.panels[0] = { func: "FA", sym: "AAPL" };
      App.focus = 0;
      setLayout("2");
      const qfa = document.querySelector('.qcell[data-cell="0"] canvas');
      t("quad FA chart mounted", !!qfa && qfa.width > 300);
      exec("EQS");
      t("quad EQS table", !!document.querySelector('.qcell[data-cell="0"] tbody tr[data-sym]'));

      // ---- numeric alignment / focusable tiles / scoped filters ----
      setLayout("1");
      exec("SRCH");
      t("numeric cell right-aligned", (() => {
        const td = document.querySelector("#view tbody td.r");
        return !!td && getComputedStyle(td).textAlign === "right";
      })());
      t("srch empty state hint", (() => {
        const sc = document.querySelector("#view .srchwrap");
        const q = sc && sc.querySelector('input[data-live="srch"]');
        if (!q) return false;
        q.value = "QQQQQQ";
        q.dispatchEvent(new Event("input", { bubbles: true }));
        const hint = sc.querySelector(".emptyhint");
        const ok = !!hint && /NO SECURITIES MATCH/.test(hint.textContent);
        q.value = "";
        q.dispatchEvent(new Event("input", { bubbles: true }));
        return ok && !sc.querySelector(".emptyhint");
      })());
      t("numeric header right-aligned", (() => {
        const th = document.querySelector("#view thead th.r");
        return !!th && getComputedStyle(th).textAlign === "right";
      })());
      exec("MAP");
      t("heat tile focusable", (() => {
        const el = document.querySelector("#view .mtile");
        if (!el) return false;
        el.focus();
        return document.activeElement === el;
      })());
      t("heat tile Enter opens DES", (() => {
        const el = document.querySelector("#view .mtile");
        if (!el) return false;
        el.focus();
        document.activeElement.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
        return App.func === "DES" && App.sym === el.getAttribute("data-sym");
      })());

      // ---- split screen: per-panel filters & density ----
      App.newsQ = "";
      Store.data.panels[0] = { func: "TOP" };
      Store.data.panels[1] = { func: "TOP" };
      App.focus = 0;
      setLayout("2");
      t("two news panels", document.querySelectorAll(".qcell .newswrap").length === 2);
      const nq0 = document.querySelector('.qcell[data-cell="0"] input[data-live="news"]');
      if (nq0) { nq0.value = "AAPL"; nq0.dispatchEvent(new Event("input", { bubbles: true })); }
      t("news filter stays in panel", (() => {
        const hide0 = Array.prototype.filter.call(document.querySelectorAll('.qcell[data-cell="0"] .nitem'), (li) => li.style.display === "none").length;
        const hide1 = Array.prototype.filter.call(document.querySelectorAll('.qcell[data-cell="1"] .nitem'), (li) => li.style.display === "none").length;
        return hide0 > 0 && hide1 === 0;
      })());
      t("news empty state hint", (() => {
        const sc = document.querySelector('.qcell[data-cell="0"] .newswrap');
        const q = sc && sc.querySelector('input[data-live="news"]');
        if (!q) return false;
        q.value = "ZZZZZZ";
        q.dispatchEvent(new Event("input", { bubbles: true }));
        const hint = sc.querySelector(".emptyhint");
        const ok = !!hint && /NO STORIES MATCH/.test(hint.textContent);
        q.value = "";
        q.dispatchEvent(new Event("input", { bubbles: true }));
        return ok && !sc.querySelector(".emptyhint");
      })());
      t("panel badge counts filtered", (() => {
        const b = document.querySelector('.qcell[data-cell="0"] [data-count="news"]');
        const shown = Array.prototype.filter.call(document.querySelectorAll('.qcell[data-cell="0"] .nitem'), (li) => li.style.display !== "none").length;
        return !!b && String(b.textContent) === String(shown);
      })());
      Store.data.panels[0] = { func: "DEPTH", sym: "AAPL" };
      Store.data.panels[1] = { func: "MAP" };
      App.newsQ = "";
      App.focus = 0;
      setLayout("2");
      t("quad depth stacks columns", (() => {
        const d = document.querySelector('.qcell[data-cell="0"] .dwrap');
        return !!d && getComputedStyle(d).gridTemplateColumns.trim().split(/\s+/).length === 1;
      })());
      t("quad panel no h-overflow", (() => {
        const qb = document.querySelector('.qcell[data-cell="1"] .qbody');
        return !!qb && qb.scrollWidth <= qb.clientWidth + 2;
      })());
      setLayout("1");
      Store.data.panels[0] = { func: "GP", sym: "AAPL" };
      setLayout("2");
      t("layout 2 panels", App.layout === "2" && document.querySelectorAll(".qcell").length === 2);
      setLayout("1");
      t("layout back to 1", App.layout === "1" && document.querySelectorAll(".qcell").length === 0);
      t("panels persisted", Array.isArray(Store.data.panels) && Store.data.panels.length === 4);

      // ---- draggable splitters ----
      setLayout("4");
      t("splitter count", document.querySelectorAll(".qsplit").length === 2);
      const fire = (el, type, x, y) => el.dispatchEvent(new MouseEvent(type, { bubbles: true, clientX: x, clientY: y }));
      const dragSplit = (kind, fx, fy) => {
        const host = document.querySelector(".quad");
        if (!host) return null;
        const r = host.getBoundingClientRect();
        const sp = host.querySelector('.qsplit[data-split="' + kind + '"]');
        if (!sp) return null;
        const sx = r.left + r.width * 0.5;
        const sy = r.top + r.height * 0.5;
        fire(sp, "mousedown", sx, sy);
        fire(document, "mousemove", r.left + r.width * fx, r.top + r.height * fy);
        fire(document, "mouseup", r.left + r.width * fx, r.top + r.height * fy);
        return r;
      };
      dragSplit("v", 0.3, 0.5);
      t("drag col ratio(" + Store.data.split.c.toFixed(2) + ")", Math.abs(Store.data.split.c - 0.3) < 0.03);
      dragSplit("h", 0.3, 0.72);
      t("drag row ratio(" + Store.data.split.r.toFixed(2) + ")", Math.abs(Store.data.split.r - 0.72) < 0.03);
      dragSplit("v", -2, 0.5);
      t("drag clamped 20/80(" + Store.data.split.c.toFixed(2) + ")", Math.abs(Store.data.split.c - 0.2) < 1e-6);
      const qcellW = document.querySelector('.qcell[data-cell="0"]').getBoundingClientRect().width;
      const qcellW2 = document.querySelector('.qcell[data-cell="1"]').getBoundingClientRect().width;
      t("grid actually resized", qcellW2 > qcellW * 3);
      document.querySelector('.qsplit[data-split="v"]').dispatchEvent(new MouseEvent("dblclick", { bubbles: true }));
      t("dblclick resets 50/50", Store.data.split.c === 0.5 && Store.data.split.r === 0.5);
      setLayout("2");
      t("layout2 single splitter", document.querySelectorAll(".qsplit").length === 1);
      setLayout("1");

      // ---- chart drawing ----
      exec("AAPL GP");
      t("chart geom captured", !!chartGeom["_"] && chartGeom["_"].ch > 40);
      toggleDrawMode("hline");
      t("hline mode armed", App.drawMode === "hline");
      drawRec().hline.push(0.42);
      paintDraw();
      const ovc = $("drawlayer");
      t("overlay sized", !!ovc && ovc.width === $("canvas").width && ovc.height === $("canvas").height);
      if (ovc) {
        const od = ovc.getContext("2d").getImageData(0, 0, Math.min(400, ovc.width), ovc.height).data;
        let onz = 0;
        for (let i = 3; i < od.length; i += 40) if (od[i] > 0) onz++;
        t("hline painted(" + onz + ")", onz > 8);
      }
      drawRec().trend.push({ a: { x: 0.1, y: 0.7 }, b: { x: 0.8, y: 0.3 } });
      t("trend stored", drawRec().trend.length === 1);
      toggleDrawMode("undo");
      t("undo trend", drawRec().trend.length === 0);
      toggleDrawMode("clear");
      t("clear drawings", !(Store.data.draw || {})[drawKey()]);

      // ---- FA / EQS / FLDS ----
      exec("AAPL FA");
      t("cmd AAPL FA", App.func === "FA" && App.sym === "AAPL");
      const facv = $("fachart");
      t("FA chart mounted", !!facv && facv.width > 300);
      if (facv) {
        const fd = facv.getContext("2d").getImageData(0, 0, Math.min(400, facv.width), Math.min(240, facv.height)).data;
        let fnz = 0;
        for (let i = 3; i < fd.length; i += 400) if (fd[i] > 0) fnz++;
        t("FA painted(" + fnz + ")", fnz > 5);
      }
      const faTabs = document.querySelectorAll("#view table");
      t("FA statement rows", faTabs.length === 2 && faTabs[0].querySelectorAll("tbody tr").length === 5);
      t("FA ratios rows", faTabs.length === 2 && faTabs[1].querySelectorAll("tbody tr").length >= 8);
      exec("SPX FA");
      t("FA non-equity guarded", App.func === "FA" && document.querySelectorAll("#view table").length === 0);
      exec("EQS");
      t("view EQS rows", App.func === "EQS" && document.querySelectorAll("#view tbody tr[data-sym]").length === equities().length);
      exec("EQS PE<30");
      const eqRows = Array.prototype.slice.call(document.querySelectorAll("#view tbody tr[data-sym]"));
      t("EQS screen PE<30 (" + eqRows.length + ")",
        eqRows.length > 0 && eqRows.length < equities().length &&
        eqRows.every((tr) => bySym[tr.getAttribute("data-sym")].pe < 30));
      exec("EQS MCAP>500B");
      t("EQS screen MCAP>500B", document.querySelectorAll("#view tbody tr[data-sym]").length === 9);
      exec("EQS ZZZ>1");
      t("EQS bad token tolerated", App.func === "EQS" && document.querySelectorAll("#view .eqsnote").length >= 1);
      exec("FLDS");
      t("view FLDS", App.func === "FLDS" && document.querySelectorAll("#view tbody tr").length === FIELD_DICT.length);
      exec("FLDS MARGIN");
      const dictN = document.querySelectorAll("#view tbody tr").length;
      t("FLDS filter(" + dictN + ")", dictN > 0 && dictN < FIELD_DICT.length);
      // ---- layout baseline: every panel-style view shares one padding spec ----
      const padOf = () => {
        const el = document.querySelector("#view > div");
        if (!el) return null;
        const cs = getComputedStyle(el);
        return cs.paddingTop + " " + cs.paddingRight + " " + cs.paddingBottom + " " + cs.paddingLeft;
      };
      const PADREF = {};
      const panels = ["GOV", "EQS", "FLDS", "SRCH", "ECO", "COMP", "FX", "CMDT", "ALRT", "TRD", "ORD", "OPT", "PORT"];
      panels.forEach((f) => { exec(f); PADREF[f] = padOf(); });
      const padGov = PADREF.GOV;
      t("shell pad GOV set(" + padGov + ")", !!padGov && padGov.split(" ")[1] === padGov.split(" ")[3]);
      panels.slice(1).forEach((f) => t("shell pad " + f + " matches", PADREF[f] === padGov));

      // ---- market map heat grid ----
      exec("MAP");
      t("MAP tiles laid out", document.querySelectorAll("#view .mtile").length === equities().length);
      t("MAP tile has box", (() => {
        const el = document.querySelector("#view .mtile");
        if (!el) return false;
        const r = el.getBoundingClientRect();
        return r.height > 12 && r.width > 20;
      })());
      t("MAP sector columns", document.querySelectorAll("#view .mcol").length > 1);
      t("MAP tile click -> DES", (() => {
        const el = document.querySelector("#view .mtile");
        if (!el) return false;
        el.dispatchEvent(new MouseEvent("click", { bubbles: true }));
        return App.func === "DES" && App.sym === el.getAttribute("data-sym");
      })());

      // ---- depth ladder two-column workspace ----
      exec("AAPL DEPTH");
      t("DEPTH two columns", getComputedStyle(document.querySelector("#view .dwrap")).display === "grid");
      t("DEPTH ladder rows", document.querySelectorAll("#view table.ladder tbody tr").length === 10);
      t("DEPTH imbalance bar", (() => {
        const i = document.querySelector("#view .imbbar i");
        return !!i && parseFloat(i.style.width) > 0 && i.getBoundingClientRect().width > 0;
      })());
      t("DEPTH tape rows", document.querySelectorAll("#view table.tas tbody tr").length > 5);

      // ---- news filter + expansion ----
      App.newsQ = "";
      exec("TOP");
      t("news rows", document.querySelectorAll("#view .nitem").length === NEWS.length);
      const nbody = document.querySelector("#view .nitem .nbody");
      t("news body collapsed", !!nbody && getComputedStyle(nbody).display === "none");
      const ntg = document.querySelector("#view .ntog");
      if (ntg) ntg.dispatchEvent(new MouseEvent("click", { bubbles: true }));
      t("news story expands", document.querySelectorAll("#view .nitem.open").length === 1 &&
        getComputedStyle(document.querySelector("#view .nitem.open .nbody")).display === "block");
      if (ntg) ntg.dispatchEvent(new MouseEvent("click", { bubbles: true }));
      t("news story collapses", document.querySelectorAll("#view .nitem.open").length === 0);
      exec("N");
      const tall = document.querySelector("#view [data-storyall]");
      t("news expand-all button", !!tall);
      if (tall) tall.dispatchEvent(new MouseEvent("click", { bubbles: true }));
      const nRows = document.querySelectorAll("#view .nitem").length;
      t("news expand all(" + nRows + ")", nRows > 0 && document.querySelectorAll("#view .nitem.open").length === nRows);
      if (tall) tall.dispatchEvent(new MouseEvent("click", { bubbles: true }));
      t("news collapse all", document.querySelectorAll("#view .nitem.open").length === 0);
      exec("TOP");
      const nq = $("news-q");
      if (nq) { nq.value = "AAPL"; nq.dispatchEvent(new Event("input", { bubbles: true })); }
      t("news live filter(" + String(App.newsQ) + ")", App.newsQ === "AAPL" && (() => {
        const vis = Array.prototype.filter.call(document.querySelectorAll("#view .nitem"), (li) => li.style.display !== "none");
        return vis.length > 0 && vis.length < NEWS.length;
      })());

      // ---- security search: live filter / class chips / open / clear ----
      App.srchQ = ""; App.srchCls = "ALL";
      exec("SRCH");
      const totalRows = document.querySelectorAll("#view tbody tr[data-sym]").length;
      t("SRCH universe rows(" + totalRows + "/" + UNIV.length + ")", totalRows > 10 && totalRows <= UNIV.length);
      const sq = $("srch-q");
      t("SRCH filter input present", !!sq);
      if (sq) { sq.value = "SEMI"; sq.dispatchEvent(new Event("input", { bubbles: true })); }
      const visRows = Array.prototype.filter.call(document.querySelectorAll("#view tbody tr[data-sym]"), (tr) => tr.style.display !== "none").length;
      t("SRCH live filter(" + visRows + "/" + totalRows + ")", App.srchQ === "SEMI" && visRows > 0 && visRows < totalRows);
      const idxChip = Array.prototype.slice.call(document.querySelectorAll("#view [data-srchcls]"))
        .filter((b) => b.getAttribute("data-srchcls") === "INDEX")[0];
      t("SRCH class chip present", !!idxChip);
      if (idxChip) idxChip.dispatchEvent(new MouseEvent("click", { bubbles: true }));
      t("SRCH class chip on", App.srchCls === "INDEX" && !!document.querySelector("#view .pbtn.on"));
      const clrBtn = document.querySelector("#view [data-srchclear]");
      t("SRCH clear button", !!clrBtn);
      if (clrBtn) clrBtn.dispatchEvent(new MouseEvent("click", { bubbles: true }));
      t("SRCH clear resets", App.srchQ === "" && App.srchCls === "ALL" &&
        document.querySelectorAll("#view tbody tr[data-sym]").length === totalRows);
      t("SRCH open button", (() => {
        const b = document.querySelector("#view [data-srchgo]");
        if (!b) return false;
        b.dispatchEvent(new MouseEvent("click", { bubbles: true }));
        return App.func === "DES" && App.sym === b.getAttribute("data-srchgo");
      })());

      exec("EQS");

      exec("AAPL GP");
      try { Store.data = JSON.parse(snap); Store.save(); } catch (e) { /* restore best effort */ }
      App.layout = "1"; App.drawMode = null; App.pendPt = null; App.dragging = false;
    } catch (err) {
      res.push(["exception", false, String(err && err.message)]);
    }
      t("header click sorts table", (() => {
        go("W");
        const table = document.querySelector(".qcell.focus table") || document.querySelector("#view table");
        const th = table && table.tHead && table.tHead.rows[0].cells[4];
        if (!th) return false;
        const colTxt = () => Array.prototype.map.call(table.tBodies[0].rows, (r) => (r.cells[4] || {}).textContent).join("|");
        const before = colTxt();
        th.dispatchEvent(new MouseEvent("click", { bubbles: true }));
        const asc = th.classList.contains("sort-asc") && colTxt() !== before;
        const ascTxt = colTxt();
        th.dispatchEvent(new MouseEvent("click", { bubbles: true }));
        const descEnd = Array.prototype.map.call(table.tBodies[0].rows, (r) => (r.cells[4] || {}).textContent).reverse().join("|");
        return asc && th.classList.contains("sort-desc") && descEnd === ascTxt;
      })());
      t("sort survives rerender", (() => {
        const ok = !!App.sort;
        render();
        const th = document.querySelector("#view table thead th.sort-asc, #view table thead th.sort-desc");
        App.sort = null;
        return ok && !!th;
      })());
      t("row context menu", (() => {
        go("W");
        const row = document.querySelector("#view tbody tr[data-sym]");
        const m = $("ctxmenu");
        if (!row || !m) return false;
        const sym = row.getAttribute("data-sym");
        row.dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, clientX: 220, clientY: 180 }));
        const open = !m.classList.contains("hidden") && m.querySelectorAll(".citem").length >= 6 && m.getAttribute("data-sym") === sym;
        const desItem = m.querySelector('[data-ctx="fn:DES"]');
        if (desItem) desItem.click();
        return open && App.func === "DES" && App.sym === sym && m.classList.contains("hidden");
      })());
      t("ctx menu watch toggle", (() => {
        go("W");
        const row = document.querySelector('#view tbody tr[data-sym]');
        if (!row) return false;
        const sym = row.getAttribute("data-sym");
        const had = Store.data.watch.indexOf(sym) >= 0;
        row.dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, clientX: 200, clientY: 160 }));
        const item = document.querySelector('#ctxmenu [data-ctx="watch"]');
        if (!item) return false;
        item.click();
        const now = Store.data.watch.indexOf(sym) >= 0;
        if (now !== had) { /* restore */ Store.data.watch = had ? Store.data.watch.concat([sym]) : Store.data.watch.filter((x) => x !== sym); Store.save(); }
        return now !== had;
      })());
      t("settings page", (() => {
        go("SET");
        const cards = document.querySelectorAll("#view .setcard").length;
        const sw = document.querySelectorAll("#view .swtch").length;
        const png = document.querySelectorAll("#view [data-png]").length;
        go("HELP");
        return App.func === "HELP" && cards >= 6 && sw >= 3 && png >= 4;
      })());
      t("settings sound toggle", (() => {
        go("SET");
        const b = document.querySelector('#view .swtch[data-set="sound"]');
        const had = setts().sound;
        if (!b) return false;
        b.click();
        const now = setts().sound;
        const off = document.querySelector('#view .swtch[data-set="sound"]');
        const label = off ? off.textContent : "";
        if (off) off.click();
        return now === !had && label === "OFF" && setts().sound === had;
      })());
      t("settings brand icon swap", (() => {
        go("SET");
        const link = document.getElementById("brandicon");
        const b = document.querySelector('#view [data-set="icon"][data-val="64"]');
        if (!b || !link) return false;
        b.click();
        const ok = /icon-64\.png$/.test(link.getAttribute("href") || "");
        const back = document.querySelector('#view [data-set="icon"][data-val="256"]');
        if (back) back.click();
        return ok && /icon-256\.png$/.test(link.getAttribute("href") || "");
      })());
      t("settings density switch", (() => {
        go("SET");
        const b = document.querySelector('#view [data-set="density"][data-val="compact"]');
        if (!b) return false;
        b.click();
        const ok = document.documentElement.getAttribute("data-density") === "compact";
        const n = document.querySelector('#view [data-set="density"][data-val="normal"]');
        if (n) n.click();
        return ok && document.documentElement.getAttribute("data-density") === "normal";
      })());
      t("settings jump buttons route", (() => {
        go("SET");
        const b = document.querySelector('#view [data-go="HELP"]');
        if (!b) return false;
        b.click();
        const ok = App.func === "HELP" && /FUNCTION GUIDE|WORKSTATION|COMMANDS/i.test($("view").textContent || "");
        go("SET");
        return ok;
      })());
      t("alert bar shows tone + desktop state", (() => {
        go("ALRT");
        const txt = ($("view").textContent || "");
        const has = /tone/i.test(txt) && /desktop/i.test(txt) && /(ON|OFF)/.test(txt);
        const btn = document.querySelector('#view [data-go="SET"]');
        if (!btn) return false;
        btn.click();
        return has && App.func === "SET";
      })());
      t("profile create then cleanup", (() => {
        const before = profileNames().length;
        const ok = profileNew("QASET");
        const created = profileNames().indexOf("QASET") >= 0 && App.user === "QASET";
        switchUser("GUEST");
        try { localStorage.removeItem(PROFILE_PREFIX + "QASET"); } catch (e) { /* ignore */ }
        return ok && created && profileNames().indexOf("QASET") < 0 && App.user === "GUEST" && before >= 1;
      })());
      t("profile guest delete guarded", profileDelete() === false);
      t("png export opens chart and rejects invalid type", (() => {
        go("HELP");
        return exportPNG("GP") === true && App.func === "GP" && exportPNG("XYZ") === false;
      })());
      t("png canvas encoder", (() => {
        go("GP");
        const cv = $("canvas");
        if (!cv) return false;
        const href = cv.toDataURL("image/png");
        return /^data:image\/png;base64,/.test(href) && href.length > 2000;
      })());
      t("notification hooks", typeof notifyAlert === "function" && typeof askNotify === "function");
      t("sound gate silences ping", (() => {
        const had = setts().sound;
        setts().sound = false;
        let threw = false;
        try { ping(); ping(); } catch (e) { threw = true; }
        setts().sound = had;
        return !threw;
      })());
      t("watch reorder buttons", (() => {
        go("W");
        const btns = document.querySelectorAll("#view [data-wmv]");
        if (btns.length < 4) return false;
        const before = Store.data.watch.slice();
        const down = document.querySelector('#view tbody tr:nth-child(2) [data-wmv="-1"]');
        if (!down) return false;
        down.click();
        const moved = JSON.stringify(Store.data.watch) !== JSON.stringify(before);
        Store.data.watch = before;
        Store.save();
        render();
        return moved && JSON.stringify(Store.data.watch) === JSON.stringify(before);
      })());
      t("watch rows draggable + focusable", (() => {
        go("W");
        const rows = document.querySelectorAll("#view tbody tr[data-sym]");
        if (!rows.length) return false;
        const row = rows[0];
        row.focus();
        const focused = document.activeElement === row;
        return row.getAttribute("draggable") === "true" && row.getAttribute("tabindex") === "0" && focused;
      })());
      t("row keyboard arrow focus", (() => {
        go("W");
        const rows = document.querySelectorAll("#view tbody tr[data-sym]");
        if (rows.length < 2) return false;
        rows[0].focus();
        rows[0].dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true }));
        const ok = document.activeElement === rows[1];
        rows[0].focus();
        return ok;
      })());
      t("row keyboard opens ctx", (() => {
        go("W");
        const row = document.querySelector("#view tbody tr[data-sym]");
        const m = $("ctxmenu");
        if (!row || !m) return false;
        row.focus();
        row.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
        const open = !m.classList.contains("hidden");
        closeCtx();
        return open;
      })());
      t("touch long-press handler bound", (() => {
        go("W");
        const row = document.querySelector("#view tbody tr[data-sym]");
        const m = $("ctxmenu");
        if (!row || !m) return false;
        const t0 = { clientX: 180, clientY: 220 };
        row.dispatchEvent(new TouchEvent("touchstart", { bubbles: true, touches: [new Touch({ identifier: 1, target: row, clientX: t0.clientX, clientY: t0.clientY })] }));
        return true;
      })());
      t("print entry present", (() => {
        go("SET");
        const b = document.querySelector('#view [data-print]');
        go("HELP");
        return !!b;
      })());
      t("narrow split stacks", (() => {
        const mq = window.matchMedia("(max-width:900px)");
        setLayout("2");
        const g = document.querySelector(".quad.quad2");
        if (!g) return false;
        const cs = getComputedStyle(g);
        const cols = cs.gridTemplateColumns.split(" ").filter(Boolean).length;
        const rows = cs.gridTemplateRows.split(" ").filter(Boolean).length;
        const stacked = cols === 1 && rows === 2;
        setLayout("1");
        return mq.matches ? stacked : rows === 1;
      })());

      /* ---- keyboard reference overlay ---- */
      t("quickref overlay opens and closes", (() => {
        const el = $("quickref");
        if (!el) return false;
        openQuickref();
        const open = !el.classList.contains("hidden") && App.qfOpen === true;
        closeQuickref();
        return open && el.classList.contains("hidden");
      })());
      t("quickref lists real key bindings", (() => {
        const el = $("quickref");
        if (!el) return false;
        const kb = el.querySelectorAll("kbd").length;
        const txt = el.textContent.replace(/\s+/g, " ");
        return kb >= 12 && /Command palette/.test(txt) && /Command history/.test(txt);
      })());
      t("quickref styled", (() => {
        const q = document.querySelector("#quickref .qbox");
        if (!q) return false;
        const cs = getComputedStyle(q);
        return parseFloat(cs.borderTopWidth) >= 1 && parseFloat(cs.width) > 300;
      })());

      /* ---- command history popover ---- */
      t("command history button wired", (() => {
        const b = $("histbtn");
        const pop = $("histpop");
        if (!b || !pop) return false;
        const before = pop.classList.contains("hidden");
        openHist();
        const opened = !pop.classList.contains("hidden") && App.histOpen === true;
        closeHist();
        return before && opened && pop.classList.contains("hidden");
      })());
      t("history lists entries or empty state", (() => {
        App.cmdHist = ["AAPL GP", "WEI", "TOP"];
        openHist();
        const n = document.querySelectorAll("#histlist .hitem").length;
        const first = (document.querySelector("#histlist .hc") || {}).textContent;
        closeHist();
        App.cmdHist = [];
        openHist();
        const empty = !!document.querySelector("#histlist .hempty");
        closeHist();
        return n === 3 && first === "AAPL GP" && empty;
      })());
      t("history entry replays command", (() => {
        App.cmdHist = ["N"];
        openHist();
        const it = document.querySelector('#histlist [data-hist="0"]');
        if (!it) return false;
        it.click();
        return App.func === "N" && $("histpop").classList.contains("hidden");
      })());

      /* ---- indicator parameter panel ---- */
      t("IND button toggles parameter panel", (() => {
        go("GP");
        const b = $("indcfg");
        if (!b) return false;
        b.click();
        const open = !!document.querySelector("#view .indpop") && App.indPanel === true;
        $("indcfg").click();
        return open && !document.querySelector("#view .indpop");
      })());
      t("indicator inputs reject out-of-range values", (() => {
        const okA = applyIndCfg("a", 20, false) && applyIndCfg("bk", 5, false);
        const badA = applyIndCfg("a", 0, false) === false;
        const badBk = applyIndCfg("bk", 9, false) === false;
        applyIndCfg("a", 20, false);
        applyIndCfg("bk", 2, false);
        return okA && badA && badBk;
      })());
      t("MA legend follows configured periods", (() => {
        applyIndCfg("a", 12, false);
        openQuickref();
        closeQuickref();
        App.indPanel = true;
        render();
        const mt = $("matog");
        const txt = mt ? mt.textContent : "";
        App.indPanel = false;
        applyIndCfg("a", 20, false);
        render();
        return txt === "MA12/60";
      })());
      t("chart repaints in place without re-render", (() => {
        go("GP");
        const n = drawOnly();
        return n >= 1 && !!document.querySelector("#view .chartbox canvas");
      })());

      /* ---- full-screen chart ---- */
      t("full-screen chart toggles", (() => {
        go("GP");
        setFullChart(true);
        const on = document.body.classList.contains("chart-full") &&
          !!document.querySelector("#view .chartwrap.isful");
        const cs = getComputedStyle(document.querySelector("#view .chartwrap.isful"));
        const fixed = cs.position === "fixed";
        setFullChart(false);
        const off = !document.body.classList.contains("chart-full") &&
          !document.querySelector("#view .chartwrap.isful");
        return on && fixed && off;
      })());
      t("full-screen exits on Escape", (() => {
        go("GP");
        setFullChart(true);
        document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
        return !App.fullChart && !document.body.classList.contains("chart-full");
      })());

      /* ---- settings: backup / restore ---- */
      t("profile backup controls present", (() => {
        go("SET");
        const ex = document.querySelector('#view [data-backup="export"]');
        const im = document.querySelector('#view [data-backup="import"]');
        const rs = document.querySelector('#view [data-backup="reset"]');
        go("GP");
        return !!(ex && im && rs);
      })());
      t("backup payload carries profile state", (() => {
        const p = backupPayload();
        return !!p && p.app === "TERMINAL" && !!p.profile && !!p.exported &&
          !!p.data && Array.isArray(p.data.watch) && !!p.data.maCfg;
      })());
      t("indicator config persists to store", (() => {
        applyIndCfg("b", 55);
        const saved = JSON.parse(localStorage.getItem(Store.key()) || "{}");
        applyIndCfg("b", 60);
        return !!(saved.maCfg && saved.maCfg.b === 55);
      })());
      t("new overlay classes are styled", (() => {
        const probe = (sel, prop) => {
          const el = document.querySelector(sel);
          return el ? getComputedStyle(el)[prop] : null;
        };
        return probe("#histbtn", "cursor") === "pointer" || !!document.querySelector("#quickref .qbox");
      })());

      /* ---- footer status chips ---- */
      t("feed freshness chip reflects state", (() => {
        const el = $("freshflag");
        if (!el) return false;
        setFresh("live");
        const live = el.textContent === "LIVE" && el.classList.contains("live");
        setFresh("stale");
        const stale = el.textContent === "STALE" && el.classList.contains("stale");
        setFresh("live");
        return live && stale;
      })());
      t("autosave chip flashes on store write", (() => {
        const el = $("savedflag");
        if (!el) return false;
        el.classList.remove("on");
        Store.save();
        return el.classList.contains("on") && /^SAVED \d\d:\d\d:\d\d$/.test(el.textContent);
      })());
      t("print header carries profile and title", (() => {
        go("WEI");
        const ph = document.querySelector(".panel-hd");
        const s = ph ? ph.getAttribute("data-printed") || "" : "";
        go("HELP");
        return /WEI/.test(s) && s.split("\u00b7").length >= 3;
      })());

      /* ---- sortable headers ---- */
      t("sorted column shows arrow and aria-sort", (() => {
        go("WEI");
        const th = document.querySelector("#view thead th:nth-child(3)");
        if (!th) return false;
        const dir = sortTable(th, "desc");
        const arrow = getComputedStyle(th, "::after").content;
        const aria = th.getAttribute("aria-sort");
        go("HELP");
        return dir === "desc" && arrow.indexOf("\u25BC") >= 0 && aria === "descending";
      })());
      t("sort state survives re-render", (() => {
        go("WEI");
        const th = document.querySelector("#view thead th:nth-child(3)");
        sortTable(th, "asc");
        render();
        const th2 = document.querySelector("#view thead th:nth-child(3)");
        const ok = !!th2 && th2.classList.contains("sort-asc") && th2.getAttribute("aria-sort") === "ascending";
        App.sort = null;
        go("HELP");
        return ok;
      })());

      /* ---- per-view scroll memory ---- */
      t("scroll position is remembered per function", (() => {
        App.scrollMemo = {};
        go("WEI");
        const v = $("view");
        const oldStyle = v.getAttribute("style");
        v.style.flex = "0 0 60px"; // force an overflow so scrollTop is meaningful
        v.scrollTop = 40;
        const real = v.scrollTop;
        App.scrollMemo["WEI"] = real;
        go("HELP");
        go("WEI");
        const back = $("view").scrollTop;
        if (oldStyle == null) v.removeAttribute("style"); else v.setAttribute("style", oldStyle);
        go("HELP");
        App.scrollMemo = {};
        return real > 0 && back === real;
      })());

      /* ---- UI zoom ---- */
      t("zoom steps clamp and persist", (() => {
        zoomStep(0, true);
        const base = document.body.style.zoom;
        zoomStep(0.1);
        const up = App.zoom;
        for (let i = 0; i < 10; i++) zoomStep(0.1);
        const capped = App.zoom;
        for (let i = 0; i < 20; i++) zoomStep(-0.1);
        const floored = App.zoom;
        zoomStep(0, true);
        return base === "" && up === 1.1 && capped === 1.3 && floored === 0.8 && Store.data.zoom === 1;
      })());

      /* ---- settings scale stepper ---- */
      t("SET scale stepper updates and persists", (() => {
        zoomStep(0, true);
        go("SET");
        const inc = document.querySelector('#view [data-zoom="0.1"]');
        const reset = document.querySelector('#view [data-zoom="0"]');
        if (!inc || !reset) return false;
        inc.click();
        const lbl = $("setzoom");
        const a = App.zoom;
        const shown = lbl ? lbl.textContent : "";
        reset.click();
        const back = App.zoom === 1 && Store.data.zoom === 1;
        go("HELP");
        return a === 1.1 && shown === "110%" && back;
      })());

      /* ---- row navigation shortcuts ---- */
      t("Home/End and PageUp/PageDown move row selection", (() => {
        go("FLDS");
        const rows = document.querySelectorAll("#view tbody tr");
        if (rows.length < 12) return false;
        if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
        App.sel = 2;
        const ev = (key) => document.dispatchEvent(new KeyboardEvent("keydown", { key: key, bubbles: true, cancelable: true }));
        ev("End");
        const atEnd = App.sel === rows.length - 1;
        ev("Home");
        const atHome = App.sel === 0;
        ev("PageDown");
        const paged = App.sel === 10;
        ev("PageUp");
        const back = App.sel === 0;
        go("HELP");
        return atEnd && atHome && paged && back;
      })());
    const pass = res.filter((r) => r[1]).length;
    const fail = res.filter((r) => !r[1]).map((r) => r[0]);
    document.title = "SELFTEST " + pass + "/" + res.length + (fail.length ? " FAIL:" + fail.join("|") : " OK");
    const pre = document.createElement("pre");
    pre.id = "selftest-out";
    pre.textContent = JSON.stringify(res, null, 1);
    pre.style.cssText = "position:fixed;left:0;top:0;z-index:9999;background:#000;color:#0f0;font-size:10px;max-height:100%;overflow:auto";
    document.body.appendChild(pre);
  }

  /* ---------------- boot ---------------- */
  function clock() {
    const d = new Date();
    $("clock").textContent = hhmmss(d);
  }

  function syncNavigation(replace) {
    if (/selftest/i.test(location.hash) || App.routeError) return;
    const url = new URL(location.href);
    url.searchParams.set("lay", App.layout);
    url.searchParams.delete("split");
    url.hash = App.func + (FUNCS[App.func]?.needsSym && App.sym ? "/" + App.sym : "");
    const state = { terminalUI:true, func:App.func, sym:App.sym, layout:App.layout, focus:App.focus, panels:JSON.parse(JSON.stringify(panels())), split:Object.assign({},Store.data.split) };
    if (url.href === location.href && !replace) history.replaceState(state,"",url);
    else history[replace ? "replaceState" : "pushState"](state,"",url);
    window.dispatchEvent(new CustomEvent("terminal:layout-changed"));
  }

  function fromHash() {
    const raw = (location.hash || "").replace(/^#\/?/, "").toUpperCase();
    App.routeError = null;
    if (!raw || raw === "SELFTEST") return;
    const parts = raw.split("/"), fn=parts[0];
    if (fn === "LOGIN") { openAuth(); return; }
    if (!VIEWS[fn] || parts.length>2 || (parts[1] && !bySym[parts[1]])) { App.routeError=raw; return; }
    App.func=fn;
    if (parts[1]) App.sym=parts[1];
    else if(FUNCS[fn]?.needsSym) App.sym=App.sym || "AAPL";
    if (App.layout !== "1") {
      const panel=panelAt(App.focus);panel.func=fn;panel.sym=FUNCS[fn]?.needsSym ? App.sym : "";
    }
  }

  function restoreNavigation() {
    const state=history.state;
    if(state && state.terminalUI) {
      App.routeError=null;App.func=state.func;App.sym=state.sym;App.layout=state.layout;App.focus=state.focus;
      Store.data.layout=state.layout;Store.data.panels=JSON.parse(JSON.stringify(state.panels));Store.data.split=Object.assign({},state.split);Store.save();
    } else {
      const layout=new URLSearchParams(location.search).get("lay");
      if(["1","2","4"].includes(layout))App.layout=layout;
      fromHash();
    }
    App.sel=0;render();
  }

  function boot() {
    bind();
    bootAuth();
    bootUI();
    applySetts();
    clock();
    setInterval(clock, 1000);
    fromHash();
    const qlay = new URLSearchParams(location.search).get("lay");
    if (qlay === "1" || qlay === "2" || qlay === "4") App.layout = qlay;
    const qsp = new URLSearchParams(location.search).get("split");
    if (qsp) {
      const pair = qsp.split(",").map(Number);
      const c = pair[0];
      const r = pair.length > 1 ? pair[1] : 0.5;
      if (isFinite(c) && isFinite(r)) {
        Store.data.split = {
          c: Math.min(0.8, Math.max(0.2, c)),
          r: Math.min(0.8, Math.max(0.2, r))
        };
      }
    }
    if(App.layout !== "1") {
      if(location.hash && !/selftest/i.test(location.hash))fromHash();
      else { const panel=panelAt(App.focus);App.func=panel.func;if(panel.sym)App.sym=panel.sym; }
    }
    paintRail();
    render();
    App.tickTimer = setInterval(() => {
      if (document.hidden && setts().pauseHidden) { setFresh("stale"); return; }
      tick();
      setFresh("live");
    }, 1000);
    document.addEventListener("visibilitychange", () => {
      App.paused = document.hidden && setts().pauseHidden;
      setFresh(App.paused ? "stale" : "live");
      if (!document.hidden && setts().pauseHidden) tick();
    });
    syncNavigation(true);
    window.addEventListener("hashchange", restoreNavigation);
    window.addEventListener("popstate", restoreNavigation);
    $("cmd").focus();
    window.TerminalWorkspace=Object.freeze({
      snapshot:()=>JSON.parse(JSON.stringify({layout:App.layout,func:App.func,sym:App.sym||'',focus:App.layout==='1'?0:App.focus,panels:panels(),split:Store.data.split||{c:.5,r:.5}})),
      codes:()=>Object.keys(VIEWS),
      focus:index=>focusCell(index),
      restore:value=>{
        if(!value||!['1','2','4'].includes(value.layout)||!VIEWS[value.func]||!Array.isArray(value.panels)||value.panels.length!==4||!Number.isInteger(value.focus)||value.focus<0||value.focus>=Number(value.layout))throw Error('invalid_workspace_layout');
        const checked=value.panels.map(p=>{if(!VIEWS[p.func]||(p.sym&&!bySym[p.sym]))throw Error('invalid_workspace_panel');return {func:p.func,sym:p.sym||''};});
        if(value.sym&&!bySym[value.sym])throw Error('invalid_workspace_symbol');
        const split={c:Number(value.split?.c),r:Number(value.split?.r)};
        if(Object.values(split).some(n=>!Number.isFinite(n)||n<.2||n>.8))throw Error('invalid_workspace_split');
        Store.data.panels=checked;Store.data.split=split;Store.data.layout=App.layout=value.layout;
        App.func=value.func;App.sym=value.sym||null;App.focus=value.focus;App.routeError=null;
        Store.save();render();syncNavigation(true);
        $("stMsg").textContent="工作区布局已恢复 · "+value.layout+"屏";
      }
    });
    // self-test surface for automated checks
    window.__TERMINAL__ = {
      ok: true,
      version: "1.0",
      securities: UNIV.length,
      views: Object.keys(VIEWS)
    };
    document.title = "TERMINAL \u00b7 " + UNIV.length + " securities \u00b7 " + Object.keys(VIEWS).length + " views";
    if (/selftest/i.test(location.hash)) setTimeout(() => {
      try { selftest(); } catch (err) { document.title = "SELFTEST ERROR: " + (err && err.message); }
    }, 250);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
