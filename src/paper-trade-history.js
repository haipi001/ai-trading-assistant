export function paperTradeHistory(value,context){
 if(value?.source!=='owned_application_paper_ledger'||value.execution_available!==false||value.account_id!==context?.accountId||value.market!==context?.market||!Array.isArray(value.entries)||value.entries.length>100||typeof value.has_more!=='boolean'||!Number.isFinite(Date.parse(value.captured_at)))throw Error('invalid Paper trade history');
 if(value.next_cursor!==undefined&&((value.has_more&&(value.entries.length!==100||value.next_cursor!==value.entries.at(-1)?.execution_id))||(!value.has_more&&value.next_cursor!==null)))throw Error('invalid Paper cursor');
 const ids=new Set();
 for(const row of value.entries){
  if(typeof row?.execution_id!=='string'||!row.execution_id||ids.has(row.execution_id)||row.execution_mode!=='paper'||!['buy','sell'].includes(row.side)||!Number.isFinite(Date.parse(row.recorded_at))||['order_draft_id','asset_id','symbol','venue','asset_currency','status'].some(key=>typeof row[key]!=='string'||!row[key]||row[key].length>128))throw Error('invalid Paper trade row');
  for(const key of ['quantity','price','fee','realized_pnl'])if(!(key==='price'&&row[key]===null)&&(typeof row[key]!=='string'||!/^[-+]?\d+(\.\d+)?$/.test(row[key])))throw Error('invalid Paper decimal');
  ids.add(row.execution_id);
 }
 return value;
}
export function paperTradeCsv(packet){
 const cell=value=>{let text=String(value??'');if(/^\s*[=+@-]/.test(text))text="'"+text;return '"'+text.replaceAll('"','""')+'"';};
 const keys=['execution_id','recorded_at','symbol','venue','asset_currency','side','status','quantity','price','fee','realized_pnl','execution_mode'];
 return '\uFEFF'+[keys,...packet.entries.map(row=>keys.map(key=>row[key]))].map(row=>row.map(cell).join(',')).join('\r\n');
}
export function paperHistoryReview(value,row,context){
 const fill=value?.execution,journal=value?.journal_entry,review=value?.post_trade_review;
 if(value?.execution_available!==false||fill?.id!==row.execution_id||fill.execution_mode!=='paper'||fill.order_draft_id!==row.order_draft_id||journal?.account_id!==context?.accountId||journal.asset_id!==row.asset_id||review?.execution_id!==fill.id||review.order_draft_id!==fill.order_draft_id||review.trade_journal_entry_id!==journal.id||typeof journal.title!=='string'||typeof journal.notes!=='string'||typeof review.status!=='string'||typeof review.id!=='string'||!review.updated_at||!Number.isFinite(Date.parse(review.updated_at)))throw Error('Paper history review identity mismatch');
 return value;
}

export function appendPaperHistory(previous,page,context){
 paperTradeHistory(page,context);
 if(!previous)return page;
 if(previous.account_id!==page.account_id||previous.market!==page.market||!previous.has_more||previous.next_cursor!==previous.entries.at(-1)?.execution_id)throw Error('Paper pagination scope mismatch');
 const ids=new Set(previous.entries.map(row=>row.execution_id));
 if(page.entries.some(row=>ids.has(row.execution_id)))throw Error('Paper pagination repeated records');
 return {...page,entries:[...previous.entries,...page.entries]};
}
