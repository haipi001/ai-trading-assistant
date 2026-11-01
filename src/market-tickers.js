const decimal = value => typeof value === 'string' && /^\d+(?:\.\d+)?$/.test(value) && Number.isFinite(Number(value)) ? Number(value) : NaN;
export function decodeMarketTickers(payload, provider, symbols) {
  if(provider==='bitget') {
    if(payload?.code!=='00000'||!Array.isArray(payload.data)||payload.data.length>10000)throw new Error('invalid Bitget ticker response');
    return decodeMarketTickers(payload.data.map(row=>({symbol:row.symbol,lastPrice:row.lastPr,openPrice:row.open,highPrice:row.high24h,lowPrice:row.low24h,quoteVolume:row.quoteVolume,closeTime:typeof row.ts==='string'&&/^\d{13}$/.test(row.ts)?Number(row.ts):NaN})),'binance',symbols);
  }

  const rows = provider === 'binance' ? payload : payload?.code === '0' ? payload.data : null;
  if (!Array.isArray(rows) || rows.length > 10000) throw new Error('invalid ticker response');
  const wanted = new Set(symbols), result = {};
  for (const row of rows) {
    const pair = provider === 'binance' ? row.symbol : row.instId;
    const match = (provider === 'binance' ? /^([A-Z0-9]+)USDT$/ : /^([A-Z0-9]+)-USDT$/).exec(String(pair));
    if (!match || !wanted.has(match[1])) continue;
    if (provider !== 'binance' && row.instType !== 'SPOT') throw new Error('wrong market');
    const price = decimal(provider === 'binance' ? row.lastPrice : row.last);
    const open = decimal(provider === 'binance' ? row.openPrice : row.open24h);
    const high = decimal(provider === 'binance' ? row.highPrice : row.high24h);
    const low = decimal(provider === 'binance' ? row.lowPrice : row.low24h);
    const turnover = decimal(provider === 'binance' ? row.quoteVolume : row.volCcy24h);
    const timestamp = provider === 'binance' ? row.closeTime : /^\d{13}$/.test(row.ts) ? Number(row.ts) : NaN;
    if (!(high >= Math.max(price,open)) || !(low > 0 && low <= Math.min(price,open)) || result[match[1]] || !(price > 0) || !(open > 0) || !(turnover >= 0) || !Number.isSafeInteger(timestamp) || timestamp <= 0) throw new Error('invalid ticker');
    const change = (price / open - 1) * 100;
    if (!Number.isFinite(change)) throw new Error('invalid change');
    result[match[1]] = {price,change,turnover,timestamp,high,low,amplitude:(high-low)/open*100};
  }
  return result;
}
export async function loadMarketTickers(venue,symbols,signal,request = fetch) {
  const provider = ({'币安':'binance','欧易OKX':'okx','Bitget':'bitget'})[venue];
  if (!provider || !Array.isArray(symbols) || symbols.length===0 || symbols.some(symbol=>!/^[A-Z0-9]{1,24}$/.test(symbol))) return {status:'unsupported',quotes:{},source:'该平台公开报价尚未接入'};
  const controller = new AbortController(), abort = () => controller.abort();
  const timer = setTimeout(abort,10000);
  signal?.addEventListener('abort',abort,{once:true});
  try {
    if (signal?.aborted) controller.abort();
    const single=symbols.length===1;
    const url = provider==='bitget'?`https://api.bitget.com/api/v2/spot/market/tickers${single?`?symbol=${symbols[0]}USDT`:''}`:provider === 'binance' ? `https://data-api.binance.vision/api/v3/ticker/24hr${single?`?symbol=${symbols[0]}USDT`:''}` : single?`https://www.okx.com/api/v5/market/ticker?instId=${symbols[0]}-USDT`:'https://www.okx.com/api/v5/market/tickers?instType=SPOT';
    const response = await request(url,{signal:controller.signal,credentials:'omit',redirect:'error',cache:'no-store'});
    if (!response.ok) return {status:'error',quotes:{},source:`公开报价失败（HTTP${response.status}）`};
    const payload=await response.json();
    const quotes = decodeMarketTickers(provider==='binance'&&single&&!Array.isArray(payload)?[payload]:payload,provider,symbols);
    return {status:'connected',quotes,source:`${venue}公开现货 · 24小时涨跌 · 30秒轮询 · ${new Date().toISOString()}`};
  } catch (error) {
    return {status:'error',quotes:{},source:error.name === 'AbortError'?'公开报价取消或超时':error instanceof TypeError?'公开报价网络或跨域失败':'公开报价响应无效'};
  } finally {clearTimeout(timer);signal?.removeEventListener('abort',abort);}
}
