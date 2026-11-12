import {test} from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
import {pageAIGuide,researchProgress,followupQuestions,researchMarkdown} from '../integration/ai-guide.mjs';
const scope={window:{}};vm.runInNewContext(readFileSync(new URL('../integration/registry.js',import.meta.url),'utf8'),scope);
test('all registered page guides derive real adapter availability and never submit or execute',()=>{
 for(const feature of scope.window.TERMINAL_FEATURES)for(const market of ['stocks','cex','onchain']){
  const guide=pageAIGuide(feature,{market});assert.equal(guide.autoSubmit,false);assert.equal(guide.executionAvailable,false);assert.equal(guide.steps.length,4);
  if(guide.canPrepare)assert.ok(guide.sources.every(source=>source.connected));
  if(guide.sources.some(source=>!source.connected))assert.equal(guide.canPrepare,false);
  if(!guide.compatible)assert.equal(guide.canPrepare,false);
 }
});
test('native demo pages route to business evidence and missing adapters route to gap planning',()=>{
 const native=pageAIGuide({code:'GP',page:'terminal',label:'Chart'},{market:'stocks'});assert.equal(native.canPrepare,false);assert.equal(native.destination,'R009');
 const depth=pageAIGuide({code:'R010',page:'market',tab:'深度'},{market:'cex'});assert.equal(depth.canPrepare,false);assert.ok(depth.action.id.endsWith('.gaps'));
});
test('busy, errors and material blockers cannot appear as completed research',()=>{
 assert.equal(researchProgress({busy:true,hasResult:true,canRequest:true}).step,2);
 assert.equal(researchProgress({issue:'wrong account',hasResult:true,canRequest:true}).step,1);
 assert.equal(researchProgress({error:'timeout',hasResult:true,canRequest:true}).label,'需要处理');
 assert.equal(researchProgress({canRequest:true,hasResult:true}).step,3);
 assert.equal(researchProgress({hasResult:true}).step,0);
});
test('followups remain editable research questions and exports require an actual AI result',()=>{
 assert.ok(followupQuestions({label:'持仓集中度'}).every(text=>text.includes('持仓集中度')));
 assert.throws(()=>researchMarkdown({role:'user',text:'hello'}),/validated_result_required/);
 const md=researchMarkdown({role:'ai',id:'request-1',context:'BTC',text:'证据不足',result:{market_context_snapshot_id:'snapshot-1'}});
 assert.match(md,/snapshot-1/);assert.match(md,/证据不足/);assert.match(md,/news: 未附带/);
});
