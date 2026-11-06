export function getTerminalTradingContext(){
 if(typeof document==='undefined'||!document.documentElement.hasAttribute('data-terminal-feature'))return null;
 const value=window.TerminalFeatureContext;
 return value&&typeof value==='object'?value:{market:'unknown',executionMode:'READ_ONLY',contextVersion:-1};
}
export function tradingContextIdentity(context=getTerminalTradingContext()){
 return context?JSON.stringify([context.market,context.instrumentId,context.venue,context.chainId,context.contractAddress,context.accountId,context.walletId,context.executionMode,context.contextVersion,context.authorizationVersion,context.accountVerified,context.paperEligible,context.identityUserId]):null;
}
export function paperEditingAllowed(context=getTerminalTradingContext()){return context===null||(context.executionMode==='PAPER'&&['stocks','cex'].includes(context.market)&&Boolean(context.accountId)&&context.accountVerified===true&&context.paperEligible===true);}
export function terminalAssetMatches(asset,context){
 if(!context)return true;
 const alias={币安:'BINANCE',欧易:'OKX',火币:'HTX','GATE.IO':'GATE'};
 const venue=value=>alias[value]||alias[String(value||'').toUpperCase()]||String(value||'').toUpperCase();
 const target=String(context.instrumentId||'').toUpperCase(),symbol=String(asset.symbol||'').toUpperCase();
 if(context.market==='stocks')return ['stock','etf'].includes(asset.asset_type)&&symbol===target&&(context.venue==='全部美股'?['NASDAQ','NYSE'].includes(venue(asset.venue)):venue(asset.venue)===venue(context.venue));
 if(context.market!=='cex'||!['crypto','crypto_spot'].includes(asset.asset_type))return false;
 const [base,quote]=target.split('/'),[assetBase,assetQuote]=symbol.split('/');
 return Boolean(quote)&&base===assetBase&&quote===(assetQuote||String(asset.currency||'').toUpperCase())&&venue(asset.venue)===venue(context.venue);
}
export function assertTerminalTradeRequest(path,options={},context=getTerminalTradingContext()){
 const method=String(options.method||'GET').toUpperCase();if(['GET','HEAD','OPTIONS'].includes(method)||context===null)return;
 const pathname=String(path).split('?')[0];
 if(/^\/(live-execution|controlled-auto)(\/|$)/.test(pathname)||pathname==='/kill-switch/disengage')throw Object.assign(Error('新终端未开放实盘或自动执行。'),{local:true,code:'terminal_live_disabled'});
 const trading=/^\/(orders|paper-executions|decision-gates|risk\/check-order|production\/broker-sandbox)(\/|$)/.test(pathname);
 if(trading&&!paperEditingAllowed(context))throw Object.assign(Error('当前工作区为只读；请明确选择Paper模式后重新核对票据。'),{local:true,code:'terminal_read_only'});
 if(trading&&options.body?.account_id&&options.body.account_id!==context.accountId)throw Object.assign(Error('票据账户与当前工作区不一致，请重新选择并核对。'),{local:true,code:'terminal_account_mismatch'});
}
