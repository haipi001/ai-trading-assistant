import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {strategyStorageKey,readStrategyDrafts} from '../../src/strategy-draft-scope.js';
test('shipped storage hook hides another account before effects and rejects old save callbacks across round trips',()=>{
 const values=new Map(),listeners=new Map(),cells=[];let cursor=0;
 const storage={getItem:key=>values.get(key)||null,setItem:(key,value)=>values.set(key,value)};
 const window={addEventListener:(key,fn)=>{if(!listeners.has(key))listeners.set(key,new Set());listeners.get(key).add(fn);},removeEventListener:(key,fn)=>listeners.get(key)?.delete(fn),dispatchEvent:event=>{for(const fn of listeners.get(event.type)||[])fn(event);}};
 const sandbox={strategyStorageKey,readStrategyDrafts,localStorage:storage,window,CustomEvent:class{constructor(type,{detail}){this.type=type;this.detail=detail;}},
 useState(initial){const i=cursor++;if(!cells[i])cells[i]={value:typeof initial==='function'?initial():initial};return [cells[i].value,next=>{cells[i].value=typeof next==='function'?next(cells[i].value):next;}];},
 useRef(initial){const i=cursor++;return cells[i]??(cells[i]={current:initial});},
 useMemo(fn,deps){const i=cursor++;if(!cells[i]||deps.some((dep,n)=>dep!==cells[i].deps[n]))cells[i]={value:fn(),deps};return cells[i].value;},
 useEffect(fn,deps){const i=cursor++;if(!cells[i]||deps.some((dep,n)=>dep!==cells[i].deps[n])){cells[i]?.cleanup?.();cells[i]={deps,cleanup:fn()};}}};
 const source=readFileSync(new URL('../../src/use-strategy-drafts.jsx',import.meta.url),'utf8').replace(/^import .*;\n/gm,'').replace('export function useStrategyDrafts','function useStrategyDrafts');
 vm.runInNewContext(source+';globalThis.hook=useStrategyDrafts;',sandbox);
 const a={identityUserId:'owner',accountId:'a',market:'cex'},b={...a,accountId:'b'};
 const render=c=>{cursor=0;return sandbox.hook(true,c);};
 let [rows,saveA]=render(a);assert.equal(rows.length,0);saveA([{id:'a'}]);assert.equal(render(a)[0][0].id,'a');
 assert.equal(render(b)[0].length,0);saveA([{id:'stale'}]);assert.equal(render(b)[0].length,0);
 storage.setItem(strategyStorageKey('ai-trading-assistant-strategies',true,a),JSON.stringify([{id:'updated-in-other-window'}]));
 assert.equal(render(a)[0][0].id,'updated-in-other-window');saveA([{id:'stale-roundtrip'}]);assert.equal(render(a)[0][0].id,'updated-in-other-window');
 window.dispatchEvent({type:'storage',key:strategyStorageKey('ai-trading-assistant-strategies',true,a)});assert.equal(render(a)[0][0].id,'updated-in-other-window');
});
