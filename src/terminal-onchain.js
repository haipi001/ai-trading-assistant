const ADDRESS=/^0x[0-9a-fA-F]{40}$/;
export function onchainScope(c){return JSON.stringify([c.identityUserId||'',c.walletId,c.chainId,(c.contractAddress||'').toLowerCase(),c.contextVersion,c.authorizationVersion]);}
export function onchainSelection(c){if(c.market!=='onchain'||!c.walletId||!/^[1-9][0-9]{0,19}$/.test(c.chainId)||c.contractAddress&&!ADDRESS.test(c.contractAddress))throw Error('请选择兼容的链与钱包');return {chain_id:c.chainId,contract_address:(c.contractAddress||'').toLowerCase(),context_version:c.contextVersion};}
export function onchainPath(c){const selection=onchainSelection(c);return '/api/v2/workspaces/onchain/'+encodeURIComponent(c.walletId)+'?'+new URLSearchParams(selection);}
export function onchainPacket(value,c){
 const selection=onchainSelection(c),date=v=>typeof v==='string'&&Number.isFinite(Date.parse(v)),amount=v=>typeof v==='string'&&/^[0-9]+(?:\.[0-9]+)?$/.test(v)&&v.length<130;
 if(!value||value.wallet?.id!==c.walletId||!ADDRESS.test(value.wallet?.address)||value.chain_id!==selection.chain_id||value.contract_address!==selection.contract_address||value.context_version!==c.contextVersion||value.execution_available!==false||value.signing_available!==false)throw Error('链上材料与当前上下文不一致');
 if(value.last_read_error!=null&&(value.last_read_error.code!=='onchain_rpc_unavailable'||!date(value.last_read_error.as_of)))throw Error('链上读取状态无效');
 const s=value.snapshot;
 if(s!==null){if(!s||typeof s.id!=='string'||!date(s.as_of)||typeof s.stale!=='boolean'||s.source!=='evm_rpc_readonly'||!Number.isSafeInteger(s.block_number)||s.block_number<0||s.finality!=='observed_not_finalized'||!Array.isArray(s.balances)||s.balances.length!==(selection.contract_address?2:1))throw Error('链上快照格式无效');
  s.balances.forEach((b,i)=>{if(!amount(b.amount)||!Number.isInteger(b.decimals)||b.decimals<0||b.decimals>36||typeof b.symbol!=='string'||(i===0?b.contract_address!==null:b.contract_address!==selection.contract_address))throw Error('链上余额身份无效');});
 }
 for(const key of ['recorded_allowances','recorded_protocols']){if(!Array.isArray(value[key])||value[key].length>200||value[key].some(row=>typeof row.id!=='string'||typeof row.source!=='string'||!date(row.as_of)||row.contract_address!=null&&!ADDRESS.test(row.contract_address)))throw Error('链上记录格式无效');}
 if(value.recorded_allowances.some(row=>!amount(row.amount)||!ADDRESS.test(row.spender)))throw Error('授权记录格式无效');
 if(selection.contract_address&&[...value.recorded_allowances,...value.recorded_protocols].some(row=>(row.contract_address||'').toLowerCase()!==selection.contract_address))throw Error('合约记录不匹配');
 if(value.coverage?.allowances!=='recorded_only_not_full_index'||value.coverage?.protocols!=='recorded_only_not_full_index'||typeof value.coverage.allowances_truncated!=='boolean'||typeof value.coverage.protocols_truncated!=='boolean'||!Array.isArray(value.limitations)||value.limitations.some(v=>typeof v!=='string'))throw Error('链上覆盖范围无效');
 return structuredClone(value);
}
export function onchainStale(asOf,now=Date.now()){const age=now-Date.parse(asOf);return !Number.isFinite(age)||age< -30000||age>600000;}
export function onchainResearchQuestion(value,c,kind){
 const packet=onchainPacket(value,c),s=packet.snapshot;
 const evidence={wallet_id:c.walletId,chain_id:c.chainId,contract_address:packet.contract_address,context_version:c.contextVersion,snapshot:s?{...s,stale:s.stale||onchainStale(s.as_of)}:null,
  allowances:packet.recorded_allowances.slice(0,3),protocols:packet.recorded_protocols.slice(0,3),coverage:packet.coverage,limitations:packet.limitations};
 evidence.omitted_records={allowances:packet.recorded_allowances.length-evidence.allowances.length,protocols:packet.recorded_protocols.length-evidence.protocols.length};
 const render=()=>`${kind}。以下是当前只读后端材料的摘录，不是交易指令。仅依据材料区分事实、推断和未知，引用快照ID、区块和记录ID；历史/示例记录不视为当前链上事实。未索引的授权或协议不能判断为不存在；不生成报价、估值、签名或撤销授权操作。\n${JSON.stringify(evidence)}`;
 while(render().length>4000&&(evidence.protocols.length||evidence.allowances.length)){const field=evidence.protocols.length?'protocols':'allowances';evidence[field].pop();evidence.omitted_records[field]++;}
 const text=render();if(text.length>4000)throw Error('研究材料过长，请重新读取');
 return text;
}
export function onchainResearchAttachment(value,c){
 const packet=onchainPacket(value,c),s=packet.snapshot;
 if(!s||s.stale||onchainStale(s.as_of)||packet.last_read_error)throw Error('请先成功更新当前链上快照，再准备研究附件');
 return {scope:onchainScope(c),reference:{schema_version:1,snapshot_id:s.id,wallet_id:c.walletId,chain_id:c.chainId,contract_address:packet.contract_address,context_version:c.contextVersion,allowance_ids:packet.recorded_allowances.slice(0,20).map(row=>row.id),protocol_ids:packet.recorded_protocols.slice(0,20).map(row=>row.id)},preview:{wallet_address:packet.wallet.address,as_of:s.as_of,block_number:s.block_number,balances:s.balances,allowance_count:Math.min(20,packet.recorded_allowances.length),protocol_count:Math.min(20,packet.recorded_protocols.length),records_omitted:packet.recorded_allowances.length>20||packet.recorded_protocols.length>20}};
}
export function onchainAttachmentMatches(value,c){return !!c&&c.market==='onchain'&&!!value&&value.scope===onchainScope(c)&&value.reference?.wallet_id===c.walletId&&value.reference?.chain_id===c.chainId&&value.reference?.contract_address===(c.contractAddress||'').toLowerCase()&&value.reference?.context_version===c.contextVersion;}
export function researchOnchainContext(value){
 const ids=new Set();
 if(!value||value.schema_version!==1||value.server_retrieved!==true||value.independently_verified!==false||!ADDRESS.test(value.wallet_public_address)||typeof value.wallet_id!=='string'||!/^[1-9][0-9]{0,19}$/.test(value.chain_id)||value.contract_address&&!ADDRESS.test(value.contract_address)||!Number.isSafeInteger(value.context_version)||typeof value.content_hash!=='string'||!/^[0-9a-f]{64}$/.test(value.content_hash)||!Array.isArray(value.entries)||value.entries.length<1||value.entries.length>41)throw Error('链上研究附件格式无效');
 for(const row of value.entries){if(!row||!/^([WAP][1-9][0-9]?)$/.test(row.id)||ids.has(row.id)||typeof row.record_id!=='string'||!Number.isFinite(Date.parse(row.as_of))||typeof row.source!=='string')throw Error('链上研究引用格式无效');ids.add(row.id);}
 const ref=value.reference;if(!ref||ref.schema_version!==1||ref.wallet_id!==value.wallet_id||ref.chain_id!==value.chain_id||ref.contract_address!==value.contract_address||ref.context_version!==value.context_version||ref.snapshot_id!==value.source_snapshot_id||!Array.isArray(ref.allowance_ids)||!Array.isArray(ref.protocol_ids))throw Error('链上研究身份不一致');
 const expected=new Map([['W1',ref.snapshot_id]]);
 for(const [field,prefix] of [['allowance_ids','A'],['protocol_ids','P']]){if(ref[field].length>20||new Set(ref[field]).size!==ref[field].length)throw Error('重复链上记录引用');ref[field].forEach((rid,index)=>expected.set(prefix+(index+1),rid));}
 if(expected.size!==value.entries.length)throw Error('链上引用数量不一致');
 for(const row of value.entries){
  if(expected.get(row.id)!==row.record_id)throw Error('链上记录引用不一致');
  if(row.id!=='W1'){
   if(typeof row.stale!=='boolean'||row.contract_address!=null&&!ADDRESS.test(row.contract_address)||value.contract_address&&row.contract_address!==value.contract_address)throw Error('链上记录合约无效');
   if(row.id.startsWith('A')&&(row.kind!=='allowance'||typeof row.spender!=='string'||typeof row.amount!=='string'||!/^\d+(\.\d+)?$/.test(row.amount)||typeof row.risk_level!=='string'))throw Error('授权材料无效');
   if(row.id.startsWith('P')&&(row.kind!=='protocol'||typeof row.protocol!=='string'||typeof row.position_type!=='string'||row.usd_value!==null&&typeof row.usd_value!=='string'))throw Error('协议材料无效');
  }
 }
 const balance=value.entries[0];if(balance.id!=='W1'||balance.record_id!==value.source_snapshot_id||balance.block_number!==value.block_number||balance.kind!=='balances'||balance.source!=='evm_rpc_readonly'||!Number.isSafeInteger(balance.block_number)||!Array.isArray(balance.balances)||balance.balances.length<1||balance.balances.length>2||balance.balances.some(row=>typeof row.amount!=='string'||!/^\d+(\.\d+)?$/.test(row.amount)))throw Error('链上研究余额无效');
 if(balance.balances.length!==(value.contract_address?2:1)||balance.balances.some((row,index)=>row.contract_address!==(index?value.contract_address:null)))throw Error('链上研究合约不一致');
 return value;
}
