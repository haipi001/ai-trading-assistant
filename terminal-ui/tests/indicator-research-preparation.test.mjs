import test from 'node:test';
import assert from 'node:assert/strict';
import {compileStrategy,STRATEGY_EXAMPLES} from '../../src/strategy-engine.js';
test('generated strategy schema rejects unsupported model output before use',()=>{
 for(const value of Object.values(STRATEGY_EXAMPLES))assert.equal(compileStrategy(JSON.stringify(value)).version,1);
 assert.throws(()=>compileStrategy('模型未配置'));
 assert.throws(()=>compileStrategy(JSON.stringify({version:1,type:'arbitrary_python',code:'print(1)'})));
});
