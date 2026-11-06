import {test} from 'node:test';import assert from 'node:assert/strict';
import {savePaperDraft,paperDraftScope,emptyPaperForm} from '../../src/paper-draft-buffer.js';
test('actual parent bridge clears local logout and explicit expiry while preserving same-user reauthentication',async()=>{
 const values=new Map();globalThis.sessionStorage={getItem:k=>values.get(k)||null,setItem:(k,v)=>values.set(k,v),removeItem:k=>values.delete(k)};
 globalThis.window={dispatchEvent:()=>{}};globalThis.CustomEvent=class {constructor(type){this.type=type;}};
 let user='alice';globalThis.fetch=async url=>({ok:true,status:200,json:async()=>url.endsWith('/login')?{session_token:'controlled-token',user:{user_id:user,role:'owner'},expires_at:new Date(Date.now()+60000).toISOString()}: {}});
 await import('../integration/backend-service.mjs');const bridge=window.TerminalBackend,b=window.TerminalDraftBuffer;
 const write=()=>savePaperDraft(paperDraftScope({userId:user,market:'stocks',symbol:'AAPL'}),{...emptyPaperForm(),accountId:'a',quantity:'3'},b);
 write();assert.equal(b.size(),2);await bridge.logout();assert.equal(b.size(),0);assert.equal(values.size,0);
 await bridge.login('fixture');write();await bridge.login('fixture');assert.equal(b.size(),2);
 user='bob';await bridge.login('fixture');assert.equal(b.size(),0);
 write();bridge.clearSession();assert.equal(b.size(),0);assert.equal(values.size,0);
});
