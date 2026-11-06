import {test} from 'node:test';import assert from 'node:assert/strict';
import {onchainPacket,onchainScope,onchainResearchQuestion,onchainStale} from '../../src/terminal-onchain.js';
const c={market:'onchain',walletId:'wallet-a',chainId:'1',contractAddress:'0x'+'a'.repeat(40),contextVersion:7,identityUserId:'user-a'};
function value(){return {wallet:{id:'wallet-a',address:'0x'+'1'.repeat(40)},chain_id:'1',contract_address:c.contractAddress,context_version:7,execution_available:false,signing_available:false,snapshot:{id:'snapshot-a',source:'evm_rpc_readonly',as_of:'2026-11-05T12:00:00Z',stale:true,block_number:100,finality:'observed_not_finalized',balances:[{symbol:'ETH',contract_address:null,decimals:18,amount:'1.000000000000000001'},{symbol:'ERC20',contract_address:c.contractAddress,decimals:6,amount:'12.34'}]},recorded_allowances:[],recorded_protocols:[],coverage:{allowances:'recorded_only_not_full_index',protocols:'recorded_only_not_full_index',allowances_truncated:false,protocols_truncated:false},limitations:['No index','No USD']};}
test('onchain packets bind exact wallet chain contract and context version with no execution permission',()=>{const v=value();assert.equal(onchainPacket(v,c).snapshot.balances[0].amount,'1.000000000000000001');for(const patch of [{walletId:'b'},{chainId:'8453'},{contractAddress:'0x'+'b'.repeat(40)},{contextVersion:8}])assert.throws(()=>onchainPacket(v,{...c,...patch}));v.execution_available=true;assert.throws(()=>onchainPacket(v,c));assert.notEqual(onchainScope(c),onchainScope({...c,identityUserId:'b'}));});
test('malformed balances, foreign record identities and unknown coverage are rejected',()=>{for(const mutate of [v=>v.snapshot.balances[1].amount='NaN',v=>v.snapshot.balances[1].contract_address='0x'+'b'.repeat(40),v=>v.snapshot.block_number=1.2,v=>v.coverage.protocols='complete',v=>v.recorded_protocols.push({id:'p',source:'unverified_record',as_of:'2026-11-05T12:00:00Z',contract_address:'0x'+'b'.repeat(40)})]){const v=value();mutate(v);assert.throws(()=>onchainPacket(v,c));}});
test('research material retains snapshot and provenance with an explicit bounded excerpt',()=>{const v=value();v.recorded_protocols=Array.from({length:20},(_,i)=>({id:'p'+i,source:'unverified_record',as_of:v.snapshot.as_of,contract_address:c.contractAddress,protocol:'P'.repeat(128),position_type:'exposure',symbol:'X',usd_value:null}));const text=onchainResearchQuestion(v,c,'解释协议暴露');assert.ok(text.length<=4000);const evidence=JSON.parse(text.slice(text.indexOf('\n')+1));assert.equal(evidence.snapshot.id,'snapshot-a');assert.equal(evidence.snapshot.stale,true);assert.equal(evidence.context_version,7);assert.ok(evidence.omitted_records.protocols>0);assert.equal(evidence.coverage.protocols,'recorded_only_not_full_index');assert.equal(onchainStale('2026-11-05T12:00:00Z',Date.parse('2026-11-05T12:11:00Z')),true);assert.equal(onchainStale('2026-11-05T12:00:00Z',Date.parse('2026-11-05T11:00:00Z')),true);});

test('typed AI attachments send record references and expire on context changes',async()=>{
 const {onchainResearchAttachment,onchainAttachmentMatches}=await import('../../src/terminal-onchain.js');
 const v=value();v.snapshot.as_of=new Date().toISOString();v.snapshot.stale=false;
 const attachment=onchainResearchAttachment(v,c);
 assert.equal(attachment.reference.snapshot_id,v.snapshot.id);
 assert.equal(attachment.reference.context_version,c.contextVersion);
 assert.equal(attachment.reference.balances,undefined);
 assert.equal(onchainAttachmentMatches(attachment,c),true);
 for(const patch of [{contextVersion:8},{walletId:'other'},{chainId:'8453'},{identityUserId:'another-user'}])assert.equal(onchainAttachmentMatches(attachment,{...c,...patch}),false);
 v.last_read_error={code:'onchain_rpc_unavailable',as_of:new Date().toISOString()};
 assert.throws(()=>onchainResearchAttachment(v,c));
});
