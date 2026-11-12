export function strategyDraftScope(embedded,context){
 if(!embedded)return 'ai-trading-assistant-strategies';
 if(!context?.identityUserId||!['stocks','cex','onchain'].includes(context.market))return null;
 return 'terminal-strategy-drafts-v1:'+JSON.stringify([context.identityUserId,context.market,context.accountId||'',context.walletId||'',context.chainId||'',context.venue||'']);
}
export function readStrategyDrafts(storage,key,initialValue=[]){
 if(!key)return [];
 try {const raw=storage.getItem(key);if(raw==null)return structuredClone(initialValue);const value=JSON.parse(raw);return Array.isArray(value)?value:[];}catch{return [];}
}

export function strategyStorageKey(namespace,embedded,context){
 if(!embedded)return namespace;
 const scope=strategyDraftScope(true,context);
 return scope?(namespace==='ai-trading-assistant-strategies'?scope:namespace+':'+scope):null;
}
