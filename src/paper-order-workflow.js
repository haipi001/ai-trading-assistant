const invalid=message=>Object.assign(new Error(message),{local:true});
export function paperOrderIntent(form) {
  const quantity=Number(form.quantity),price=Number(form.price);
  const mode=form.evidenceMode||(form.reportId?'report':'manual');
  if(!['manual','report'].includes(mode)||!form.accountId||!form.assetId||(mode==='report'&&!form.reportId))throw invalid('请选择模拟账户、标的和证据方式');
  if(!['buy','sell'].includes(form.side)||!Number.isFinite(quantity)||quantity<=0||!Number.isFinite(price)||price<=0)throw invalid('数量和限价必须为正数');
  if(!(form.rationale||'').trim())throw invalid('请填写本次交易理由');
  return {source_type:'manual',asset_id:form.assetId,account_id:form.accountId,side:form.side,order_type:'limit',quantity,limit_price:price,
    rationale:form.rationale.trim(),user_rationale:form.rationale.trim(),...(form.thesisId?{investment_thesis_id:form.thesisId}:{}),evidence_json:mode==='report'?{report_id:form.reportId}:{}};
}
export async function previewPaperOrder(request,form,report){
  const body=paperOrderIntent(form);
  const manual=(form.evidenceMode||(form.reportId?'report':'manual'))==='manual';
  if(!manual&&(!report?.data_snapshot_id||report.id!==form.reportId))throw invalid('研究证据已失效，请重新选择');
  const intent=await request('/orders/intents',{method:'POST',body});
  const evidence=manual?await request(`/orders/intents/${encodeURIComponent(intent.id)}/manual-evidence`,{method:'POST'}):null;
  if(manual&&(!evidence?.data_snapshot_id||evidence.order_intent_id!==intent.id))throw invalid('手动行情凭据与订单不匹配，请重新读取');
  const gates=await request('/decision-gates/evaluate',{method:'POST',body:{order_intent_id:intent.id,data_snapshot_id:manual?evidence.data_snapshot_id:report.data_snapshot_id}});
  if(!gates.all_passed)return {intent,gates,draft:null,evidence};
  const draft=await request(`/orders/intents/${encodeURIComponent(intent.id)}/draft`,{method:'POST',body:{order_intent_id:intent.id}});
  return {intent,gates,draft,evidence};
}
export function paperAccounts(accounts){return accounts.filter(account=>account.mode==='paper'&&!account.live_trading_enabled);}

export function paperExecutionBody(draftId,price,attempts,makeKey=()=>crypto.randomUUID()){
  const fillPrice=Number(price);
  if(!draftId||!Number.isFinite(fillPrice)||fillPrice<=0)throw invalid('请先核对模拟草稿和限价');
  const previous=attempts.get(draftId);
  if(previous&&previous.fill_price!==fillPrice)throw invalid('同次执行参数已变化，请重新预览草稿');
  if(!previous)attempts.set(draftId,{fill_price:fillPrice,idempotency_key:makeKey()});
  return {...attempts.get(draftId)};
}

export function paperUnknownOutcome(error){
  return !error?.local&&(!error?.status||error.status>=500||error.code==='paper_execution_outcome_unknown');
}

export function paperRestoredEvidence(intent,draft,timeline=[]){
  if(intent.evidence_json?.manual_snapshot_id)return {evidenceMode:'manual',reportId:''};
  const gateId=draft.decision_gate_results?.RESEARCH_GATE?.gate_id;
  const bound=timeline.find(row=>row.id===gateId&&row.gate_type==='RESEARCH_GATE'&&row.order_intent_id===intent.id);
  const reportId=intent.evidence_json?.report_id||intent.evidence_json?.research_report_id||bound?.evidence_json?.research_report_id||'';
  return {evidenceMode:reportId?'report':'manual',reportId};
}
