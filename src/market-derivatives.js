const decimal=(value,signed=false)=>typeof value==='string'&&(signed?/^-?\d+(?:\.\d+)?$/:/^\d+(?:\.\d+)?$/).test(value)&&Number.isFinite(Number(value))?Number(value):NaN;
const timestamp=value=>typeof value==='string'&&/^\d{13}$/.test(value)?Number(value):NaN;
const row=(body,instId)=>{
 if(body?.code!=='0'||!Array.isArray(body.data)||body.data.length!==1||body.data[0]?.instId!==instId||body.data[0].instType!=='SWAP')throw new Error('contract identity');
 return body.data[0];
};
export function decodeOkxDerivatives(funding,interest,symbol){
 const instId=`${symbol}-USDT-SWAP`,f=row(funding,instId),oi=row(interest,instId);
 const rate=decimal(f.fundingRate,true),fundingTime=timestamp(f.fundingTime),fundingUpdatedAt=timestamp(f.ts),interestUpdatedAt=timestamp(oi.ts);
 const contracts=decimal(oi.oi),baseQuantity=decimal(oi.oiCcy),usdValue=decimal(oi.oiUsd);
 if(![rate,fundingTime,fundingUpdatedAt,interestUpdatedAt,contracts,baseQuantity,usdValue].every(Number.isFinite)||contracts<0||baseQuantity<0||usdValue<0)throw new Error('contract values');
 return {instId,rate,fundingTime,fundingUpdatedAt,interestUpdatedAt,contracts,baseQuantity,usdValue};
}
export function decodeBitgetDerivatives(funding,interest,symbol){
 const instId=`${symbol}USDT`;
 if(funding?.code!=='00000'||interest?.code!=='00000'||!Array.isArray(funding.data)||funding.data.length!==1||funding.data[0]?.symbol!==instId||!Array.isArray(interest.data?.list)||interest.data.list.length!==1||interest.data.list[0]?.symbol!==instId)throw new Error('contract identity');
 const f=funding.data[0],oi=interest.data.list[0],rate=decimal(f.fundingRate,true),fundingTime=timestamp(f.nextUpdate),interestUpdatedAt=timestamp(interest.data.ts),baseQuantity=decimal(oi.openInterest);
 if(![rate,fundingTime,interestUpdatedAt,baseQuantity].every(Number.isFinite)||baseQuantity<0||!Number.isSafeInteger(funding.requestTime)||funding.requestTime<=0||!['1','2','4','8'].includes(f.fundingRateInterval))throw new Error('contract values');
 return {instId:`${instId} USDT永续`,rate,fundingTime,fundingUpdatedAt:funding.requestTime,fundingTimestampKind:'请求时间',interestUpdatedAt,baseQuantity,contracts:null,usdValue:null,intervalHours:Number(f.fundingRateInterval),interestBasis:'平台返回多头与空头持仓之和，基础币单位'};
}
export function decodeBinanceDerivatives(funding,interest,info,symbol){
 const pair=`${symbol}USDT`;
 if(!Array.isArray(info?.symbols)||info.symbols.length>10000)throw new Error('contract info');
 const matches=info.symbols.filter(row=>row.symbol===pair),instrument=matches[0];
 if(matches.length!==1||instrument.contractType!=='PERPETUAL'||instrument.status!=='TRADING'||instrument.baseAsset!==symbol||instrument.quoteAsset!=='USDT'||instrument.marginAsset!=='USDT'||funding?.symbol!==pair||interest?.symbol!==pair)throw new Error('contract identity');
 const rate=decimal(funding.lastFundingRate,true),baseQuantity=decimal(interest.openInterest);
 if(![rate,baseQuantity].every(Number.isFinite)||baseQuantity<0||![funding.time,funding.nextFundingTime,interest.time].every(value=>Number.isSafeInteger(value)&&value>0&&value<=253402300799999))throw new Error('contract values');
 return {instId:`${pair} USDT永续`,rate,rateLabel:'最近资金费率',fundingTime:funding.nextFundingTime,fundingUpdatedAt:funding.time,interestUpdatedAt:interest.time,baseQuantity,contracts:null,usdValue:null,interestBasis:'币安USDT永续返回基础币持仓量；最近资金费率不表示下一期预测'};
}
export async function loadPublicDerivatives(symbol,venue,signal,request=fetch){
 if(!/^[A-Z0-9]{1,24}$/.test(symbol)||!['币安','欧易OKX','Bitget'].includes(venue))return {status:'unsupported',source:'该平台USDT永续公开数据尚未接入'};
 const controller=new AbortController(),abort=()=>controller.abort(),timer=setTimeout(abort,10000);signal?.addEventListener('abort',abort,{once:true});
 try{
   if(signal?.aborted)controller.abort();
   const instId=`${symbol}-USDT-SWAP`,config={signal:controller.signal,credentials:'omit',redirect:'error',cache:'no-store'};
   const paths=venue==='币安'?[`premiumIndex?symbol=${symbol}USDT`,`openInterest?symbol=${symbol}USDT`,'exchangeInfo']:venue==='Bitget'?[`current-fund-rate?category=USDT-FUTURES&symbol=${symbol}USDT`,`open-interest?category=USDT-FUTURES&symbol=${symbol}USDT`]:[`funding-rate?instId=${instId}`,`open-interest?instType=SWAP&instId=${instId}`];
   const origin=venue==='币安'?'https://fapi.binance.com/fapi/v1/':venue==='Bitget'?'https://api.bitget.com/api/v3/market/':'https://www.okx.com/api/v5/public/';
   const responses=await Promise.all(paths.map(path=>request(`${origin}${path}`,config)));
   if(responses.some(response=>!response.ok))return {status:'error',source:`${venue}永续公开数据请求失败`};
   const values=await Promise.all(responses.map(response=>response.json()));
   return {status:'connected',...(venue==='币安'?decodeBinanceDerivatives(...values,symbol):venue==='Bitget'?decodeBitgetDerivatives(...values,symbol):decodeOkxDerivatives(...values,symbol)),source:`${venue} ${venue!=='欧易OKX'?`${symbol}USDT USDT永续`:instId} 公开永续快照 · 30秒轮询 · 获取于 ${new Date().toISOString()}`};
 }catch(error){return {status:'error',source:error.name==='AbortError'?'永续公开数据取消或超时':error instanceof TypeError?'永续公开数据网络或跨域失败':'永续公开数据身份或字段校验失败'};}
 finally{clearTimeout(timer);signal?.removeEventListener('abort',abort);}
}
