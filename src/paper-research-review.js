import {paperOrderIntent,paperThesisMatches} from './paper-order-workflow.js';
const invalid=message=>Object.assign(new Error(message),{local:true});
export function researchThesisReviewBody(thesisId,decision,summary,confidence){
 if(!thesisId||!['supports','weakens','invalidates'].includes(decision)||typeof summary!=='string'||summary.trim().length<8||summary.length>2000||confidence===null||String(confidence).trim()===''||!Number.isFinite(Number(confidence))||Number(confidence)<0||Number(confidence)>1)throw invalid('请选择判断，并填写8至2000字的人工审阅理由及0至1的判断强度。');
 return {thesis_id:thesisId,decision,human_summary:summary.trim(),confidence:Number(confidence)};
}
export function validateResearchThesisReview(packet,report,thesisId,decision){
 if(packet?.execution_available!==false||packet.report_id!==report?.id||packet.thesis_id!==thesisId||packet.checkpoint?.thesis_id!==thesisId||!packet.checkpoint?.id||packet.trace?.research_report_id!==report.id||packet.trace?.data_snapshot_id!==report.data_snapshot_id||packet.trace?.thesis_id!==thesisId||packet.trace?.thesis_checkpoint_id!==packet.checkpoint.id||packet.trace?.checkpoint_decision!==decision)throw invalid('人工审阅回执与报告或假设不匹配，请重新读取。');
 return packet;
}
export async function previewResearchPaperOrder(request,form,report,theses=[]){
 const input=paperOrderIntent(form);
 if(!form.thesisId||!theses.some(thesis=>paperThesisMatches(thesis,form))||!report?.data_snapshot_id||report.id!==form.reportId||form.evidenceMode!=='report')throw invalid('请先选择兼容报告与当前账户假设，并记录人工审阅。');
 const plan=await request(`/reports/${encodeURIComponent(report.id)}/create-plan-and-evaluate`,{method:'POST',body:{thesis_id:form.thesisId,account_id:form.accountId,side:input.side,order_type:input.order_type,quantity:input.quantity,limit_price:input.limit_price,user_rationale:input.user_rationale}});
 const intent=plan?.order_intent,trace=plan?.trace;
 if(plan?.execution_available!==false||!intent?.id||intent.account_id!==form.accountId||intent.asset_id!==form.assetId||intent.investment_thesis_id!==form.thesisId||intent.source_type!=='research_report'||intent.source_id!==report.id||intent.side!==input.side||intent.order_type!==input.order_type||Number(intent.quantity)!==input.quantity||Number(intent.limit_price)!==input.limit_price||trace?.research_report_id!==report.id||trace?.data_snapshot_id!==report.data_snapshot_id||trace?.thesis_id!==form.thesisId||!trace?.thesis_checkpoint_id||!Array.isArray(plan.gates)||typeof plan.all_gates_passed!=='boolean')throw invalid('研究计划返回的账户、标的或证据不匹配，请重新读取。');
 const gates={all_passed:plan.all_gates_passed,gates:plan.gates};
 if(!gates.all_passed)return {intent,gates,draft:null,evidence:null};
 if(new Set(plan.gates.map(gate=>gate.gate_type)).size!==5||!['RESEARCH_GATE','THESIS_GATE','RISK_GATE','BEHAVIOR_GATE','EXECUTION_GATE'].every(type=>plan.gates.some(gate=>gate.gate_type===type))||plan.gates.some(gate=>gate.status!=='PASSED'||gate.order_intent_id!==intent.id))throw invalid('门禁回执不完整，请重新读取。');
 const draft=await request(`/orders/intents/${encodeURIComponent(intent.id)}/draft`,{method:'POST',body:{order_intent_id:intent.id}});
 if(!draft?.id||draft.order_intent_id!==intent.id||draft.approval_status!=='pending')throw invalid('研究计划草稿回执不匹配，请重新读取。');
 return {intent,gates,draft,evidence:null};
}
