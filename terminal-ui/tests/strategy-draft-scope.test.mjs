import test from 'node:test';
import assert from 'node:assert/strict';
import {strategyDraftScope,readStrategyDrafts} from '../../src/strategy-draft-scope.js';
test('terminal strategies use distinct user, market and account stores without adopting legacy drafts',()=>{
 const c={identityUserId:'a',market:'cex',accountId:'one',venue:'mock'};
 const key=strategyDraftScope(true,c);
 for(const patch of [{identityUserId:'b'},{market:'stocks'},{accountId:'two'},{venue:'other'}])assert.notEqual(strategyDraftScope(true,{...c,...patch}),key);
 assert.equal(strategyDraftScope(true,{market:'cex'}),null);
 assert.equal(strategyDraftScope(false,c),'ai-trading-assistant-strategies');
 const store={getItem:k=>k==='ai-trading-assistant-strategies'?'[{"id":"legacy"}]':null};
 assert.deepEqual(readStrategyDrafts(store,key),[]);assert.equal(readStrategyDrafts(store,strategyDraftScope(false,c))[0].id,'legacy');
});

test('specialist workbench namespaces isolate records while retaining the existing terminal draft key',async()=>{
 const {strategyStorageKey}=await import('../../src/strategy-draft-scope.js');
 const c={identityUserId:'a',market:'cex',accountId:'one',venue:'mock'};
 assert.equal(strategyStorageKey('ai-trading-assistant-strategies',true,c),strategyDraftScope(true,c));
 for(const namespace of ['grid','spot-dca','futures-dca','indicator','quick-orders','copy-cex','copy-dex']){
  assert.notEqual(strategyStorageKey(namespace,true,c),strategyStorageKey(namespace,true,{...c,accountId:'two'}));
  assert.notEqual(strategyStorageKey(namespace,true,c),strategyStorageKey(namespace,true,{...c,identityUserId:'b'}));
  assert.equal(strategyStorageKey(namespace,false,c),namespace);
  assert.equal(strategyStorageKey(namespace,true,{}),null);
 }
});
