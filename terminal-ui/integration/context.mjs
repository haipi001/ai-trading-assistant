export const MARKETS = Object.freeze({stocks:{label:'股票 / ETF',instrumentId:'AAPL',venue:'NASDAQ',chainId:null},cex:{label:'加密 CEX',instrumentId:'BTC/USDT',venue:'币安',chainId:null},onchain:{label:'Web3 链上',instrumentId:'',venue:'',chainId:'1'}});
const clean = (value,max=128) => typeof value==='string'?value.trim().slice(0,max):'';
export function marketContext(market, saved={}) {
 if(!MARKETS[market])throw Error('invalid_market');
 const defaults=MARKETS[market];
 const timeframe=clean(saved.timeframe)||'1D';
 if(!/^[1-9][0-9]{0,3}(S|M|H|D|W|MO)$/.test(timeframe))throw Error('invalid_timeframe');
 if(market==='onchain'){
  if(saved.contractAddress&&!/^0x[0-9a-fA-F]{40}$/.test(saved.contractAddress))throw Error('invalid_contract_address');
  if(saved.chainId&&!/^[1-9][0-9]{0,19}$/.test(saved.chainId))throw Error('invalid_chain_id');
 }

 return {market,instrumentId:clean(saved.instrumentId)||defaults.instrumentId,venue:clean(saved.venue)||defaults.venue,chainId:market==='onchain'?(clean(saved.chainId)||'1'):null,contractAddress:market==='onchain'?clean(saved.contractAddress):'',accountId:clean(saved.accountId),walletId:market==='onchain'?clean(saved.walletId):'',timeframe,executionMode:'READ_ONLY',contextVersion:0};
}
export function switchMarket(state, market) {
 if(!MARKETS[market])throw Error('invalid_market');
 const memories={...state.memories,[state.current.market]:{...state.current}};
 const current=marketContext(market,memories[market]);
 current.contextVersion=state.current.contextVersion+1;
 return {current,memories};
}
export function updateContext(state, patch) {
 const permitted=['instrumentId','venue','chainId','contractAddress','accountId','walletId','timeframe'];
 const values={...state.current}; for(const k of permitted)if(k in patch)values[k]=clean(patch[k]);
 if(values.market==='onchain'&&values.contractAddress&&!/^0x[0-9a-fA-F]{40}$/.test(values.contractAddress))throw Error('invalid_contract_address');
 if(values.market==='onchain'&&!/^\d+$/.test(values.chainId))throw Error('invalid_chain_id');
 const current=marketContext(values.market,values);current.contextVersion=state.current.contextVersion+1;
 const mode=patch.executionMode??state.current.executionMode;
 if(!['READ_ONLY','PAPER'].includes(mode))throw Error('live_mode_not_available');
 if(mode==='PAPER'&&current.market==='onchain')throw Error('onchain_read_only');
 const accountChanged=current.accountId!==state.current.accountId||current.walletId!==state.current.walletId;
 current.executionMode=accountChanged?'READ_ONLY':mode;
 return {...state,current};
}
export function initialState(raw) {
 try { const parsed=JSON.parse(raw);const market=parsed.current.market;const memories={};for(const key of Object.keys(MARKETS))if(parsed.memories?.[key])memories[key]=marketContext(key,parsed.memories[key]);return {current:marketContext(market,parsed.current),memories}; }catch{return {current:marketContext('stocks'),memories:{}};}
}
