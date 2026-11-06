import {researchOnchainContext} from './terminal-onchain.js';
const id=value=>typeof value==='string'&&/^[0-9a-f-]{36}$/.test(value);
export function onchainHistoryList(value){
 if(!value||value.execution_available!==false||typeof value.has_more!=='boolean'||!Array.isArray(value.items)||value.items.length>20)throw Error('历史列表格式无效');
 const ids=new Set();
 for(const row of value.items){if(!id(row.snapshot_id)||ids.has(row.snapshot_id)||!Number.isSafeInteger(row.context_version)||row.context_version<0||!['ok','failed',null].includes(row.reply_status??null)||!Number.isFinite(Date.parse(row.created_at)))throw Error('历史列表条目无效');ids.add(row.snapshot_id);}
 return value;
}
export function onchainHistoryArtifact(value,context,snapshotId){
 if(!value||value.execution_available!==false||value.snapshot_id!==snapshotId||!id(snapshotId))throw Error('历史材料权限字段无效');
 const c=researchOnchainContext(value.provided_onchain);
 if(c.wallet_id!==context.walletId||c.chain_id!==context.chainId||c.contract_address!==(context.contractAddress||'').toLowerCase())throw Error('历史材料身份不一致');
 const reply=value.validated_reply;
 if(value.reply_status==='ok'){
  const allowed=new Set(c.entries.map(row=>row.id));
  if(!reply||typeof reply.bullish_case!=='string'||typeof reply.bearish_case!=='string'||!Array.isArray(reply.key_risks)||reply.key_risks.length>10||reply.key_risks.some(v=>typeof v!=='string')||reply.suggested_action!=null&&typeof reply.suggested_action!=='string'||reply.confidence!=null&&(typeof reply.confidence!=='number'||!Number.isFinite(reply.confidence)||reply.confidence<0||reply.confidence>1))throw Error('历史回复研究字段无效');
  if(!reply||reply.status!=='ok'||typeof reply.summary!=='string'||!reply.summary.trim()||typeof reply.limitations!=='string'||!Array.isArray(reply.cited_onchain_ids)||reply.cited_onchain_ids.some(key=>!allowed.has(key)))throw Error('历史回复无效');
 }else if(!['failed',null].includes(value.reply_status??null)||reply!=null)throw Error('失败请求不能附带有效回复');
 return value;
}
