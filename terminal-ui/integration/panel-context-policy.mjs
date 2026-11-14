export function selectPanelContext({current,locked,retained,supportedMarkets=[]}){
 const supported=!supportedMarkets.length||supportedMarkets.includes(current?.market);
 const context=locked||(!supported?retained:null)||current;
 if(!context)return null;
 const compatible=current&&context.market===current.market&&context.accountId===current.accountId&&context.walletId===current.walletId;
 return {...context,executionMode:compatible&&current.executionMode==='PAPER'?'PAPER':'READ_ONLY',authorizationVersion:current?.contextVersion,marketRetained:!locked&&!supported&&Boolean(retained)};
}
