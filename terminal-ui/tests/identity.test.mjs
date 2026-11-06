import {test} from 'node:test';import assert from 'node:assert/strict';
import {identityCatalog,identitiesFor,verifiedIdentity,identityPatch,createIdentityCatalog} from '../integration/identity-catalog.mjs';
const payload=(user='a')=>({user_id:user,execution_authorized:false,source:'owned_workspace_identities',accounts:[{id:'stock',label:'Stock Paper',markets:['stocks'],mode:'paper',paper_eligible:true},{id:'cex',label:'CEX Read',markets:['cex'],mode:'read_only',paper_eligible:false}],wallets:[{id:'eth',label:'ETH wallet',chain_id:'1'},{id:'base',label:'Base wallet',chain_id:'8453'},{id:'unknown',label:'Unknown chain',chain_id:null}]});
test('catalog exposes only whitelisted metadata and separates account markets and wallet chains',()=>{
 const raw=payload();raw.accounts[0].secret='not-copied';const data=identityCatalog(raw);assert.equal(data.accounts[0].secret,undefined);
 assert.deepEqual(identitiesFor({market:'stocks'},data).accounts.map(a=>a.id),['stock']);assert.deepEqual(identitiesFor({market:'onchain',chainId:'8453'},data).wallets.map(w=>w.id),['base']);
 assert.throws(()=>identityCatalog({...raw,execution_authorized:true}));assert.throws(()=>identityCatalog({...raw,accounts:[raw.accounts[0],raw.accounts[0]]}));
});
test('restored foreign identities and incompatible markets are cleared without granting Paper',()=>{
 const context={market:'stocks',accountId:'foreign',walletId:'eth',executionMode:'PAPER'};assert.deepEqual(identityPatch(context,identityCatalog(payload())),{accountId:'',walletId:'',executionMode:'READ_ONLY'});
 const stock={...context,accountId:'stock',walletId:''};assert.equal(verifiedIdentity(stock,identityCatalog(payload())).paperEligible,true);assert.deepEqual(identityPatch(stock,null),{executionMode:'READ_ONLY'});
 const cex={market:'cex',accountId:'cex',executionMode:'PAPER'};assert.deepEqual(identityPatch(cex,identityCatalog(payload())),{executionMode:'READ_ONLY'});
});
test('late catalog responses cannot replace a newer session or recover revoked choices',async()=>{
 const pending=[];let identity='session-a';const client=createIdentityCatalog({identity:()=>identity,request:()=>new Promise(resolve=>pending.push(resolve))});
 const first=client.refresh();identity='session-b';client.invalidate();const second=client.refresh();pending[1](payload('b'));await second;pending[0](payload('a'));await first;assert.equal(client.snapshot().userId,'b');
 const view=client.snapshot();view.accounts[0].label='changed';assert.equal(client.snapshot().accounts[0].label,'Stock Paper');client.invalidate();assert.equal(client.snapshot(),null);
});
test('catalog refresh revokes old verification before waiting and failed refresh does not reuse stale choices',async()=>{
 let fail=false,notifications=0;const client=createIdentityCatalog({request:async()=>{if(fail)throw Object.assign(Error('offline'),{status:503});return payload();},notify:()=>notifications++});await client.refresh();assert.ok(client.snapshot());fail=true;const pending=client.refresh();assert.equal(client.snapshot(),null);assert.equal(client.status().loading,true);await pending;assert.equal(client.snapshot(),null);assert.match(client.status().error,/不可用/);assert.ok(notifications>=4);
});
