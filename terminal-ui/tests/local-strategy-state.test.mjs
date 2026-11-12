import test from 'node:test';
import assert from 'node:assert/strict';
import {localStrategyLabel,toggleLocalStrategy} from '../../src/local-strategy-state.js';
test('local strategy drafts cannot be promoted to running by pause/resume',()=>{
 const draft={id:1,status:'草稿'};assert.equal(toggleLocalStrategy(draft),draft);
 const paused={id:2,status:'已暂停'};assert.equal(toggleLocalStrategy(paused).status,'待启动');
 assert.equal(localStrategyLabel({status:'运行中'}),'本地模拟 · 未验证运行');
 assert.equal(localStrategyLabel(draft),'本地草稿');
 assert.equal(paused.status,'已暂停');
});
