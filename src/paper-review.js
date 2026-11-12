const invalid=message=>Object.assign(new Error(message),{local:true});
export function paperReviewBody(context,notes,complete=false){
 const {execution,journal_entry:journal,post_trade_review:review}=context||{};
 if(!execution?.id||execution.execution_mode!=='paper'||!review?.id||review.execution_id!==execution.id||review.order_draft_id!==execution.order_draft_id||review.trade_journal_entry_id!==journal?.id||context.execution_available!==false||!review.updated_at||!Number.isFinite(Date.parse(review.updated_at)))throw invalid('复盘与模拟成交不匹配，请重新读取。');
 if(typeof notes!=='string'||!notes.trim()||notes.length>8000)throw invalid('请填写复盘笔记，最多8000字。');
 return {expected_updated_at:review.updated_at,review_json:{...review.review_json,terminal_manual_review:{notes:notes.trim(),source:'human'}},...(complete?{status:'completed'}:{})};
}
export function paperReviewResponse(saved,context,body){
 const original=context?.post_trade_review;
 if(!saved||saved.id!==original?.id||saved.execution_id!==original.execution_id||saved.order_draft_id!==original.order_draft_id||saved.trade_journal_entry_id!==original.trade_journal_entry_id||saved.user_id!==original.user_id||!saved.updated_at||!Number.isFinite(Date.parse(saved.updated_at)))throw invalid('服务端返回的复盘对象不匹配，请重新读取。');
 if(body&&(saved.review_json?.terminal_manual_review?.notes!==body.review_json?.terminal_manual_review?.notes||saved.review_json?.terminal_manual_review?.source!=='human'||body.status&&saved.status!==body.status))throw invalid('保存回执未包含预期笔记或完成状态，请重新读取核对。');
 return {...context,post_trade_review:saved};
}
