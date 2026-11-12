import test from 'node:test';
import assert from 'node:assert/strict';
import {spotDcaConfiguration} from '../../src/spot-dca-configuration.js';
import {strategyMaterialRequest} from '../../src/strategy-material.js';
test('spot DCA plan preserves local timing without turning it into an execution schedule',()=>{
 const dca={kind:'spot_dca',frequency:'每周',first_run_local:'2027-01-02T09:30',take_profit_percent:'20'};
 assert.deepEqual(spotDcaConfiguration(dca),dca);
 for(const patch of [{frequency:'每秒'},{first_run_local:'2027-02-30T09:30'},{first_run_local:'2027-01-02T09:30Z'},{take_profit_percent:'NaN'},{take_profit_percent:'0'},{execute:true}])assert.throws(()=>spotDcaConfiguration({...dca,...patch}));
 const request=strategyMaterialRequest({name:'DCA',coin:'ETH',type:'现货DCA',amount:'100',platform:'mock',risk:'review',dca},{identityUserId:'owner',accountVerified:true,accountId:'a',market:'cex',instrumentId:'ETH/USDT',contextVersion:3});
 assert.deepEqual(request.parameters.dca,dca);assert.equal(request.parameters.execute,undefined);
});
