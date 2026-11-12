import test from 'node:test';
import assert from 'node:assert/strict';
import {checkGridParameters} from '../../src/grid-parameter-check.js';
test('grid check computes actual parameter spacing and budget without inventing profitability',()=>{
 const input={lower:'100',upper:'200',gridCount:'10',amount:'100'};const result=checkGridParameters(input);
 assert.equal(result.priceSpacing,10);assert.equal(result.budgetPerInterval,10);assert.equal(result.feesIncluded,false);assert.equal(result.executionAvailable,false);assert.equal(result.profit,undefined);
 for(const patch of [{amount:'NaN'},{amount:'Infinity'},{lower:''},{upper:'99'},{gridCount:'2.5'},{gridCount:'501'},{amount:'19'},{lower:'-1'}])assert.throws(()=>checkGridParameters({...input,...patch}));
});

test('grid configuration remains typed in material and cannot be replaced by stale bounds',async()=>{
 const {strategyMaterialRequest,strategyMaterialPacket}=await import('../../src/strategy-material.js');
 const form={name:'Grid',coin:'ETH',type:'AI网格',amount:'100',platform:'mock',risk:'review',grid:{kind:'arithmetic_grid',lower:'100',upper:'200',intervals:10}};
 const request=strategyMaterialRequest(form,{identityUserId:'owner',accountVerified:true,accountId:'a',market:'cex',contextVersion:4});
 assert.deepEqual(request.parameters.grid,form.grid);
 const packet={snapshot_id:'snapshot',execution_available:false,material:{schema_version:1,source:'user_local_strategy_parameters',...request,captured_at:new Date().toISOString(),content_hash:'a'.repeat(64),execution_available:false,usable_for_trading:false,independently_verified:false}};
 assert.deepEqual(strategyMaterialPacket(packet,request).material.parameters.grid,form.grid);
 assert.throws(()=>strategyMaterialPacket({...packet,material:{...packet.material,parameters:{...request.parameters,grid:{...form.grid,upper:'300'}}}},request));
});
