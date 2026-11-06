export function workspaceSaveBody(context, version, agentOpen=false) {
  const keys=['page','tab','asset_class','symbol','venue','timeframe','source','account_id','mode'];
  return {expected_version:version,context:Object.fromEntries(keys.map(key=>[key,context[key]??null])),layout:{agent_open:agentOpen,density:'standard'}};
}
export function workspaceRestorePlan(packet) {
  const context=packet?.context;
  if (!context||!['home','market','flash','news','strategy','chain','assets','auth','data','more'].includes(context.page)) throw Error('工作区页面不受支持');
  if (context.account_id||context.mode) throw Error('该工作区包含交易账户或执行模式，请在账户工作流中单独确认');
  let period=null;
  if(context.timeframe){const match=/^([1-9]\d{0,3})(s|m|h|d|wk|mo|y)$/.exec(context.timeframe);if(!match)throw Error('工作区周期不受支持');period=match[2]==='y'?`${Number(match[1])*12}月`:`${match[1]}${{s:'秒',m:'分',h:'时',d:'日',wk:'周',mo:'月'}[match[2]]}`;}
  const stocks=['stock','etf'].includes(context.asset_class);
  if(context.venue&&!(stocks?['NASDAQ','NYSE','全部美股']:['币安','欧易OKX','Hyperliquid','Bitget']).includes(context.venue))throw Error('工作区平台不受支持');
  return {...context,period,marketMode:stocks?'stocks':'web3',agentOpen:packet.layout?.agent_open===true};
}
