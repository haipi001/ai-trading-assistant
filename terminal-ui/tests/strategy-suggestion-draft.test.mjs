import test from 'node:test';
import assert from 'node:assert/strict';
import {strategySuggestionDraft} from '../../src/strategy-suggestion-draft.js';
const now=Date.now(),context={identityUserId:'owner',accountVerified:true,accountId:'account',market:'cex',contextVersion:4};
const material={schema_version:1,source:'user_local_strategy_parameters',execution_available:false,usable_for_trading:false,independently_verified:false,market:'cex',account_id:'account',context_version:4,content_hash:'a'.repeat(64),captured_at:new Date(now).toISOString(),parameters:{name:'DCA',coin:'ETH',type:'DCA',amount:'10',platform:'mock',risk:'low',trigger:'weekly',invalidation:'manual stop',constraints:'no leverage'}};
const change={field:'trigger',before:'weekly',after:'monthly',rationale:'Budget review',citation_ids:['SP1']};
const result={request_id:'chat-12345678-1234-1234-1234-123456789abc',strategy_context_snapshot_id:'12345678-1234-1234-1234-123456789abc',provided_strategy:material,strategy_parameter_changes:[change]};
test('reviewed suggestions create a new unexecuted draft, retain provenance and never overwrite source parameters',()=>{
 const draft=strategySuggestionDraft(result,{trigger:'every two weeks'},context,now);
 assert.equal(draft.trigger,'every two weeks');assert.equal(draft.id,undefined);assert.equal(draft.status,'草稿');assert.equal(draft.source_snapshot_id,result.strategy_context_snapshot_id);assert.equal(material.parameters.trigger,'weekly');
 assert.throws(()=>strategySuggestionDraft(result,{trigger:'weekly'},context,now));
 assert.throws(()=>strategySuggestionDraft(result,{trigger:'monthly',account_id:'foreign'},context,now));
 assert.throws(()=>strategySuggestionDraft(result,{trigger:'monthly'},{...context,accountId:'other'},now));
 assert.throws(()=>strategySuggestionDraft(result,{trigger:'monthly'},context,now+600001));
});

test('reviewed grid changes become nested fields of a new draft without modifying the source',()=>{
 const gridResult={...result,provided_strategy:{...material,parameters:{...material.parameters,amount:'100',grid:{kind:'arithmetic_grid',lower:'100',upper:'200',intervals:10}}},strategy_parameter_changes:[{field:'grid.upper',before:'200',after:'250',rationale:'Hypothetical range review',citation_ids:['SP1']}]};
 const draft=strategySuggestionDraft(gridResult,{'grid.upper':'260'},context,now);
 assert.equal(draft.grid.upper,'260');assert.equal(draft['grid.upper'],undefined);assert.equal(gridResult.provided_strategy.parameters.grid.upper,'200');
 assert.throws(()=>strategySuggestionDraft(gridResult,{'grid.upper':'99'},context,now));
});
