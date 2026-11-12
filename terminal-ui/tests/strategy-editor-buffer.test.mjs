import test from 'node:test';
import assert from 'node:assert/strict';
import {strategyEditorKey,readStrategyEditor,saveStrategyEditor,clearStrategyEditor} from '../../src/strategy-editor-buffer.js';
test('unsubmitted strategy editor survives reload only in original account and draft',()=>{
 const map=new Map();const storage={getItem:k=>map.get(k),setItem:(k,v)=>map.set(k,v),removeItem:k=>map.delete(k)};
 const key=strategyEditorKey('user-a:account-a',null);const initial={name:'initial',amount:'1000',status:'草稿'};
 saveStrategyEditor(storage,key,{name:'edited',amount:'invalid pending input',trigger:'user rule',api_key:'secret',status:'运行中',id:'foreign'});
 const restored=readStrategyEditor(storage,key,initial);assert.equal(restored.name,'edited');assert.equal(restored.amount,'invalid pending input');assert.equal(restored.status,'草稿');assert.equal(restored.id,undefined);
 assert.doesNotMatch(map.get(key),/secret|运行中|foreign/);
 assert.deepEqual(readStrategyEditor(storage,strategyEditorKey('user-a:account-b',null),initial),initial);
 assert.deepEqual(readStrategyEditor(storage,strategyEditorKey('user-a:account-a','saved'),initial),initial);
 clearStrategyEditor(storage,key);assert.deepEqual(readStrategyEditor(storage,key,initial),initial);
});
