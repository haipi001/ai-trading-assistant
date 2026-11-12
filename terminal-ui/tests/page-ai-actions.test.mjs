import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {pageAIPolicy,preparePageAIAction,validatePageAIIntent,pageAIReadiness,pageAIMarketMatches,PAGE_AI_SOURCES,PAGE_AI_ARTIFACT_LABELS} from '../integration/page-ai-actions.mjs';
const scope={window:{}};vm.runInNewContext(readFileSync(new URL('../integration/registry.js',import.meta.url),'utf8'),scope);
const features=scope.window.TERMINAL_FEATURES;
const chart=features.find(row=>row.code==='R009'),news=features.find(row=>row.code==='R014');
const context={panelId:'main:R009',market:'stocks',instrumentId:'AAPL',venue:'NASDAQ',accountId:'account-a',walletId:'',chainId:null,contractAddress:'',timeframe:'1D',executionMode:'READ_ONLY',contextVersion:7};
test('all 68 migrated pages retain individual data/output/failure/destination contracts',()=>{
 assert.equal(features.length,68);const ids=new Set(),codes=new Set(features.map(row=>row.code));
 for(const feature of features){
  const policy=pageAIPolicy(feature);assert.deepEqual(JSON.parse(JSON.stringify(feature.aiActionContracts)),policy.actions);
  assert.equal(feature.aiPolicyVersion,1);assert.equal(feature.aiActionContracts.length,3);
  for(const action of policy.actions){assert.ok(!ids.has(action.id));ids.add(action.id);assert.ok(codes.has(action.destination));assert.ok(action.artifact&&action.implementedArtifact&&PAGE_AI_ARTIFACT_LABELS[action.artifact]);assert.ok(action.failureStates.includes('data_missing'));assert.ok(action.label.includes(feature.label));for(const source of action.requiredSources)assert.ok(PAGE_AI_SOURCES[source]);}
 }
 assert.equal(ids.size,204);
});
test('an existing UI component does not imply its private data is bound to AI',()=>{
 for(const code of ['R010','R047','R050','R051','STR4']){
  const feature=features.find(row=>row.code===code),policy=pageAIPolicy(feature);
  assert.equal(policy.actions[0].availability,'adapter_unavailable');
  assert.throws(()=>preparePageAIAction(feature,code+'.analysis',context),/adapter_unavailable/);
  const gaps=preparePageAIAction(feature,code+'.gaps',context);
  assert.deepEqual(gaps.requiredSources,[]);assert.equal(gaps.executionAvailable,false);assert.equal(gaps.autoSubmit,false);
 }
});
test('prepared actions are immutable and cannot cross account, venue, version or panel boundaries',()=>{
 const prepared=preparePageAIAction(chart,'R009.analysis',context);
 assert.ok(Object.isFrozen(prepared)&&Object.isFrozen(prepared.context));
 assert.equal(validatePageAIIntent(prepared,chart,context).actionId,'R009.analysis');
 for(const patch of [{panelId:'1:R009'},{accountId:'account-b'},{instrumentId:'MSFT'},{venue:'Other'},{timeframe:'1H'},{contextVersion:8},{executionMode:'PAPER'}])assert.throws(()=>validatePageAIIntent(prepared,chart,{...context,...patch}));
 assert.throws(()=>validatePageAIIntent(prepared,news,context));
 assert.throws(()=>validatePageAIIntent({...prepared,requiredSources:[]},chart,context),/contract_mismatch/);
 assert.throws(()=>validatePageAIIntent({...prepared,autoSubmit:true},chart,context));
});
test('required evidence cannot be unchecked while retaining a page action',()=>{
 const prepared=preparePageAIAction(chart,'R009.analysis',context);
 assert.ok(pageAIReadiness(prepared,{context}));
 assert.ok(pageAIReadiness(prepared,{context,includeMarket:true,marketCapture:null}));
 assert.equal(pageAIReadiness(prepared,{context,includeMarket:true,marketCapture:{symbol:'AAPL',venue:'NASDAQ',timeframe:'1d',market_type:'stock',quote_currency:'USD',data_semantics:'raw_ohlcv',kind:'online',source_label:'Public data',bars:[{}]}}),'');
 const n=preparePageAIAction(news,'R014.analysis',context);
 assert.ok(pageAIReadiness(n,{context,includeNews:true,newsReady:false}));
 assert.equal(pageAIReadiness(n,{context,includeNews:true,newsReady:true}),'');
});
test('wallet evidence stays read-only, requires an explicit attachment, and cannot use stock context',()=>{
 const feature=features.find(row=>row.code==='R056');
 assert.throws(()=>preparePageAIAction(feature,'R056.analysis',context),/market_incompatible/);
 const chain={...context,market:'onchain',chainId:'8453',walletId:'wallet-a',instrumentId:'',accountId:''};
 const prepared=preparePageAIAction(feature,'R056.analysis',chain);
 assert.ok(pageAIReadiness(prepared,{context:chain,includeOnchain:true,onchainValid:false}));
 assert.equal(pageAIReadiness(prepared,{context:chain,includeOnchain:true,onchainValid:true}),'');
 assert.throws(()=>preparePageAIAction(feature,'R056.analysis',{...chain,executionMode:'PAPER'}));
});
test('native simulated chart action directs to a business page instead of accepting demo quotes',()=>{
 const feature={code:'GP',page:'terminal',tab:'Price chart',label:'Price chart'},policy=pageAIPolicy(feature);
 assert.equal(policy.actions[0].availability,'business_panel_required');assert.equal(policy.actions[0].destination,'R009');
 assert.throws(()=>preparePageAIAction(feature,'GP.analysis',context),/business_panel_required/);
 const gaps=preparePageAIAction(feature,'GP.gaps',context);assert.deepEqual(gaps.requiredSources,[]);
 assert.ok(Object.values(PAGE_AI_SOURCES).every(source=>source.reads.every(field=>!/secret|password|private_key|api_key|signature/.test(field))));
});

