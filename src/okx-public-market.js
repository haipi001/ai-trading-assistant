import { validateMarketBars } from './market-chart-model.js';
const bars = {'1m':'1m','3m':'3m','5m':'5m','15m':'15m','30m':'30m','1h':'1H','2h':'2H','4h':'4H','6h':'6Hutc','12h':'12Hutc','1d':'1Dutc','2d':'2Dutc','3d':'3Dutc','1wk':'1Wutc','1mo':'1Mutc','3mo':'3Mutc'};
export async function loadOkxPublicCandles(symbol, timeframe, options = {}) {
  const unsupported = source => ({status:'unsupported',candles:[],source});
  if (!['欧易okx','欧易','okx'].includes(String(options.venue || '').toLowerCase()) || options.quoteCurrency !== 'USDT') return unsupported('OKX公开行情仅支持本平台USDT现货');
  if (!bars[timeframe]) return unsupported(`OKX公开行情不支持周期 ${timeframe}`);
  const input = String(symbol).trim().toUpperCase();
  if (!/^[A-Z0-9]{1,24}(?:[/-]USDT)?$/.test(input)) return unsupported('OKX公开行情标的格式不支持');
  const base = input.replace(/[/-]?USDT$/, '');
  if (!base) return unsupported('OKX公开行情标的无效');
  const pair = `${base}-USDT`;
  const controller = new AbortController(), abort = () => controller.abort();
  const timer = setTimeout(abort,10000);
  options.signal?.addEventListener('abort',abort,{once:true});
  try {
    if (options.signal?.aborted) controller.abort();
    const url = new URL('https://www.okx.com/api/v5/market/candles');
    url.search = new URLSearchParams({instId:pair,bar:bars[timeframe],limit:'240'}).toString();
    const response = await (options.publicFetch || fetch)(url.href,{signal:controller.signal,credentials:'omit',redirect:'error',cache:'no-store'});
    if (!response.ok) return {status:'error',candles:[],source:`OKX公开行情失败（HTTP${response.status}）`};
    const body = await response.json();
    if (body?.code !== '0') return {status:'error',candles:[],source:'OKX未返回成功的公开行情响应'};
    if (!Array.isArray(body.data) || body.data.length > 240) throw new Error('shape');
    const decimal = value => typeof value === 'string' && /^(?:\d+(?:\.\d*)?|\.\d+)$/.test(value) ? Number(value) : NaN;
    const candles = validateMarketBars(body.data.map(row => {
      if (!Array.isArray(row) || row.length !== 9 || typeof row[0] !== 'string' || !/^\d{13}$/.test(row[0]) || Number(row[0]) % 1000 || !['0','1'].includes(row[8])) throw new Error('shape');
      return {time:Number(row[0])/1000,open:decimal(row[1]),high:decimal(row[2]),low:decimal(row[3]),close:decimal(row[4]),volume:decimal(row[5])};
    }));
    if (candles.some(row => row.open <= 0 || row.low <= 0 || row.close <= 0)) throw new Error('price');
    return {status:candles.length?'connected':'empty',candles,publicProvider:'okx',publicInterval:bars[timeframe],quoteCurrency:'USDT',fetchedAt:new Date().toISOString(),asset:{symbol:pair,venue:'okx',currency:'USDT'},source:`OKX公开现货快照 · ${pair} · ${timeframe} · UTC（30秒轮询，非实时推送；末根可能未收盘）`};
  } catch (error) {
    return {status:error.name === 'AbortError'||error instanceof TypeError?'offline':'invalid',candles:[],source:error.name === 'AbortError'?'OKX公开行情已取消或超时':error instanceof TypeError?'OKX公开行情无法读取（网络或跨域限制）':'OKX公开K线响应无效'};
  } finally {clearTimeout(timer);options.signal?.removeEventListener('abort',abort);}
}
