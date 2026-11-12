import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {researchPrincipal,researchVisibleMessages} from '../../src/research-request-scope.js';
test('old and unidentified messages are hidden before effects clear state after a session change',()=>{const first=researchPrincipal('user-a','session-1'),next=researchPrincipal('user-b','session-2');assert.notEqual(first,next);assert.deepEqual(researchVisibleMessages([{principal:first,text:'private'},{text:'unknown'}],next),[]);assert.equal(researchVisibleMessages([{principal:next,text:'new'}],next).length,1);});
const source=readFileSync(new URL('../../src/research-ai-chat.jsx',import.meta.url),'utf8');
const start=source.indexOf('const ask=async('),end=source.indexOf('\n if(!open)return null;',start);assert.ok(start>=0&&end>start);
for(const failure of [false,true])test('the shipped async chat handler discards previous-session '+(failure?'errors':'replies'),async()=>{
 let settle;const deferred=new Promise((resolve,reject)=>{settle=failure?reject:resolve;});let messages=[],errors=[],toasts=0;
 const sandbox={strategyAttachment:null,includeStrategy:false,strategyReadiness:()=>'',activeRequestPrincipal:{current:null},input:'Private question',pending:{current:false},principalMatches:true,includePaperReview:false,paperReviewAttachment:null,paperReviewReadiness:()=>'',terminalContext:null,includePortfolio:false,pageActionIssue:'',includeOnchain:false,attachmentValid:false,includeMarket:false,marketCapture:null,includeNews:false,newsReady:true,status:{can_request:true},setError:value=>errors.push(value),setBusy(){},currentScope:'old-scope',principal:'old-user',page:'assets',symbol:'AAPL',researchHistory:()=>[],workspaceContext:null,visibleMessages:[],contextIdentity:'old-scope',terminalKey:'',pageAction:null,setMessages:callback=>{messages=callback(messages);},crypto:{randomUUID:()=> 'controlled'},requestResearchChat:()=>deferred,mounted:{current:true},latestPrincipal:{current:'old-user'},latestScope:{current:'old-scope'},AI_MESSAGES:{},isResearchMaterialFailure:()=>false,setStatus(){},researchText:()=> 'Private reply',setInput(){},say:()=>toasts++};
 vm.runInNewContext(source.slice(start,end)+';globalThis.ask=ask;',sandbox);
 const work=sandbox.ask();assert.equal(messages.length,1);assert.equal(sandbox.activeRequestPrincipal.current,'old-user');sandbox.latestPrincipal.current='new-user';sandbox.latestScope.current='new-scope';
 if(failure)settle(new Error('Private old-session failure'));else settle({status:'ok',request_id:'controlled',provider:'controlled',model:'controlled'});
 await work;assert.equal(sandbox.activeRequestPrincipal.current,null);assert.equal(messages.length,1);assert.equal(toasts,0);assert.deepEqual(errors,['']);
 assert.equal(researchVisibleMessages(messages,'new-user').length,0);
});

const intentStart=source.indexOf('useEffect(()=>{if(!intent||processedIntent.current===intent)'),intentEnd=source.indexOf('},[intent,busy,principal,currentScope]);',intentStart);
assert.ok(intentStart>=0&&intentEnd>intentStart);
test('new research preparation waits for the active request, applies once and never crosses its principal or scope',()=>{
 for(const changed of [null,'principal','scope']){
  const intent={id:'prepared',question:'Review original Paper fill'},applied=[];
  const sandbox={intent,processedIntent:{current:null},intentEnvelope:{current:{intent,principal:'owner',scope:'workspace'}},principal:'owner',currentScope:'workspace',pending:{current:true},setInput:value=>applied.push(value),setPageAction(){},setStrategyAttachment(){},setIncludeStrategy(){},setPaperReviewAttachment(){},setIncludePaperReview(){},setIncludePortfolio(){},setIncludeNews(){},setIncludeMarket(){},setAttachment(){},setIncludeOnchain(){},setError(){}};
  vm.runInNewContext('globalThis.applyIntent='+source.slice(intentStart+'useEffect('.length,intentEnd+1)+';',sandbox);
  sandbox.applyIntent();assert.equal(applied.length,0);
  if(changed==='principal')sandbox.principal='another-user';if(changed==='scope')sandbox.currentScope='another-account';
  sandbox.pending.current=false;sandbox.applyIntent();sandbox.applyIntent();assert.equal(applied.length,changed?0:1);
 }
});
