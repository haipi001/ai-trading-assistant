import test from 'node:test';
import assert from 'node:assert/strict';
import {checkFuturesDcaParameters} from '../../src/futures-dca-parameters.js';
test('futures DCA estimates only initial linear exposure and refuses unsupported or nonfinite inputs',()=>{
 const form={amount:'100',leverage:'3x',addRatio:'2.5',takeProfit:'8',direction:'做多',frequency:'每4小时'};
 const value=checkFuturesDcaParameters(form);
 assert.equal(value.initialNotional,300);assert.equal(value.absolutePnlForOnePercent,3);assert.equal(value.maximumLoss,null);assert.equal(value.maximumAdditionalMargin,null);assert.equal(value.feesIncluded,false);assert.equal(value.executionAvailable,false);
 for(const patch of [{amount:'Infinity'},{amount:'NaN'},{amount:'19'},{addRatio:'-1'},{takeProfit:''},{leverage:'100x'},{frequency:'every second'},{direction:'unknown'}])assert.throws(()=>checkFuturesDcaParameters({...form,...patch}));
});
