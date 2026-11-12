import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

// Exercise the shipped message handler, including the initial-null-state race.
const source=readFileSync(new URL('../integration/shell.js',import.meta.url),'utf8');
const start=source.indexOf("window.addEventListener('message',event=>{");
const end=source.indexOf("\n window.addEventListener('terminal:appearance'",start);
assert.ok(start>=0&&end>start,'shell message registration must be present');
const registration=source.slice(start,end);
function harness(){
 const sent=[];let handler,closed=0;
 const frameWindow={postMessage:(message,origin)=>sent.push({message,origin})};
 const context={
  window:{addEventListener:(_,callback)=>{handler=callback;}},location:{origin:'http://127.0.0.1:8850'},
  toolFrame:{contentWindow:frameWindow},toolDialog:{querySelector:()=>({remove(){}})},
  toolReady:false,toolActivated:false,pendingTool:'ai',language:'en',
  closeTool:()=>closed++,applyLanguage(){},
  document:{querySelectorAll:()=>[],querySelector:()=>null},dock:{querySelectorAll:()=>[]}
 };
 vm.runInNewContext(registration,context);
 const receive=(type,extra={},origin=context.location.origin,source=frameWindow)=>handler({origin,source,data:{type,...extra}});
 return {context,sent,receive,closed:()=>closed};
}
test('untrusted origins and sibling windows cannot initialize or close the global tool drawer',()=>{
 const h=harness();
 for(const type of ['terminal:tool-ready','terminal:tool-activated','terminal:tool-close']){
  h.receive(type,{},'https://untrusted.example');
  h.receive(type,{},'http://127.0.0.1:8850',{});
 }
 assert.equal(h.context.toolReady,false);assert.equal(h.context.toolActivated,false);
 assert.equal(h.sent.length,0);assert.equal(h.closed(),0);
});
test('trusted tool readiness sends the selected language and requested tool only to that frame',()=>{
 const h=harness();h.receive('terminal:tool-ready');
 assert.equal(h.context.toolReady,true);
 assert.deepEqual(h.sent.map(item=>item.message.type),['terminal:feature-language','terminal:feature-tool']);
 assert.equal(h.sent[0].message.language,'en');assert.equal(h.sent[1].message.tool,'ai');
 assert.ok(h.sent.every(item=>item.origin==='http://127.0.0.1:8850'));
});
test('initial empty React state does not close the drawer before the requested tool activates',()=>{
 const h=harness();h.receive('terminal:tool-ready');h.receive('terminal:tool-state',{tool:null});
 assert.equal(h.closed(),0);
 h.receive('terminal:tool-activated',{tool:'ai'});h.receive('terminal:tool-state',{tool:'ai'});
 assert.equal(h.closed(),0);
 h.receive('terminal:tool-state',{tool:null});assert.equal(h.closed(),1);
});
