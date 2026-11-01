export const SUPPORTED_CHART_SYNC = ["十字光标", "交易对", "指标", "周期", "日期范围", "缩放比例", "坐标轴"];
export function periodDefinition(label) {
  if (label === "分时") return { label, timeframe: "1m", seconds: 60 };
  if (label === "季K") return { label, timeframe: "3mo", months: 3 };
  if (label === "年K") return { label, timeframe: "1y", months: 12 };
  const match = /^([1-9]\d{0,3})(秒|分|时|日|周|月)$/.exec(label);
  if (!match) throw new Error("不支持的周期，请输入正整数和明确单位");
  const amount = Number(match[1]), unit = match[2];
  const suffix = { 秒: "s", 分: "m", 时: "h", 日: "d", 周: "wk", 月: "mo" }[unit];
  return { label, timeframe: `${amount}${suffix}`, ...(unit === "月" ? { months: amount } : { seconds: amount * { 秒: 1, 分: 60, 时: 3600, 日: 86400, 周: 604800 }[unit], week: unit === "周" }) };
}
export function periodBounds(label, now = Date.now()) {
  const definition = periodDefinition(label);
  if (!Number.isFinite(now) || now <= 0 || !Number.isFinite(new Date(now).getTime())) throw new Error("时间无效");
  if (definition.months) {
    const date = new Date(now), month = date.getUTCFullYear() * 12 + date.getUTCMonth();
    const first = Math.floor(month / definition.months) * definition.months;
    const stamp = value => Math.floor(value / 12) < 1970 ? 0 : Date.UTC(Math.floor(value / 12), value % 12, 1) / 1000;
    return { start: stamp(first), end: stamp(first + definition.months), previous: count => stamp(first - count * definition.months) };
  }
  const anchor = definition.week ? Date.UTC(1970, 0, 5) / 1000 : 0;
  const start = Math.floor((now / 1000 - anchor) / definition.seconds) * definition.seconds + anchor;
  return { start, end: start + definition.seconds, previous: count => start - count * definition.seconds };
}
export function periodCountdown(label, now = Date.now()) {
  const seconds = Math.max(0, Math.ceil(periodBounds(label, now).end - now / 1000));
  const days = Math.floor(seconds / 86400);
  return `${days ? `${days}天 ` : ""}${[Math.floor(seconds / 3600) % 24, Math.floor(seconds / 60) % 60, seconds % 60].map(value => String(value).padStart(2, "0")).join(":")}`;
}
export function validateMarketBars(rows) {
  if (!Array.isArray(rows)) throw new Error("后端K线不是数组");
  const seen = new Set();
  return rows.map((row, index) => {
    const { time, open, high, low, close } = row;
    const volume = row.volume ?? 0;
    if (!Number.isSafeInteger(time) || time <= 0 || time > 253402300799 || ![open, high, low, close, volume].every(value => typeof value === "number" && Number.isFinite(value) && value >= 0) || high < Math.max(open, close, low) || low > Math.min(open, close)) throw new Error(`第${index + 1}根K线价格或时间无效`);
    if (seen.has(time)) throw new Error("后端K线时间重复，不合并不同来源的数据");
    seen.add(time);
    return { time, open, high, low, close, volume };
  }).sort((a, b) => a.time - b.time);
}
export function demoMarketBars(base, period, seed = "", now = Date.now(), count = 132) {
  if (!Number.isFinite(base) || base <= 0) return [];
  const bounds = periodBounds(period, now);
  const times = Array.from({ length: count }, (_, i) => bounds.previous(count - 1 - i)).filter(time => time > 0);
  const variant = [...seed].reduce((sum, char) => sum + char.charCodeAt(0), 0) % 19;
  let close = base * .982;
  const bars = times.map((time, index) => {
    const open = close;
    close = Math.max(base * .82, open + Math.sin((index + variant) / 7) * base * .000714 + base * .00024 + Math.cos(index / 13) * base * .00035);
    return { time, open, high: Math.max(open, close) + base * (.0012 + ((index * 7) % 9) * .00012), low: Math.max(0, Math.min(open, close) - base * (.0011 + ((index * 5) % 8) * .00011)), close, volume: 90 + ((index * 37 + variant * 41) % 420) };
  });
  const scale = base / (bars.at(-1)?.close || base);
  return bars.map(bar => ({ ...bar, open: bar.open * scale, high: bar.high * scale, low: bar.low * scale, close: bar.close * scale }));
}
const venueAliases = { "币安": "binance", "欧易okx": "okx", "欧易": "okx", "纳斯达克": "nasdaq" };
export function selectMarketAsset(assets, symbol, venue, quoteCurrency) {
  if (!Array.isArray(assets)) throw new Error("资产目录格式无效");
  const canonical = value => String(value || "").trim().toUpperCase().replace(/[-/]/g, "");
  const requested = canonical(symbol), quote = quoteCurrency ? canonical(quoteCurrency) : null;
  if(!requested)throw new Error("请选择标的");
  const pairQuote=value=>["FDUSD","USDT","USDC","BUSD","TUSD","USD","EUR"].find(unit=>value.length>unit.length&&value.endsWith(unit));
  const requestedQuote=pairQuote(requested);
  if(quote&&requestedQuote&&requestedQuote!==quote)throw new Error("请求交易对的报价币与页面报价币不一致");
  const normalVenue = value => venueAliases[String(value).trim().toLowerCase()] || String(value).trim().toLowerCase();
  let available = venue ? assets.filter(asset => normalVenue(asset.venue) === normalVenue(venue)) : assets;
  if(quote)available=available.filter(asset=>{
    const assetSymbol=canonical(asset.symbol),encodedQuote=pairQuote(assetSymbol),currency=canonical(asset.currency);
    if(encodedQuote&&encodedQuote!==quote || currency&&currency!==quote)return false;
    return encodedQuote===quote || currency===quote;
  });
  const exact=available.filter(asset=>canonical(asset.symbol)===requested);
  const pairs=available.filter(asset=>(quote?[quote]:["USD","USDT","USDC"]).some(unit=>canonical(asset.symbol)===requested+unit));
  const candidates=quote?[...new Set([...exact,...pairs])]:exact.length?exact:pairs;
  if(!candidates.length)throw new Error(quote ? `后端暂无匹配${quote}报价币与所选平台的标的数据` : venue?"后端暂无该标的在所选平台的数据":"后端暂无该标的");
  if(candidates.length!==1)throw new Error("后端存在多个匹配资产，请指定唯一标的、报价币和平台");
  return candidates[0];
}

