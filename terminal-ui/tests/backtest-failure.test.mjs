import test from 'node:test';
import assert from 'node:assert/strict';
import {AI_MESSAGES,isResearchMaterialFailure} from '../../src/research-ai.js';
test('backtest material failures explain recovery without disabling the configured model',()=>{
 for(const reason of ['ai_backtest_stale','ai_backtest_unavailable','ai_backtest_identity_mismatch','ai_backtest_incompatible']){assert.equal(isResearchMaterialFailure(reason),true);assert.ok(AI_MESSAGES[reason]);}
 assert.equal(isResearchMaterialFailure('ai_configuration_required'),false);
});

test('conversation history labels BT1 as a prior run rather than current evidence',async()=>{
 const {researchHistory}=await import('../../src/research-ai.js');
 const history=researchHistory([{role:'ai',text:'Review [BT1]',result:{backtest_context_snapshot_id:'old-snapshot',provided_backtest:{backtest_run_id:'old-run',captured_at:'old-time',content_hash:'old-hash'}}}]);
 assert.match(history[0].content,/old-run/);assert.match(history[0].content,/old-snapshot/);assert.match(history[0].content,/not the current backtest_context/);assert.match(history[0].content,/no new script execution/);
});
