const cryptoSymbols=['BTC','ETH','SOL','PEPE'];
export function strategyWorkbenchView(context){
 if(!context)return {scope:'legacy',symbol:'BTC',symbols:cryptoSymbols};
 const symbol=String(context.instrumentId||'').split('/')[0];
 const scope=JSON.stringify([context.identityUserId,context.market,context.accountId,context.walletId,context.chainId,context.contractAddress,context.venue,context.instrumentId]);
 const symbols=context.market==='cex'?cryptoSymbols:context.market==='stocks'?['AAPL','MSFT','NVDA']:[];
 return {scope,symbol,symbols:[...new Set([symbol,...symbols])]};
}
export function strategySelectionPatch(context,symbol){
 if(!context)return null;
 if(typeof symbol!=='string'||!/^[-A-Z0-9._]{1,32}$/.test(symbol))throw Error('策略标的格式无效');
 if(context.market==='onchain')throw Error('链上标的需在顶部按链与合约选择，不能用交易所币种替代。');
 if(context.market==='stocks'){
  if(!strategyWorkbenchView(context).symbols.includes(symbol))throw Error('此模板标的不属于当前股票选择，请在顶部选择股票后重试。');
  return {instrumentId:symbol};
 }
 if(context.market!=='cex')throw Error('当前市场不可选择此策略标的');
 const parts=String(context.instrumentId||'').split('/');
 if(parts.length!==2||!parts[1])throw Error('请先在顶部填写完整交易对，以便保留正确计价币种。');
 return {instrumentId:symbol+'/'+parts[1]};
}
