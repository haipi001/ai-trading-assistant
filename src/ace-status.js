// Navigation plans never grant account, approval, or execution authority.
export function aceReviewPlan(notice){
 const invalid=message=>Object.assign(new Error(message),{local:true});
 if(notice?.source_kind!=='order_draft'||!notice.source_id||!notice.account_id||!notice.instrument?.asset_id)throw invalid('订单来源不完整，请刷新待处理事项');
 if(notice.order_type!=='limit'||!Number.isFinite(notice.quantity)||notice.quantity<=0||!Number.isFinite(notice.limit_price)||notice.limit_price<=0)throw invalid('当前票据只支持有明确数量和限价的 Paper 草稿；其余记录保持只读');
 if(notice.mode!=='paper')throw invalid('当前仅支持跳转 Paper 审查；实盘入口尚未接通');
 const instrument=notice.instrument;
 const stock=['stock','etf'].includes(instrument.asset_type);
 const crypto=['crypto','stablecoin'].includes(instrument.asset_type);
 const venues=stock?{NASDAQ:'NASDAQ',NYSE:'NYSE'}:{BINANCE:'币安',OKX:'欧易OKX',BITGET:'Bitget'};
 const venue=venues[String(instrument.venue).toUpperCase()];
 if((!stock&&!crypto)||!venue||(stock&&(instrument.currency!=='USD'||instrument.market!=='US'))||(crypto&&(instrument.currency!=='USDT'||!['GLOBAL','CRYPTO'].includes(instrument.market))))throw invalid('该服务端资产平台尚未映射到图表，请保留原订单并使用对应工作区审查');
 const raw=String(instrument.symbol).toUpperCase();
 const symbol=stock?raw:raw.endsWith('/USDT')?raw.slice(0,-5):raw.endsWith('USDT')?raw.slice(0,-4):raw;
 if(!/^[A-Z0-9][A-Z0-9.^_-]{0,63}$/.test(symbol))throw invalid('服务端标的代码无法映射，请刷新来源');
 return {page:'market',tab:'图表',marketMode:stock?'stocks':'web3',symbol,venue,
         draftId:notice.source_id,assetId:instrument.asset_id,accountId:notice.account_id};
}
export function noticeUpdate(notice,status){
 if(!['OPEN','ACKNOWLEDGED','DISMISSED'].includes(status)||!notice?.source_revision||!Number.isInteger(notice.disposition_version))throw Error('invalid_notice_state');
 return {source_revision:notice.source_revision,expected_version:notice.disposition_version,status};
}

export function aceReviewUnavailable(notice){try{aceReviewPlan(notice);return null;}catch(error){return error.message;}}
