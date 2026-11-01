import assert from 'node:assert/strict';
import {balanceListPage} from '../src/exchange-balance-list.js';
const rows=Array.from({length:121},(_,i)=>({asset:`COIN${i}`,free:'1.000000000000000001',equity:null}));
assert.equal(balanceListPage(rows,'',2).rows.length,21);assert.equal(balanceListPage(rows,'coin120',2).rows[0].asset,'COIN120');assert.equal(balanceListPage(rows,'coin120',2).current,0);assert.equal(balanceListPage(rows,'missing').total,0);assert.equal(balanceListPage(rows,'',100).current,2);assert.equal(balanceListPage(rows,'coin120').rows[0].free,'1.000000000000000001');assert.equal(balanceListPage(rows,'coin120').rows[0].equity,null);assert.equal(balanceListPage(rows,'ＣＯＩＮ１２０').total,1);
console.log('Balance search: all pages searched, Unicode/case matching, page clamp and original precision/null retained');
