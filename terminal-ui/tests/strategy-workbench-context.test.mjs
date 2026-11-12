import test from 'node:test';
import assert from 'node:assert/strict';
import {strategyWorkbenchView,strategySelectionPatch} from '../../src/strategy-workbench-context.js';
test('strategy selector follows stocks and preserves the exact CEX quote without switching accounts',()=>{
 const stocks={market:'stocks',instrumentId:'TSLA',accountId:'stocks',identityUserId:'owner'};
 assert.equal(strategyWorkbenchView(stocks).symbol,'TSLA');assert.ok(!strategyWorkbenchView(stocks).symbols.includes('BTC'));
 assert.deepEqual(strategySelectionPatch(stocks,'AAPL'),{instrumentId:'AAPL'});
 assert.throws(()=>strategySelectionPatch(stocks,'BTC'));
 const cex={market:'cex',instrumentId:'ETH/BTC',accountId:'cex'};
 assert.deepEqual(strategySelectionPatch(cex,'SOL'),{instrumentId:'SOL/BTC'});
 assert.throws(()=>strategySelectionPatch({...cex,instrumentId:'BTC'},'ETH'));
 assert.throws(()=>strategySelectionPatch({market:'onchain',instrumentId:'ETH',chainId:'1'},'BTC'));
 assert.notEqual(strategyWorkbenchView(stocks).scope,strategyWorkbenchView({...stocks,accountId:'other'}).scope);
 assert.equal(strategyWorkbenchView({market:'stocks',instrumentId:''}).symbol,'');
 assert.equal(strategyWorkbenchView(null).symbol,'BTC');
});
