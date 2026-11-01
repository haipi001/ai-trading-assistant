import { loadBitgetPublicCandles } from "./bitget-public-market.js";
import { loadOkxPublicCandles } from "./okx-public-market.js";
import { apiRequest } from "./backend-api.js";
import { selectMarketAsset, validateMarketBars } from "./market-chart-model.js";
import { parseChartTimestamp } from "./chart-analysis.js";
import { aggregateMarketCandles } from "./market-candle-aggregation.js";

async function loadDatabaseCandles(symbol, timeframe = "1d", options = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 12000);
  const abort = () => controller.abort();
  options.signal?.addEventListener("abort", abort, { once: true });
  const request = options.request || apiRequest;
  try {
    if (options.signal?.aborted) throw Object.assign(new Error("cancelled"), { name: "AbortError" });
    const assets = await request("/assets?limit=1000", { signal: controller.signal });
    let asset;
    try { asset = selectMarketAsset(assets, symbol, options.venue, options.quoteCurrency); }
    catch (error) { return { status: "missing", candles: [], source: error.message }; }
    const rows = await request(`/candles?asset_id=${encodeURIComponent(asset.id)}&timeframe=${encodeURIComponent(timeframe)}&limit=240`, { signal: controller.signal });
    let candles;
    try {
      if (!Array.isArray(rows)) throw new Error("后端K线不是数组");
      if (rows.some(row => (row.asset_id !== undefined && row.asset_id !== asset.id) || (row.timeframe !== undefined && row.timeframe !== timeframe))) throw new Error("返回K线标的或周期与请求不一致");
      if (new Set(rows.map(row => row.source || "后端快照")).size > 1) throw new Error("后端K线包含多个来源，请先核对来源");
      const numeric = value => typeof value === "number" ? value : typeof value === "string" && /^(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i.test(value.trim()) ? Number(value) : NaN;
      candles = validateMarketBars(rows.map(row => ({ time: parseChartTimestamp(String(row.timestamp)), open: numeric(row.open), high: numeric(row.high), low: numeric(row.low), close: numeric(row.close), volume: row.volume === undefined ? 0 : numeric(row.volume) })));
    } catch (error) { return { status: "invalid", candles: [], asset, source: `后端数据无效：${error.message}` }; }
    return {
      status: candles.length ? "connected" : "empty",
      source: rows[0]?.source || "后端快照",
      asset,
      quoteCurrency: asset.currency || options.quoteCurrency || null,
      volumeAvailable:rows.every(row=>row.volume!==undefined&&row.volume!==null),
      candles,
    };
  } catch (error) {
    if(error.status===401||error.status===403)return {status:"unauthorized",candles:[],source:error.status===401?"后端需要登录（HTTP401）":"当前用户无行情读取权限（HTTP403）"};
    if(error.status)return {status:"error",candles:[],source:`后端行情请求失败（HTTP${error.status}）`};
    return { status: "offline", candles: [], source: error.name === "AbortError" ? "后端响应超时" : error instanceof TypeError ? "浏览器无法读取后端（网络或跨域限制）" : "后端未连接" };
  } finally { clearTimeout(timer); options.signal?.removeEventListener("abort", abort); }
}

