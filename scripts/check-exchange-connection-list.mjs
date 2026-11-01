import assert from 'node:assert/strict';
import {connectionListPage} from '../src/exchange-connection-list.js';
const rows=Array.from({length:61},(_,i)=>({id:String(i),label:`账户 ${i}`,exchange:i%2?'okx':'binance',status:i%3?'verified_readonly':'disabled',credentials_persisted:!!(i%3)}));
assert.equal(connectionListPage(rows).rows.length,25);assert.equal(connectionListPage(rows,{page:2}).rows.length,11);assert.equal(connectionListPage(rows,{page:99}).current,2);
assert.equal(connectionListPage(rows,{query:'账户 60'}).rows[0].id,'60');assert.equal(connectionListPage(rows,{query:' OKX '}).total,30);assert.equal(connectionListPage(rows,{exchange:'okx',status:'enabled'}).total,20);assert.equal(connectionListPage(rows,{status:'disabled'}).total,21);
assert.equal(connectionListPage(rows,{query:'missing',page:8}).current,0);assert.equal(connectionListPage(rows,{query:'missing'}).pages,1);assert.equal(connectionListPage(rows,{page:-1}).current,0);
console.log('Connection list: search/filter before paging, exact platform/state, page clamping and empty filters passed');
