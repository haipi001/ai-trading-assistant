const invalid=()=>Object.assign(new Error('复盘材料与当前成交、账户或上下文不匹配。'),{local:true});
export function paperReviewMaterial(packet,context,{contextVersion,market}={}){
 const ref=packet?.reference,material=packet?.provided_paper_review;
 if(packet?.execution_available!==false||!ref||ref.schema_version!==1||!Number.isSafeInteger(ref.context_version)||ref.context_version!==contextVersion||typeof ref.snapshot_id!=='string'||!ref.snapshot_id||ref.execution_id!==context?.execution?.id||ref.account_id!==context?.journal_entry?.account_id||ref.asset_id!==context?.journal_entry?.asset_id||!['stocks','cex'].includes(ref.market)||market&&ref.market!==market||material?.schema_version!==1||material.source!=='paper_ledger'||material.server_retrieved!==true||material.independently_verified!==false||material.execution_available!==false||material.usable_for_trading!==false||!Number.isFinite(Date.parse(material.captured_at))||!/^[a-f0-9]{64}$/.test(material.content_hash||'')||!material.reference||['schema_version','snapshot_id','context_version','execution_id','account_id','asset_id','market'].some(key=>material.reference[key]!==ref[key]))throw invalid();
 for(const key of ['execution_id','account_id','asset_id','market'])if(material[key]!==ref[key])throw invalid();
 if(!Array.isArray(material.entries)||material.entries.length!==5)throw invalid();
 const kinds=['paper_execution','original_order_rationale','saved_review_record','trade_journal_record','historical_decision_gates'];
 for(let index=0;index<5;index++)if(material.entries[index]?.id!=='PR'+(index+1)||material.entries[index].kind!==kinds[index])throw invalid();
 if(material.entries[0].record_id!==ref.execution_id||material.entries[0].execution_mode!=='paper'||material.entries[2].record_id!==context.post_trade_review?.id||material.entries[3].record_id!==context.journal_entry?.id||material.entries[4].current_authorization_verified!==false)throw invalid();
 for(const key of ['filled_quantity','average_fill_price','fill_notional','fee_amount','realized_pnl']){const value=material.entries[0][key];if(!(key==='average_fill_price'&&value===null)&&(typeof value!=='string'||!/^[-+]?\d+(\.\d+)?$/.test(value)))throw invalid();}
 return material;
}
