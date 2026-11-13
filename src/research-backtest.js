import {apiRequest} from './backend-api.js';
import {savedBacktestMaterial} from './saved-backtests.js';
export function backtestAttachment(packet,run,userId,scope){
 savedBacktestMaterial(packet,run);
 if(!userId||!scope)throw Error('unverified backtest workspace');
 return {ownerUserId:userId,workspaceScope:scope,material:packet.material,reference:{snapshot_id:packet.snapshot_id,backtest_run_id:run.id,content_hash:packet.material.content_hash}};
}
export function backtestAttachmentMatches(attachment,userId,scope,now=Date.now()){
 try{
  const m=attachment?.material,r=attachment?.reference;
  savedBacktestMaterial({snapshot_id:r?.snapshot_id,material:m,execution_available:false},{id:r?.backtest_run_id,strategy_playbook_id:m?.strategy_playbook_id});
  const age=now-Date.parse(m.captured_at);
  return Boolean(userId&&scope&&attachment.ownerUserId===userId&&attachment.workspaceScope===scope&&r.content_hash===m.content_hash&&Number.isFinite(age)&&age>=-30000&&age<=600000);
 }catch{return false;}
}
export function backtestRequestReference(attachment,userId,scope,now=Date.now()){
 if(!backtestAttachmentMatches(attachment,userId,scope,now))throw Error('回测材料已过期或工作区变化，请重新准备。');
 return {...attachment.reference};
}

export async function requestBacktestResearch({attachment,userId,scope,question,signal}){
 const reference=backtestRequestReference(attachment,userId,scope);
 if(typeof question!=='string'||!question.trim()||question.length>4000)throw Error('请输入最多4000字的研究问题。');
 const result=await apiRequest('/production/human-control/llm/chat',{method:'POST',body:{question,backtest_context:reference},signal,timeout:90000});
 return validateBacktestResult(result,attachment);
}
export function validateBacktestResult(result,attachment){
 const reference=attachment.reference;
 if(!['ok','failed','blocked'].includes(result?.status)||result.execution_available!==false)throw Error('invalid backtest research response');
 if(result.status==='ok'){
  const material=result.provided_backtest;
  savedBacktestMaterial({snapshot_id:reference.snapshot_id,execution_available:false,material},{id:reference.backtest_run_id,strategy_playbook_id:attachment.material.strategy_playbook_id});
  if(['summary','bullish_case','bearish_case','limitations','suggested_action'].some(key=>typeof result[key]!=='string')||!Array.isArray(result.key_risks)||result.key_risks.some(value=>typeof value!=='string'))throw Error('invalid backtest research text');
  const text=[result.summary,result.bullish_case,result.bearish_case,result.limitations,result.suggested_action,...result.key_risks].join('\n');
  if(!text.includes('[BT1]'))throw Error('missing backtest source marker');
  if(result.context_scope!=='owned_frozen_backtest_material'||material?.content_hash!==reference.content_hash||material.backtest_run_id!==reference.backtest_run_id||!result.backtest_context_snapshot_id||result.cited_backtest_ids?.length!==1||result.cited_backtest_ids[0]!=='BT1')throw Error('backtest research source mismatch');
 }
 return result;
}
