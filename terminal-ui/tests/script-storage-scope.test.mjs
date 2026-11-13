import test from 'node:test';
import assert from 'node:assert/strict';
import {SCRIPT_STORE_KEY,SCRIPT_BUFFER_KEY} from '../../src/script-drafts.js';
import {scopedScriptStorage} from '../../src/script-storage-scope.js';
test('scoped script stores keep legacy records untouched and separate owners and buffers',()=>{
 const data=new Map([[SCRIPT_STORE_KEY,'legacy']]),storage={getItem:key=>data.get(key)??null,setItem:(key,value)=>data.set(key,value),removeItem:key=>data.delete(key)};
 const a=scopedScriptStorage(storage,'a'),b=scopedScriptStorage(storage,'b');
 assert.equal(a.getItem(SCRIPT_STORE_KEY),null);a.setItem(SCRIPT_STORE_KEY,'private');a.setItem(SCRIPT_BUFFER_KEY,'buffer');
 assert.equal(b.getItem(SCRIPT_STORE_KEY),null);assert.equal(a.getItem(SCRIPT_STORE_KEY),'private');assert.equal(a.getItem(SCRIPT_BUFFER_KEY),'buffer');
 b.removeItem(SCRIPT_STORE_KEY);assert.equal(a.getItem(SCRIPT_STORE_KEY),'private');assert.equal(data.get(SCRIPT_STORE_KEY),'legacy');
 assert.throws(()=>scopedScriptStorage(storage,null).getItem(SCRIPT_STORE_KEY));
});

test('actual script commit remains isolated and a revoked session cannot write',async()=>{
 const {sessionBoundScriptStorage}=await import('../../src/script-storage-scope.js');
 const {commitScriptStore,readScriptStore}=await import('../../src/script-drafts.js');
 const data=new Map(),storage={getItem:key=>data.get(key)??null,setItem:(key,value)=>data.set(key,value),removeItem:key=>data.delete(key)};
 let identity='session-a';const owner=sessionBoundScriptStorage(scopedScriptStorage(storage,'a'),()=>identity);
 const saved=commitScriptStore(owner,null,{type:'save',id:null,name:'Private script',code:'plot(close)'},{id:'script-a'});
 assert.equal(saved.data.documents[0].code,'plot(close)');assert.equal(readScriptStore(scopedScriptStorage(storage,'b')).data.documents.length,0);
 identity='session-b';const before=JSON.stringify([...data]);
 assert.throws(()=>commitScriptStore(owner,saved.raw,{type:'save',id:'script-a',name:'Changed',code:'other'}));
 assert.throws(()=>owner.removeItem(SCRIPT_STORE_KEY));assert.equal(JSON.stringify([...data]),before);
});
