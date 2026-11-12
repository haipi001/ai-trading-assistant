import {terminalAssetMatches} from './terminal-trading-policy.js';
import {paperReviewMaterial} from './paper-review-material.js';
export function researchPaperReviewContext(material){
 const ref=material?.reference,entries=material?.entries;
 return paperReviewMaterial({reference:ref,provided_paper_review:material,execution_available:false},{execution:{id:material?.execution_id},journal_entry:{id:entries?.[3]?.record_id,account_id:material?.account_id,asset_id:material?.asset_id},post_trade_review:{id:entries?.[2]?.record_id}},{contextVersion:ref?.context_version,market:ref?.market});
}
export function paperReviewAttachmentMatches(attachment,context,symbol,now=Date.now()){
 try{
  const material=researchPaperReviewContext(attachment?.material),ref=material.reference;
  if(!attachment?.reference||Object.keys(ref).some(key=>ref[key]!==attachment.reference[key]))return false;
  const age=now-Date.parse(material.captured_at);if(age < -30000||age>600000)return false;
  const [expectedSymbol,expectedQuote]=String(context?.instrumentId||symbol||'').toUpperCase().split('/'),[actualSymbol,actualQuote]=String(material.instrument?.symbol||'').toUpperCase().split('/');
  if(!expectedSymbol||expectedSymbol!==actualSymbol||expectedQuote&&expectedQuote!==(actualQuote||String(material.instrument?.currency||'').toUpperCase()))return false;
  return !context||context.market===ref.market&&context.accountId===ref.account_id&&context.contextVersion===ref.context_version&&terminalAssetMatches(material.instrument,context);
 }catch{return false;}
}

export function paperReviewReadiness(attachment,enabled,context,symbol,{includeMarket=false,includeOnchain=false,includePortfolio=false,pageAction=null}={}){
 if(!attachment&&!enabled)return '';
 if(!enabled)return '请核对并勾选此成交的Paper复盘材料；或取消此复盘准备后手动提问。';
 if(!paperReviewAttachmentMatches(attachment,context,symbol))return '请回原成交重新读取有效Paper复盘材料。';
 if(includeMarket||includeOnchain||includePortfolio||pageAction)return 'Paper复盘暂不能与其他专属附件或本页动作同时发送。';
 return '';
}
