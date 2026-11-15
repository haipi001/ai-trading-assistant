import {test} from 'node:test';
import assert from 'node:assert/strict';
import {newsScopeForMarket,MARKET_NEWS_SCOPE} from '../../src/news-market-scope.js';

test('each terminal market maps to one news scope',()=>{
 assert.equal(newsScopeForMarket('stocks'),'us');
 assert.equal(newsScopeForMarket('web3'),'crypto');
 assert.equal(newsScopeForMarket('cex'),'crypto');
 assert.equal(newsScopeForMarket('onchain'),'crypto');
});

test('unknown market falls back to every feed instead of guessing one',()=>{
 assert.equal(newsScopeForMarket('forex'),'all');
 assert.equal(newsScopeForMarket(undefined),'all');
 assert.equal(newsScopeForMarket(''),'all');
});

test('stock scope never resolves to the crypto feed or the reverse',()=>{
 assert.notEqual(MARKET_NEWS_SCOPE.stocks,MARKET_NEWS_SCOPE.cex);
 assert.notEqual(MARKET_NEWS_SCOPE.stocks,MARKET_NEWS_SCOPE.web3);
 assert.equal(newsScopeForMarket('stocks'),MARKET_NEWS_SCOPE.stocks);
});
