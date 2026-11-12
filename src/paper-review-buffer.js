export function paperReviewBufferKey(userId,scope,context){
 const review=context?.post_trade_review,fill=context?.execution;
 if(!userId||!scope||!review?.id||!review.updated_at||!fill?.id||review.execution_id!==fill.id)return null;
 return 'terminal-paper-review-buffer-v2:'+JSON.stringify([userId,scope,fill.id,review.id,review.updated_at]);
}
export function readPaperReviewBuffer(storage,key,fallback=''){
 if(!key)return fallback;
 const value=JSON.parse(storage.getItem(key)||'null');
 return value?.version===1&&typeof value.notes==='string'&&value.notes.length<=8000?value.notes:fallback;
}
export function savePaperReviewBuffer(storage,key,notes){
 if(typeof notes!=='string'||notes.length>8000)throw Error('invalid review buffer');
 if(key)storage.setItem(key,JSON.stringify({version:1,status:'unsubmitted',notes}));
}

// Remove only this editor's legacy key; never persist session credentials again.
export function migratePaperReviewBuffer(storage,identity,scope,context,key){
 if(!identity||!key)return;
 const old='terminal-paper-review-buffer-v1:'+JSON.stringify([identity,scope,context.execution.id,context.post_trade_review.id,context.post_trade_review.updated_at]);
 const raw=storage.getItem(old);
 if(raw===null)return;
 try{
  const value=JSON.parse(raw);
  if(storage.getItem(key)===null&&value?.version===1&&typeof value.notes==='string'&&value.notes.length<=8000)savePaperReviewBuffer(storage,key,value.notes);
 }finally{storage.removeItem(old);}
}
