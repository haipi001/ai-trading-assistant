const numeric = value => typeof value==='string' && /^\d+(?:\.\d+)?$/.test(value) && Number.isFinite(Number(value)) && Number(value)>0 ? Number(value) : NaN;
export function decodeMarketDepth(body,provider) {
  const data = provider==='binance'?body:provider==='bitget'?body?.code==='00000'?body.data:null:body?.code==='0'&&Array.isArray(body.data)&&body.data.length===1?body.data[0]:null;
  if(!data)throw new Error('shape');
  const snapshotTime=provider!=='binance'?typeof data.ts==='string'&&/^\d{13}$/.test(data.ts)?Number(data.ts):NaN:null;
  if(provider!=='binance'&&!Number.isSafeInteger(snapshotTime))throw new Error('timestamp');
  const parse=(rows,descending)=>{
    if(!Array.isArray(rows)||rows.length>20)throw new Error('shape');
    const seen=new Set();
    let total=0;
    return rows.map(row=>{
      if(!Array.isArray(row)||row.length<2)throw new Error('shape');
      const price=numeric(row[0]),quantity=numeric(row[1]);
      if(!Number.isFinite(price)||!Number.isFinite(quantity)||seen.has(price))throw new Error('level');
      seen.add(price);return {price,quantity};
    }).sort((a,b)=>descending?b.price-a.price:a.price-b.price).slice(0,9).map(row=>{
      total+=row.quantity;if(!Number.isFinite(total))throw new Error('total');return {...row,total};
    });
  };
  const asks=parse(data.asks,false),bids=parse(data.bids,true);
  if(asks.length&&bids.length&&asks[0].price<=bids[0].price)throw new Error('crossed book');
  return {asks,bids,snapshotTime};
}
export async function loadMarketDepth(symbol,venue,signal,request=fetch) {
  const provider=({'币安':'binance','欧易OKX':'okx','Bitget':'bitget'})[venue];
  if(!provider || !/^[A-Z0-9]{1,24}$/.test(symbol))return {status:'unsupported',source:'该标的或平台公开现货盘口尚未接入',asks:[],bids:[]};
  const controller=new AbortController(),abort=()=>controller.abort(),timer=setTimeout(abort,10000);
  signal?.addEventListener('abort',abort,{once:true});
  try {
    if(signal?.aborted)controller.abort();
    const url=provider==='bitget'?`https://api.bitget.com/api/v2/spot/market/orderbook?symbol=${symbol}USDT&type=step0&limit=20`:provider==='binance'?`https://data-api.binance.vision/api/v3/depth?symbol=${symbol}USDT&limit=20`:`https://www.okx.com/api/v5/market/books?instId=${symbol}-USDT&sz=20`;
    const response=await request(url,{signal:controller.signal,credentials:'omit',redirect:'error',cache:'no-store'});
    if(!response.ok)return {status:'error',source:`盘口读取失败（HTTP${response.status}）`,asks:[],bids:[]};
    const depth=decodeMarketDepth(await response.json(),provider);
    return {status:'connected',...depth,source:`${venue} ${symbol}/USDT 现货盘口快照 · 30秒轮询${depth.snapshotTime?` · 交易所时间 ${new Date(depth.snapshotTime).toISOString()}`:""} · 获取于 ${new Date().toISOString()}`};
  } catch(error) {
    return {status:'error',asks:[],bids:[],source:error.name==='AbortError'?'盘口已取消或超时':error instanceof TypeError?'盘口网络或跨域失败':'盘口响应无效'};
  } finally {clearTimeout(timer);signal?.removeEventListener('abort',abort);}
}