test('page actions cannot accept a stale chart from another symbol, venue or timeframe',()=>{
 const capture={symbol:'AAPL',venue:'NASDAQ',timeframe:'1d',market_type:'stock',quote_currency:'USD',data_semantics:'raw_ohlcv',kind:'online',source_label:'Public data',bars:[{}]};
 assert.equal(pageAIMarketMatches(capture,context),true);
 for(const patch of [{symbol:'MSFT'},{venue:'NYSE'},{timeframe:'1h'},{market_type:'spot'},{source_label:'demo prices'},{bars:[]}])assert.equal(pageAIMarketMatches({...capture,...patch},context),false);
});

test('data-gap actions cannot silently acquire materials beyond their declared read scope',()=>{const plan=preparePageAIAction(chart,'R009.gaps',context);assert.equal(pageAIReadiness(plan,{context}),'');for(const patch of [{includeMarket:true},{includeNews:true},{includeOnchain:true}])assert.ok(pageAIReadiness(plan,{context,...patch}));});

test('previous-context page actions remain blocked until explicitly replaced or cleared',()=>{const plan=preparePageAIAction(chart,'R009.analysis',context);assert.match(pageAIReadiness(plan,{context:{...context,accountId:'next-account'}}),/此前上下文/);assert.equal(pageAIReadiness(null,{context:{...context,accountId:'next-account'}}),'');assert.equal(plan.context.accountId,'account-a');});

test('DEX copy research is onchain/read-only while CEX copy and stock tracking retain their markets',()=>{const chain={...context,market:'onchain',chainId:'1',accountId:'',walletId:'wallet-a'};const dex=features.find(row=>row.code==='STR6');assert.deepEqual(pageAIPolicy(dex).supportedMarkets,['onchain']);assert.equal(preparePageAIAction(dex,'STR6.gaps',chain).executionAvailable,false);assert.throws(()=>preparePageAIAction(dex,'STR6.gaps',context),/market_incompatible/);assert.deepEqual(pageAIPolicy(features.find(row=>row.code==='STR5')).supportedMarkets,['cex']);assert.deepEqual(pageAIPolicy(features.find(row=>row.code==='STR8')).supportedMarkets,['stocks']);});

test('portfolio actions require owned ledger selection and cannot be used as onchain balances',()=>{const feature=features.find(row=>row.code==='R045');const plan=preparePageAIAction(feature,'R045.analysis',context);assert.deepEqual(plan.requiredSources,['portfolio']);assert.ok(pageAIReadiness(plan,{context}));assert.equal(pageAIReadiness(plan,{context,includePortfolio:true,portfolioValid:true}),'');assert.ok(pageAIReadiness(plan,{context,includePortfolio:true,portfolioValid:false}));assert.throws(()=>preparePageAIAction(feature,'R045.analysis',{...context,market:'onchain',chainId:'1'}));});
