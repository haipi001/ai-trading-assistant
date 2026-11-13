import test from 'node:test';
import assert from 'node:assert/strict';
import {researchMarkdown} from '../integration/ai-guide.mjs';
test('research export retains saved backtest identity, hash and source limits',()=>{
 const result={request_id:'request',backtest_context_snapshot_id:'frozen-ai',provided_backtest:{backtest_run_id:'run',captured_at:'capture-time',content_hash:'digest',date_from:'start',date_to:'end'}};
 const text=researchMarkdown({role:'ai',text:'Review [BT1]',result});
 for(const value of ['frozen-ai','run','capture-time','digest','start','end','[BT1]','历史模拟'])assert.ok(text.includes(value));
});
