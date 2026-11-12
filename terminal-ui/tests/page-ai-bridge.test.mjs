import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {preparePageAIAction,validatePageAIIntent} from '../integration/page-ai-actions.mjs';
const source=readFileSync(new URL('../../src/terminal-feature.jsx',import.meta.url),'utf8');
const start=source.indexOf('const receive=event=>{'),end=source.indexOf(";window.addEventListener('message',receive)",start);
assert.ok(start>=0&&end>start);
const feature={code:'R009',page:'market',tab:'图表',label:'图表'};
const context={panelId:'main:R009',market:'stocks',instrumentId:'AAPL',venue:'NASDAQ',accountId:'a',walletId:'',chainId:null,contractAddress:'',timeframe:'1D',executionMode:'READ_ONLY',contextVersion:3};
function receiver(){
 const events=[],acks=[],parent={postMessage:packet=>acks.push(packet)},origin='http://127.0.0.1:8850';
 const scope={current:{current:{context, target:feature}},location:{origin},parent,validatePageAIIntent,window:{dispatchEvent:event=>events.push(event)},CustomEvent:class {constructor(type,{detail}){this.type=type;this.detail=detail;}}};
 vm.runInNewContext(source.slice(start,end)+';globalThis.receive=receive;',scope);
 return {events,acks,parent,origin,receive:scope.receive};
}
test('the shipped feature bridge accepts only the current parent and canonical page action',()=>{
 const h=receiver(),plan=preparePageAIAction(feature,'R009.analysis',context);
 const message={type:'terminal:feature-research',question:'Do something else',contextVersion:3,pageAction:structuredClone(plan)};
 h.receive({origin:'https://untrusted.example',source:h.parent,data:message});
 h.receive({origin:h.origin,source:{},data:message});
 h.receive({origin:h.origin,source:h.parent,data:{...message,contextVersion:2}});
 h.receive({origin:h.origin,source:h.parent,data:{...message,pageAction:{...plan,context:{...plan.context,panelId:'1:R009'}}}});
 h.receive({origin:h.origin,source:h.parent,data:{...message,pageAction:{...plan,requiredSources:[]}}});
 assert.equal(h.events.length,0);
 h.receive({origin:h.origin,source:h.parent,data:message});
 assert.equal(h.events.length,1);assert.equal(h.events[0].type,'terminal:research');
 assert.equal(h.events[0].detail.question,plan.question);
 assert.equal(h.events[0].detail.pageAction.context.panelId,'main:R009');
 assert.ok(Object.isFrozen(h.events[0].detail.pageAction));
});

test('parent bridge refuses stale actions and reports missing panels instead of claiming delivery',()=>{
 const parentSource=readFileSync(new URL('../integration/panel-host.mjs',import.meta.url),'utf8');
 const begin=parentSource.indexOf("window.addEventListener('terminal:research-request',"),end=parentSource.indexOf('\n',begin);
 let listener,focused=null,sent=[];
 const scope={crypto:{randomUUID:()=> 'request-test'},researchDeliveries:new Map(),setTimeout:()=>1,window:{addEventListener:(name,fn)=>listener=fn},document:{querySelector:()=>focused},validatePageAIIntent,entries:new Map([[feature.code,feature]]),runtimeContext:()=>context,effective:()=>context,location:{origin:'http://127.0.0.1:8850'}};
 vm.runInNewContext(parentSource.slice(begin,end),scope);
 const absent={detail:{question:'Research'}};listener(absent);assert.equal(absent.detail.delivery,'business_panel_required');
 focused={dataset:{terminalFeature:feature.code},contentWindow:{postMessage:packet=>sent.push(packet)}};
 const plan=preparePageAIAction(feature,'R009.analysis',context);
 const stale={detail:{question:plan.question,pageAction:{...plan,context:{...plan.context,accountId:'other'}}}};
 listener(stale);assert.equal(stale.detail.delivery,'context_changed');assert.equal(sent.length,0);
 const valid={detail:{question:plan.question,pageAction:plan}};listener(valid);assert.equal(valid.detail.delivery,'forwarded');assert.equal(sent.length,1);assert.equal(sent[0].contextVersion,3);
 listener({});assert.equal(sent.length,1);
});

test('child reports unhandled research as rejected rather than accepted',()=>{const h=receiver();h.receive({origin:h.origin,source:h.parent,data:{type:'terminal:feature-research',question:'Review',contextVersion:3,requestId:'request-a'}});assert.equal(h.events.length,1);assert.equal(h.acks[0].requestId,'request-a');assert.equal(h.acks[0].accepted,false);});

test('receipt is bound to the originating frame and is consumed once; session change clears timers',()=>{
 const parentSource=readFileSync(new URL('../integration/panel-host.mjs',import.meta.url),'utf8');
 const begin=parentSource.indexOf('const researchDeliveries=new Map();'),end=parentSource.indexOf('\nfunction frames()',begin);
 const listeners={},events=[],cleared=[],frame={contentWindow:{}};
 const scope={window:{addEventListener:(name,fn)=>listeners[name]=fn,dispatchEvent:e=>events.push(e)},location:{origin:'http://127.0.0.1:8850'},clearTimeout:id=>cleared.push(id),CustomEvent:class{constructor(type,{detail}){this.type=type;this.detail=detail;}}};
 vm.runInNewContext(parentSource.slice(begin,end)+';globalThis.pending=researchDeliveries;',scope);
 scope.pending.set('r',{frame,timer:7});
 const message={origin:scope.location.origin,source:frame.contentWindow,data:{type:'terminal:research-received',requestId:'r',accepted:true}};
 listeners.message({...message,origin:'https://foreign.example'});listeners.message({...message,source:{}});assert.equal(events.length,0);assert.equal(scope.pending.size,1);
 listeners.message(message);listeners.message(message);assert.equal(events.length,1);assert.equal(events[0].detail.status,'received');assert.deepEqual(cleared,[7]);
 scope.pending.set('next',{frame,timer:8});listeners['terminal:session-changed']();assert.equal(scope.pending.size,0);assert.deepEqual(cleared,[7,8]);
});