// Public spot snapshots are independent of private account authorization.
export async function loadBinancePublicCandles(symbol, timeframe, options = {}) {
  const interval = ({ '1wk': '1w', '1mo': '1M' })[timeframe] || timeframe;
  const intervals = new Set(['1s','1m','3m','5m','15m','30m','1h','2h','4h','6h','8h','12h','1d','3d','1w','1M']);
  const unavailable = source => ({ status: 'unsupported', candles: [], source });
  if (!['币安','binance'].includes(String(options.venue || '').toLowerCase()) || options.quoteCurrency !== 'USDT') return unavailable('公开行情当前仅支持币安现货 USDT');
  if (!intervals.has(interval)) return unavailable(`币安公开行情不支持周期 ${timeframe}`);
  const input = String(symbol).trim().toUpperCase();
  if (!/^[A-Z0-9]{1,24}(?:\/USDT)?$/.test(input)) return unavailable('公开行情标的格式不支持');
  const pair = input.includes('/') ? input.replace('/', '') : input.endsWith('USDT') ? input : `${input}USDT`;
  const controller = new AbortController(), abort = () => controller.abort();
  const timer = setTimeout(abort, 10000);
  options.signal?.addEventListener('abort', abort, { once: true });
  try {
    if (options.signal?.aborted) controller.abort();
    const url = new URL('https://data-api.binance.vision/api/v3/klines');
    url.search = new URLSearchParams({ symbol: pair, interval, limit: '240' }).toString();
    const response = await (options.publicFetch || fetch)(url.href, { signal: controller.signal, credentials: 'omit', redirect: 'error', cache: 'no-store' });
    if (!response.ok) return { status: 'error', candles: [], source: `币安公开行情失败（HTTP${response.status}）` };
    const rows = await response.json();
    if (!Array.isArray(rows) || rows.length > 240) throw new Error('shape');
    const numeric = value => typeof value === 'string' && /^(?:\d+(?:\.\d*)?|\.\d+)$/.test(value) ? Number(value) : NaN;
    const candles = validateMarketBars(rows.map(row => {
      if (!Array.isArray(row) || row.length < 7 || !Number.isSafeInteger(row[0]) || row[0] % 1000 !== 0 || !Number.isSafeInteger(row[6]) || row[6] < row[0]) throw new Error('shape');
      return { time: row[0] / 1000, open: numeric(row[1]), high: numeric(row[2]), low: numeric(row[3]), close: numeric(row[4]), volume: numeric(row[5]) };
    }));
    if (candles.some(bar => bar.open <= 0 || bar.low <= 0 || bar.close <= 0)) throw new Error('price');
    return { publicProvider:'binance', publicInterval:interval, status: candles.length ? 'connected' : 'empty', candles, source: `Binance 公开现货快照 · ${pair} · ${timeframe}（30秒轮询，非实时推送）`, quoteCurrency: 'USDT', fetchedAt: new Date().toISOString(), asset: { symbol: pair, venue: 'binance', currency: 'USDT' } };
  } catch (error) {
    return { status: error.name === 'AbortError' ? 'offline' : error instanceof TypeError ? 'offline' : 'invalid', candles: [], source: error.name === 'AbortError' ? '币安公开行情已取消或超时' : error instanceof TypeError ? '币安公开行情无法读取（网络或跨域限制）' : '币安公开K线响应无效' };
  } finally { clearTimeout(timer); options.signal?.removeEventListener('abort', abort); }
}

export async function loadBackendCandles(symbol, timeframe = '1d', options = {}) {
  const database = await loadDatabaseCandles(symbol, timeframe, options);
  if (!options.publicMarket || !['missing','empty','offline'].includes(database.status) || options.signal?.aborted) return database;
  const venue = String(options.venue || '').toLowerCase();
  const loader = ['币安','binance'].includes(venue) ? loadBinancePublicCandles : ['欧易okx','欧易','okx'].includes(venue) ? loadOkxPublicCandles : venue==='bitget'?loadBitgetPublicCandles:null;
  if (!loader || options.quoteCurrency !== 'USDT') return database;
  let snapshot = await loader(symbol, timeframe, options);
  const aggregation = {'45m':{base:'15m',seconds:900,target:2700},'8h':{base:'4h',seconds:14400,target:28800}}[timeframe];
  if(snapshot.status==='unsupported'&&aggregation&&!options.signal?.aborted){
    const raw=await loader(symbol,aggregation.base,options);
    if(raw.status==='connected'){
      try{
        const combined=aggregateMarketCandles(raw.candles,aggregation.seconds,aggregation.target);
        const {publicProvider,publicInterval,...metadata}=raw;
        snapshot={...metadata,status:combined.candles.length?'connected':'empty',candles:combined.candles,aggregation:{base:aggregation.base,target:timeframe,skipped:combined.skipped,partial:combined.partial},source:`${raw.asset.venue}公开现货 · ${raw.asset.symbol} · ${timeframe}（由${aggregation.base}按UTC聚合，30秒轮询；${combined.partial?'末根未收盘':'仅完整区间'}；跳过${combined.skipped}个不完整区间）`};
      }catch{snapshot={status:'invalid',candles:[],source:'公开K线聚合失败：子周期数据或数值无效'};}
    }else snapshot={...raw,source:`${timeframe}聚合所需${aggregation.base}数据不可用：${raw.source}`};
  }
  return { ...snapshot, source: `${snapshot.source}${snapshot.fetchedAt ? ` · 获取于 ${snapshot.fetchedAt}` : ""}；本地：${database.source}` };
}
