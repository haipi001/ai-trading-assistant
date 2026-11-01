import { validateMarketBars } from './market-chart-model.js';
const bars = {'1m':'1min','5m':'5min','15m':'15min','30m':'30min','1h':'1h','4h':'4h','6h':'6Hutc','12h':'12Hutc','1d':'1Dutc','3d':'3Dutc','1wk':'1Wutc','1mo':'1Mutc'};
export async function loadBitgetPublicCandles(symbol, timeframe, options = {}) {
  const unsupported = source => ({status:'unsupported',candles:[],source});
  if (!['bitget'].includes(String(options.venue || '').toLowerCase()) || options.quoteCurrency !== 'USDT') return unsupported('Bitget公开行情仅支持本平台USDT现货');
  if (!bars[timeframe]) return unsupported(`Bitget公开行情不支持周期 ${timeframe}`);
  const input = String(symbol).trim().toUpperCase();
  if (!/^[A-Z0-9]{1,24}(?:[/-]USDT)?$/.test(input)) return unsupported('Bitget公开行情标的格式不支持');
  const base = input.replace(/[/-]?USDT$/, '');
  if (!base) return unsupported('Bitget公开行情标的无效');
  const pair = `${base}USDT`;
  const controller = new AbortController(), abort = () => controller.abort();
  const timer = setTimeout(abort,10000);
  options.signal?.addEventListener('abort',abort,{once:true});
  try {
    if (options.signal?.aborted) controller.abort();
    const url = new URL('https://api.bitget.com/api/v2/spot/market/candles');
    url.search = new URLSearchParams({symbol:pair,granularity:bars[timeframe],limit:'240'}).toString();
    const response = await (options.publicFetch || fetch)(url.href,{signal:controller.signal,credentials:'omit',redirect:'error',cache:'no-store'});
    if (!response.ok) return {status:'error',candles:[],source:`Bitget公开行情失败（HTTP${response.status}）`};
    const body = await response.json();
    if (body?.code !== '00000') return {status:'error',candles:[],source:'Bitget未返回成功的公开行情响应'};
    if (!Array.isArray(body.data) || body.data.length > 240) throw new Error('shape');
    const decimal = value => typeof value === 'string' && /^(?:\d+(?:\.\d*)?|\.\d+)$/.test(value) ? Number(value) : NaN;
    const candles = validateMarketBars(body.data.map(row => {
      if (!Array.isArray(row) || row.length !== 8 || typeof row[0] !== 'string' || !/^\d{13}$/.test(row[0]) || Number(row[0]) % 1000) throw new Error('shape');
      return {time:Number(row[0])/1000,open:decimal(row[1]),high:decimal(row[2]),low:decimal(row[3]),close:decimal(row[4]),volume:decimal(row[5])};
    }));
    if (candles.some(row => row.open <= 0 || row.low <= 0 || row.close <= 0)) throw new Error('price');
    return {status:candles.length?'connected':'empty',candles,...({'1m':'1m','5m':'5m','15m':'15m','30m':'30m','1h':'1H','4h':'4H'}[timeframe]?{publicProvider:'bitget',publicInterval:({'1m':'1m','5m':'5m','15m':'15m','30m':'30m','1h':'1H','4h':'4H'})[timeframe]}:{}),quoteCurrency:'USDT',fetchedAt:new Date().toISOString(),asset:{symbol:pair,venue:'bitget',currency:'USDT'},source:`Bitget公开现货快照 · ${pair} · ${timeframe} · UTC（30秒轮询，非实时推送；末根可能未收盘）`};
  } catch (error) {
    return {status:error.name === 'AbortError'||error instanceof TypeError?'offline':'invalid',candles:[],source:error.name === 'AbortError'?'Bitget公开行情已取消或超时':error instanceof TypeError?'Bitget公开行情无法读取（网络或跨域限制）':'Bitget公开K线响应无效'};
  } finally {clearTimeout(timer);options.signal?.removeEventListener('abort',abort);}
}
