import test from 'node:test';
import assert from 'node:assert/strict';
import {paperReviewBufferKey,readPaperReviewBuffer,savePaperReviewBuffer} from '../../src/paper-review-buffer.js';
test('manual review buffers isolate identity, account scope, fill and server revision',()=>{
 const context={execution:{id:'fill'},post_trade_review:{id:'review',execution_id:'fill',updated_at:'v1'}};
 const key=paperReviewBufferKey('user','account',context),data=new Map(),storage={getItem:k=>data.get(k),setItem:(k,v)=>data.set(k,v)};
 const notes='n'.repeat(8000);savePaperReviewBuffer(storage,key,notes);assert.equal(readPaperReviewBuffer(storage,key),notes);
 for(const other of [paperReviewBufferKey('other','account',context),paperReviewBufferKey('user','other',context),paperReviewBufferKey('user','account',{...context,post_trade_review:{...context.post_trade_review,updated_at:'v2'}})])assert.equal(readPaperReviewBuffer(storage,other,'server'),'server');
 assert.equal(paperReviewBufferKey('', 'account',context),null);
 assert.throws(()=>savePaperReviewBuffer(storage,key,'n'.repeat(8001)));
 data.set(key,'bad-json');assert.throws(()=>readPaperReviewBuffer(storage,key));
});

test('legacy credential-bearing key is removed while retaining matching draft text',async()=>{
 const {migratePaperReviewBuffer}=await import('../../src/paper-review-buffer.js');
 const context={execution:{id:'fill'},post_trade_review:{id:'review',execution_id:'fill',updated_at:'v1'}},identity='Bearer test-only-not-a-real-token',scope='scope';
 const key=paperReviewBufferKey('user',scope,context),legacy='terminal-paper-review-buffer-v1:'+JSON.stringify([identity,scope,'fill','review','v1']);
 const data=new Map([[legacy,JSON.stringify({version:1,notes:'unsaved note'})]]),storage={getItem:k=>data.get(k)??null,setItem:(k,v)=>data.set(k,v),removeItem:k=>data.delete(k)};
 migratePaperReviewBuffer(storage,identity,scope,context,key);
 assert.equal(data.has(legacy),false);assert.equal(readPaperReviewBuffer(storage,key),'unsaved note');
 assert.equal([...data.keys()].some(k=>k.includes(identity)),false);
});
