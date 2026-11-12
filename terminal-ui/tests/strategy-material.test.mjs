import test from 'node:test';
import assert from 'node:assert/strict';
import {strategyMaterialRequest,strategyMaterialPacket} from '../../src/strategy-material.js';
const form={name:'DCA',coin:'ETH',type:'DCA',amount:'20',platform:'mock',risk:'bounded'};
const context={identityUserId:'owner',accountVerified:true,accountId:'a',market:'cex',contextVersion:4};
test('strategy material binds exact validated account, context and edited fields',()=>{
 const request=strategyMaterialRequest(form,context);
 const packet={snapshot_id:'snapshot',execution_available:false,material:{schema_version:1,source:'user_local_strategy_parameters',...request,captured_at:new Date().toISOString(),content_hash:'a'.repeat(64),execution_available:false,usable_for_trading:false,independently_verified:false}};
 assert.equal(strategyMaterialPacket(packet,request).snapshot_id,'snapshot');
 for(const patch of [{account_id:'foreign'},{context_version:5},{market:'stocks'},{execution_available:true},{parameters:{...request.parameters,amount:'21'}}])assert.throws(()=>strategyMaterialPacket({...packet,material:{...packet.material,...patch}},request));
 for(const patch of [{identityUserId:null},{accountVerified:false},{market:'onchain'},{accountId:''}])assert.throws(()=>strategyMaterialRequest(form,{...context,...patch}));
});