// Independent of React/LW Charts so re-entrant chart callbacks can be tested.
export function createChartSync(readOptions) {
  const panes = new Map(), expectedRanges = new Map();
  let crosshairBusy = false, rangeBusy = false;
  return {
    register(id, pane) { panes.set(id, pane); return () => { if (panes.get(id) === pane) panes.delete(id); expectedRanges.delete(id); }; },
    crosshair(id, time) {
      if (crosshairBusy || !readOptions().includes("十字光标")) return;
      crosshairBusy = true;
      try { for (const [key, pane] of panes) if (key !== id) pane.crosshair(time ?? null); }
      finally { crosshairBusy = false; }
    },
    range(id, logical, timeRange, explicit = false) {
      const expected=expectedRanges.get(id);expectedRanges.delete(id);
      if(rangeBusy)return;
      const matches=expected?.kind==="logical"?logical&&Math.abs(logical.from-expected.range.from)<1e-7&&Math.abs(logical.to-expected.range.to)<1e-7:expected?.kind==="date"?timeRange&&expected.range.from===timeRange.from&&expected.range.to===timeRange.to:expected?.kind==="zoom"&&logical&&Math.abs(logical.to-logical.from-expected.span)<1e-7;
      if(!explicit&&matches)return;
      const options = readOptions();
      if (!logical || !Number.isFinite(logical.from) || !Number.isFinite(logical.to) || logical.to <= logical.from) return;
      const dates = options.includes("日期范围") && options.includes("周期") && timeRange;
      if (!dates && !options.includes("缩放比例")) return;
      rangeBusy = true;
      try {
        for (const [key, pane] of panes) if (key !== id) {
          const source=panes.get(id);
          if(dates&&source?.timeline&&source.timeline===pane.timeline&&pane.logicalRange){
            expectedRanges.set(key,{kind:"logical",range:{...logical}});
            pane.logicalRange(logical);
            continue;
          }
          expectedRanges.set(key,dates?{kind:"date",range:timeRange}:{kind:"zoom",span:logical.to-logical.from});
          if (dates) pane.timeRange(timeRange);
          else pane.zoom(logical.to - logical.from);
        }
      } finally { rangeBusy = false; }
    },
  };
}
