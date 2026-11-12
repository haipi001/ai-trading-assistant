const invalid=message=>Object.assign(new Error(message),{local:true});
export function manualPaperThesisBody(form,accountId,assetId){
 const lines=value=>String(value||'').split('\n').map(row=>row.trim()).filter(Boolean);
 const reason=String(form.reason||'').trim(),target=String(form.target||'').trim(),drivers=lines(form.drivers),invalidation=lines(form.invalidation),horizon=String(form.horizon||'').trim();
 const loss=Number(form.lossPct),confidence=Number(form.confidence);
 if(!accountId||!assetId||reason.length<8||reason.length>4000||target.length<8||target.length>2000||!horizon||horizon.length>64||!drivers.length||!invalidation.length||drivers.length>20||invalidation.length>20||[...drivers,...invalidation].some(row=>row.length>500)||!String(form.lossPct||'').trim()||!String(form.confidence??'').trim()||!Number.isFinite(loss)||loss<=0||loss>100||!Number.isFinite(confidence)||confidence<0||confidence>1)throw invalid('请完整填写理由、驱动因素、失效条件、期限、目标、损失容忍度和判断强度。');
 return {account_id:accountId,asset_id:assetId,entry_reason:reason,key_drivers:drivers,invalidation_conditions:invalidation,expected_horizon:horizon,target_condition:target,max_loss_tolerance_pct:loss/100,confidence};
}
export function manualPaperThesisResponse(packet,accountId,assetId){
 const thesis=packet?.thesis;
 if(packet?.execution_available!==false||!thesis?.id||thesis.account_id!==accountId||thesis.asset_id!==assetId||thesis.source!=='terminal_manual'||thesis.status!=='active'||thesis.position_plan_json?.execution_available!==false||thesis.position_plan_json?.human_authored!==true)throw invalid('假设回执与当前账户或标的不匹配，请重新读取列表。');
 return thesis;
}
