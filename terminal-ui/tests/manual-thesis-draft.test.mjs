import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {createPersistentPaperDrafts} from '../integration/persistent-paper-drafts.mjs';
import {emptyManualThesisForm,paperDraftScope,saveManualThesisDraft,readManualThesisDraft,savePaperDraft,readPaperDraft,emptyPaperForm} from '../../src/paper-draft-buffer.js';
const form={...emptyManualThesisForm(),reason:'Original human research rationale',drivers:'Recorded source to verify',invalidation:'Reason breaks',horizon:'swing',target:'Reassess original evidence',lossPct:'2',confidence:'0.6'};
function storage(){const values=new Map();return{getItem:key=>values.get(key)||null,setItem:(key,value)=>values.set(key,value),removeItem:key=>values.delete(key)};}
const scope=paperDraftScope({userId:'user-a',market:'stocks',symbol:'AAPL',venue:'NASDAQ'});
test('manual fields and unconfirmed outcome survive a terminal buffer reload without carrying authority',()=>{
 const disk=storage(),first=createPersistentPaperDrafts(disk);saveManualThesisDraft(scope,'account-a','asset-a',form,'unconfirmed',first);
 const reloaded=createPersistentPaperDrafts(disk),saved=readManualThesisDraft(scope,'account-a','asset-a',reloaded);
 assert.equal(saved.reason,form.reason);assert.equal(saved.outcome,'unconfirmed');assert.equal(saved.approval_status,undefined);assert.equal(saved.execution_mode,undefined);
 assert.equal(readManualThesisDraft(scope,'other-account','asset-a',reloaded),null);assert.equal(readManualThesisDraft(scope,'account-a','other-asset',reloaded),null);
 for(const patch of [{userId:'user-b'},{market:'cex'},{symbol:'MSFT'},{venue:'OTHER'}])assert.equal(readManualThesisDraft(paperDraftScope({userId:'user-a',market:'stocks',symbol:'AAPL',venue:'NASDAQ',...patch}),'account-a','asset-a',reloaded),null);
});
test('legacy order forms remain intact; manual drafts reject extra authority and clear with session data',()=>{
 const disk=storage(),buffer=createPersistentPaperDrafts(disk);savePaperDraft(scope,{...emptyPaperForm(),accountId:'account-a',quantity:'1'},buffer);saveManualThesisDraft(scope,'account-a','asset-a',form,'draft',buffer);
 assert.throws(()=>saveManualThesisDraft(scope,'account-a','asset-a',{...form,approval_status:'approved'},'draft',buffer));assert.throws(()=>saveManualThesisDraft(scope,'account-a','asset-a',form,'completed',buffer));
 assert.equal(readPaperDraft(scope,'account-a',createPersistentPaperDrafts(disk)).quantity,'1');
 saveManualThesisDraft(scope,'account-a','asset-a',emptyManualThesisForm(),'draft',buffer);assert.equal(readManualThesisDraft(scope,'account-a','asset-a',buffer).reason,'');buffer.clear();assert.equal(createPersistentPaperDrafts(disk).size(),0);
});
const source=readFileSync(new URL('../../src/paper-thesis-editor.jsx',import.meta.url),'utf8');
const start=source.indexOf(' async function save(){'),end=source.indexOf('\n const locked=',start);
assert.ok(start>=0&&end>start);
test('shipped handler persists uncertainty before sending, and a storage error prevents a new request',async()=>{
 for(const storageFails of [false,true]){
  const events=[];const sandbox={pending:{current:false},uncertain:false,saved:false,current:()=>true,manualPaperThesisBody:()=>({}),form,account:{id:'account-a'},asset:{id:'asset-a'},draftScope:scope,saveManualThesisDraft:(_s,_a,_b,_f,outcome)=>{events.push(outcome);if(storageFails)throw Error('quota');},setNotice(){},setBusy(){},setSaved(){},setUncertain(){},onCreated(){},manualPaperThesisResponse:()=>({id:'saved'}),emptyManualThesisForm,apiRequest:async()=>{events.push('request');return {};}};
  vm.runInNewContext(source.slice(start,end)+';globalThis.save=save;',sandbox);await sandbox.save();
  assert.equal(events[0],'unconfirmed');assert.equal(events.includes('request'),!storageFails);
 }
});
