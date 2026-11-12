const uuid=value=>typeof value==='string'&&/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(value);
const decimal=value=>typeof value==='string'&&value.length<=100&&/^-?\d+(\.\d+)?$/.test(value);
export function portfolioContext(value){
 if(!value||value.schema_version!==1||value.server_retrieved!==true||value.independently_verified!==false||value.source!=='application_ledger'||value.valuation_freshness!=='unknown'||!['stocks','cex'].includes(value.market)||typeof value.account_id!=='string'||!value.account_id||!Number.isSafeInteger(value.context_version)||value.context_version<0||!Number.isFinite(Date.parse(value.captured_at))||!/^[0-9a-f]{64}$/.test(value.content_hash)||!/^[0-9a-f]{64}$/.test(value.ledger_revision))throw Error('账户账本材料无效');
 const ref=value.reference;
 if(!ref||ref.schema_version!==1||!uuid(ref.snapshot_id)||ref.snapshot_id!==value.source_snapshot_id||['account_id','market','context_version'].some(key=>ref[key]!==value[key]))throw Error('账户账本引用不一致');
 if(!value.account||value.account.account_id!==value.account_id||typeof value.account.mode!=='string'||typeof value.account.base_currency!=='string'||!Array.isArray(value.entries)||value.entries.length<1||value.entries.length>21||!Number.isSafeInteger(value.total_position_count)||value.total_position_count<0||value.included_count!==value.entries.length-1||value.total_position_count<value.included_count||value.truncated!==(value.total_position_count>value.included_count))throw Error('账户账本范围无效');
 const first=value.entries[0];if(first.id!=='H1'||first.kind!=='account_ledger'||first.source!=='application_ledger'||['account_id','mode','base_currency','account_type'].some(key=>first.account?.[key]!==value.account[key])||['total_position_count','included_count','truncated'].some(key=>first[key]!==value[key]))throw Error('账户账本总览不一致');
 const records=new Set();
 for(const [index,row] of value.entries.slice(1).entries()){
  if(row.id!=='H'+(index+2)||row.kind!=='position_ledger'||row.source!=='application_ledger'||typeof row.record_id!=='string'||records.has(row.record_id)||row.quote_as_of!==null||row.valuation_verified!==false||!Number.isFinite(Date.parse(row.record_updated_at))||!row.instrument||typeof row.instrument.asset_id!=='string'||typeof row.instrument.symbol!=='string'||typeof row.instrument.currency!=='string'||['quantity','recorded_average_cost','recorded_market_price','recorded_market_value'].some(key=>!decimal(row[key])))throw Error('账户账本条目无效');records.add(row.record_id);
 }
 return value;
}
export function portfolioAttachmentMatches(attachment,context,now=Date.now()){
 try{if(!context?.accountVerified||!['stocks','cex'].includes(context.market))return false;const value=portfolioContext(attachment?.preview),ref=attachment.reference;if(!ref||['schema_version','snapshot_id','account_id','market','context_version'].some(key=>ref[key]!==value.reference[key])||Object.keys(ref).length!==5)return false;const age=now-Date.parse(value.captured_at);return value.account_id===context.accountId&&value.market===context.market&&value.context_version===context.contextVersion&&age>=-30000&&age<=600000;}catch{return false;}
}
export function portfolioHistoryList(value,context){
 if(!value||value.execution_available!==false||typeof value.has_more!=='boolean'||!Array.isArray(value.items)||value.items.length>20)throw Error('账本研究历史无效');const ids=new Set();
 for(const row of value.items){if(!uuid(row.snapshot_id)||ids.has(row.snapshot_id)||row.account_id!==context.accountId||row.market!==context.market||(!Number.isSafeInteger(row.context_version)||row.context_version<0)||!Number.isFinite(Date.parse(row.created_at))||!['ok','failed',null].includes(row.reply_status??null))throw Error('账本历史归属无效');ids.add(row.snapshot_id);}
 return value;
}
