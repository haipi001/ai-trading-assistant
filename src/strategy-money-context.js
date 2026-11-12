const currency=value=>typeof value==='string'&&/^[A-Z0-9]{2,12}$/.test(value)?value:null;
export function strategyMoneyContext(symbol,context){
 if(!context)return {instrument:symbol+'/USDT',budgetCurrency:'USDT',quoteCurrency:'USDT',legacy:true};
 if(context.market==='stocks')return {instrument:symbol,budgetCurrency:context.accountVerified?currency(context.accountCurrency):null,quoteCurrency:null,legacy:false};
 if(context.market==='cex'){
  const pair=String(context.instrumentId||'').split('/'),quote=pair.length===2?currency(pair[1]):null;
  return {instrument:quote?symbol+'/'+quote:symbol,budgetCurrency:quote,quoteCurrency:quote,legacy:false};
 }
 return {instrument:symbol,budgetCurrency:null,quoteCurrency:null,legacy:false};
}
