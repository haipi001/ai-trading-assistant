import test from 'node:test';
import assert from 'node:assert/strict';
import {strategyMoneyContext} from '../../src/strategy-money-context.js';
test('budget units use the exact CEX quote or verified stock account currency without inventing a price currency',()=>{
 assert.deepEqual(strategyMoneyContext('SOL',{market:'cex',instrumentId:'ETH/BTC'}),{instrument:'SOL/BTC',budgetCurrency:'BTC',quoteCurrency:'BTC',legacy:false});
 const stocks=strategyMoneyContext('AAPL',{market:'stocks',accountVerified:true,accountCurrency:'EUR'});
 assert.equal(stocks.instrument,'AAPL');assert.equal(stocks.budgetCurrency,'EUR');assert.equal(stocks.quoteCurrency,null);
 assert.equal(strategyMoneyContext('AAPL',{market:'stocks',accountVerified:false,accountCurrency:'USD'}).budgetCurrency,null);
 assert.equal(strategyMoneyContext('ETH',{market:'cex',instrumentId:'ETH'}).budgetCurrency,null);
 assert.equal(strategyMoneyContext('ETH',{market:'onchain'}).quoteCurrency,null);
 assert.equal(strategyMoneyContext('BTC',null).budgetCurrency,'USDT');
});

test('material binds budget and quote units and refuses a draft copied from another currency',async()=>{
 const {strategyMaterialRequest}=await import('../../src/strategy-material.js');
 const context={identityUserId:'owner',accountVerified:true,accountId:'account',market:'cex',contextVersion:1,instrumentId:'ETH/BTC'};
 const form={name:'DCA',coin:'ETH',type:'DCA',amount:'100',platform:'mock',risk:'bounded'};
 const request=strategyMaterialRequest(form,context);
 assert.equal(request.parameters.budget_currency,'BTC');assert.equal(request.parameters.quote_currency,'BTC');
 assert.throws(()=>strategyMaterialRequest({...form,budget_currency:'USDT'},context));
 const stock=strategyMaterialRequest({...form,coin:'AAPL'},{...context,market:'stocks',instrumentId:'AAPL',accountCurrency:'EUR'});
 assert.equal(stock.parameters.budget_currency,'EUR');assert.equal(stock.parameters.quote_currency,undefined);
});
