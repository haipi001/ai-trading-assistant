import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const source=readFileSync(new URL('../../src/market-workbench.jsx',import.meta.url),'utf8');
const panel=source.slice(source.indexOf('function IndicatorPanel'),source.indexOf('function GridPanel'));
const start=panel.indexOf('onClick={()=>{\n if(!aiPrompt.trim())'),end=panel.indexOf('}}><I.PaperPlaneTilt/>',start);
assert.ok(start>=0&&end>start);
test('shipped indicator action prepares the current script for explicit AI review without fake generation',()=>{
 const events=[],notices=[];
 const sandbox={aiPrompt:'Review RSI',code:'user-script'.repeat(300),say:value=>notices.push(value),JSON,CustomEvent:class{constructor(type,{detail}){this.type=type;this.detail=detail;}},window:{dispatchEvent:event=>{events.push(event);event.detail.accepted=true;}}};
 vm.runInNewContext('globalThis.run='+panel.slice(start+'onClick={'.length,end+1)+';',sandbox);sandbox.run();
 assert.equal(events.length,1);assert.equal(events[0].type,'ai-trading-assistant-research-intent');assert.equal(events[0].detail.includeMarket,false);
 assert.match(events[0].detail.question,/user-script/);assert.match(events[0].detail.question,/script_truncated/);assert.ok(events[0].detail.question.length<4000);assert.match(notices[0],/手动发送/);
 sandbox.aiPrompt='';sandbox.run();assert.equal(events.length,1);
 assert.equal(panel.includes('setTimeout'),false);
});
