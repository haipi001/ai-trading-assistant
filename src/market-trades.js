const decimal=value=>typeof value==='string'&&/^\d+(?:\.\d+)?$/.test(value)&&Number.isFinite(Number(value))&&Number(value)>0?Number(value):NaN;
export function decodeMarketTrades(body,provider,symbol) {
  if(provider==='bitget') {
    if(body?.code!=='00000'||!Array.isArray(body.data)||body.data.length>20)throw new Error('shape');
    if(body.data.some(row=>row.symbol!==`${symbol}USDT`))throw new Error('identity');
    return decodeMarketTrades({code:'0',data:body.data.map(row=>({instId:`${symbol}-USDT`,tradeId:row.tradeId,px:row.price,sz:row.size,ts:row.ts,side:row.side}))},'okx',symbol);
  }

  const rows=provider==='binance'?body:body?.code==='0'?body.data:null;
  if(!Array.isArray(rows)||rows.length>20)throw new Error('shape');
  const ids=new Set();
  return rows.map(row=>{
    if(provider!=='binance'&&row.instId!==`${symbol}-USDT`)throw new Error('identity');
    const id=provider==='binance'?Number.isSafeInteger(row.id)&&row.id>=0?String(row.id):null:typeof row.tradeId==='string'&&/^\d+$/.test(row.tradeId)?row.tradeId:null;
    const time=provider==='binance'?row.time:typeof row.ts==='string'&&/^\d{13}$/.test(row.ts)?Number(row.ts):NaN;
    const price=decimal(provider==='binance'?row.price:row.px),quantity=decimal(provider==='binance'?row.qty:row.sz);
    const side=provider==='binance'?typeof row.isBuyerMaker==='boolean'?row.isBuyerMaker?'卖出':'买入':null:row.side==='buy'?'买入':row.side==='sell'?'卖出':null;
    if(id===null||ids.has(id)||!Number.isSafeInteger(time)||time<=0||time>253402300799999||!Number.isFinite(price)||!Number.isFinite(quantity)||!side)throw new Error('trade');
    ids.add(id);return {id,time,price,quantity,side};
  }).sort((a,b)=>b.time-a.time);
}
export async function loadMarketTrades(symbol,venue,signal,request=fetch) {
  const provider=({'币安':'binance','欧易OKX':'okx','Bitget':'bitget'})[venue];
  if(!provider||!/^[A-Z0-9]{1,24}$/.test(symbol))return {status:'unsupported',trades:[],source:'该平台或标的公开现货成交尚未接入'};
  const controller=new AbortController(),abort=()=>controller.abort(),timer=setTimeout(abort,10000);
  signal?.addEventListener('abort',abort,{once:true});
  try {
    if(signal?.aborted)controller.abort();
    const url=provider==='bitget'?`https://api.bitget.com/api/v2/spot/market/fills?symbol=${symbol}USDT&limit=20`:provider==='binance'?`https://data-api.binance.vision/api/v3/trades?symbol=${symbol}USDT&limit=20`:`https://www.okx.com/api/v5/market/trades?instId=${symbol}-USDT&limit=20`;
    const response=await request(url,{signal:controller.signal,credentials:'omit',redirect:'error',cache:'no-store'});
    if(!response.ok)return {status:'error',trades:[],source:`公开成交读取失败（HTTP${response.status}）`};
    return {status:'connected',trades:decodeMarketTrades(await response.json(),provider,symbol),source:`${venue} ${symbol}/USDT 最近20笔公开现货成交 · 30秒轮询 · 获取于 ${new Date().toISOString()}`};
  } catch(error) {
    return {status:'error',trades:[],source:error.name==='AbortError'?'公开成交已取消或超时':error instanceof TypeError?'公开成交网络或跨域失败':'公开成交响应无效'};
  } finally {clearTimeout(timer);signal?.removeEventListener('abort',abort);}
}
