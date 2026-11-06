import {test} from 'node:test';import assert from 'node:assert/strict';
import {onchainHistoryList} from '../../src/onchain-research-history.js';
const row={snapshot_id:'12345678-1234-1234-1234-123456789abc',context_version:7,reply_status:'ok',created_at:new Date().toISOString()};
test('history list validates bounded unique artifacts and explicit result states',()=>{const good={execution_available:false,has_more:false,items:[row]};assert.equal(onchainHistoryList(good).items.length,1);for(const change of [{execution_available:true},{has_more:'no'},{items:[row,row]},{items:[{...row,context_version:-1}]},{items:[{...row,reply_status:'approved'}]},{items:[{...row,created_at:'invalid'}]}])assert.throws(()=>onchainHistoryList({...good,...change}));});
