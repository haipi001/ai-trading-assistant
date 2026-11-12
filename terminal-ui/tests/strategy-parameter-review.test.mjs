import test from 'node:test';
import assert from 'node:assert/strict';
import {strategyParameterReview} from '../../src/strategy-parameter-review.js';
test('strategy review uses explicit editable parameters, excludes secrets and never authorizes execution',()=>{
 const form={name:'DCA',coin:'ETH',amount:'20',trigger:'每周',constraints:'单次20',api_key:'must-not-leak'};
 const value=strategyParameterReview(form,{market:'cex',accountId:'owned',secret:'must-not-leak'});
 assert.match(value.question,/每周/);assert.match(value.question,/user_local_strategy_parameters/);assert.doesNotMatch(value.question,/must-not-leak/);assert.equal(value.includeMarket,false);assert.equal(value.parameters.invalidation,'');
 assert.ok(value.question.length<4000);assert.equal(form.api_key,'must-not-leak');
 for(const amount of ['NaN','Infinity','-1','0','1e8',''])assert.throws(()=>strategyParameterReview({...form,amount}));
});
