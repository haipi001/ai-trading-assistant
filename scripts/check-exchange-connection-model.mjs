import assert from 'node:assert/strict';
import {validateExchangeSnapshot,validateConnectionList,validateConnectionSnapshot} from '../src/exchange-connection-model.js';
const snapshot={exchange:'bybit',status:'verified_readonly',checked_at:'2026-10-28T00:00:00Z',permissions:{reading:true,trading:false,transfers:false,withdrawals:false},credentials_persisted:true,balances:[{asset:'BTC',free:null,locked:'0.1',wallet_balance:'1.0000000000000001',equity:'1E-8'}]};
assert.equal(validateExchangeSnapshot(snapshot).balances[0].wallet_balance,'1.0000000000000001');
assert.equal(validateExchangeSnapshot(snapshot).balances[0].free,null);
assert.equal(validateExchangeSnapshot({...snapshot,api_secret:'must_drop'}).api_secret,undefined);
for(const changed of [{permissions:{...snapshot.permissions,trading:true}},{status:'active'},{balances:[...snapshot.balances,...snapshot.balances]},{balances:[{asset:'BTC',free:'NaN'}]}])assert.throws(()=>validateExchangeSnapshot({...snapshot,...changed}));
const row={id:'fixture',label:'只读连接',exchange:'binance',status:'verified_readonly',checked_at:snapshot.checked_at,credentials_persisted:true};
assert.equal(validateConnectionList([row])[0].label,'只读连接');
assert.throws(()=>validateConnectionList([row,row]));
assert.throws(()=>validateConnectionList([{...row,exchange:'unknown'}]));
assert.equal(validateConnectionList([{...row,credentials_ref:'drop_reference'}])[0].credentials_ref,undefined);
console.log('Exchange UI model: strict permission proof, precision, absent values, duplicate rejection and secret/reference removal passed');

const tied={...snapshot,id:'fixture'};
assert.equal(validateConnectionSnapshot(tied,{id:'fixture',exchange:'bybit'}).id,'fixture');
for(const connection of [{id:'other',exchange:'bybit'},{id:'fixture',exchange:'binance'},null])assert.throws(()=>validateConnectionSnapshot(tied,connection));
assert.throws(()=>validateConnectionSnapshot({...tied,credentials_persisted:false},{id:'fixture',exchange:'bybit'}));

const {validateProbeSnapshot}=await import('../src/exchange-connection-model.js');
assert.equal(validateProbeSnapshot({...snapshot,credentials_persisted:false},'bybit',false).exchange,'bybit');
assert.equal(validateProbeSnapshot(tied,'bybit',true).id,'fixture');
assert.throws(()=>validateProbeSnapshot(tied,'binance',true));
assert.throws(()=>validateProbeSnapshot(tied,'bybit',false));
assert.throws(()=>validateProbeSnapshot({...snapshot,credentials_persisted:undefined},'bybit',false));
assert.throws(()=>validateProbeSnapshot(snapshot,'bybit',true));
assert.throws(()=>validateExchangeSnapshot({...snapshot,balances:[{asset:'BTC',free:'1e9999'}]}));
assert.throws(()=>validateExchangeSnapshot({...snapshot,balances:[{asset:'BTC',free:'1'},{asset:'btc',free:'2'}]}));
console.log('Exchange probe response binding: requested venue/save mode, saved ID, explicit persistence, finite amounts and case-insensitive unique assets passed');
