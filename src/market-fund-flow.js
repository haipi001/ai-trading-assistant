export const FLOW_PERIODS=['15m','30m','1h','2h','4h','1d'];
export function decodeBitgetFundFlow(body){
 if(body?.code!=='00000'||!body.data||Array.isArray(body.data)||!Number.isSafeInteger(body.requestTime)||body.requestTime<=0)throw new Error('flow shape');
 const number=value=>typeof value==='string'&&/^\d+(?:\.\d+)?$/.test(value)&&Number.isFinite(Number(value))?Number(value):NaN;
 const groups=['whale','dolphin','fish'].map(group=>{
   const buy=number(body.data[`${group}BuyVolume`]),sell=number(body.data[`${group}SellVolume`]);
   if(!Number.isFinite(buy)||!Number.isFinite(sell))throw new Error('flow quantity');
   return {group,buy,sell,net:buy-sell};
 });
 const buy=groups.reduce((sum,row)=>sum+row.buy,0),sell=groups.reduce((sum,row)=>sum+row.sell,0);
 if(!Number.isFinite(buy)||!Number.isFinite(sell))throw new Error('flow total');
 return {groups,buy,sell,net:buy-sell,requestTime:body.requestTime};
}
export async function loadPublicFundFlow(symbol,venue,period,signal,request=fetch){
 if(venue!=='Bitget'||!/^[A-Z0-9]{1,24}$/.test(symbol)||!FLOW_PERIODS.includes(period))return {status:'unsupported',source:'该平台或周期的公开资金流尚未接入'};
 const controller=new AbortController(),abort=()=>controller.abort(),timer=setTimeout(abort,10000);signal?.addEventListener('abort',abort,{once:true});
 try{
   if(signal?.aborted)controller.abort();
   const response=await request(`https://api.bitget.com/api/v3/market/spot-fund-flow?symbol=${symbol}USDT&period=${period}`,{signal:controller.signal,credentials:'omit',redirect:'error',cache:'no-store'});
   if(!response.ok)return {status:'error',source:`公开资金流读取失败（HTTP${response.status}）`};
   return {status:'connected',...decodeBitgetFundFlow(await response.json()),source:`Bitget ${symbol}USDT 现货资金流 · ${period} · 30秒轮询`};
 }catch(error){return {status:'error',source:error.name==='AbortError'?'公开资金流取消或超时':error instanceof TypeError?'公开资金流网络或跨域失败':'公开资金流字段校验失败'};}
 finally{clearTimeout(timer);signal?.removeEventListener('abort',abort);}
}
