import test from 'node:test';
import assert from 'node:assert/strict';
import {checkCopyParameters} from '../../src/copy-parameters.js';
import {workbenchFormKey} from '../../src/workbench-form-buffer.js';
import {localStrategyLabel,toggleLocalStrategy} from '../../src/local-strategy-state.js';
test('copy settings are strict manual inputs and local configuration cannot imply an executed subscription',()=>{
 const form={amount:'100',stopLoss:'10',mode:'定额跟单'};const value=checkCopyParameters(form);
 assert.equal(value.executionAvailable,false);assert.equal(value.maximumLossVerified,false);
 for(const patch of [{amount:'NaN'},{amount:'Infinity'},{amount:''},{stopLoss:'-1'},{mode:'auto-live'}])assert.throws(()=>checkCopyParameters({...form,...patch}));
 const record={status:'待启动'};assert.match(localStrategyLabel(record),/未启动/);assert.equal(toggleLocalStrategy({status:'已暂停'}).status,'待启动');
 const context={identityUserId:'owner',accountId:'a',market:'cex',instrumentId:'BTC/USDT',panelId:'main:STR5'};
 assert.notEqual(workbenchFormKey('copy-CEX','template-a',context),workbenchFormKey('copy-CEX','template-b',context));
 assert.notEqual(workbenchFormKey('copy-CEX','template-a',context),workbenchFormKey('copy-DEX','template-a',context));
});
