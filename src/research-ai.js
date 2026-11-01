import {apiRequest} from './backend-api.js';
import {validateMarketBars} from './market-chart-model.js';
import {safeNewsURL} from './news-feed-model.js';
export const AI_MESSAGES={ai_market_invalid:'行情快照无效，请重新选择或等待有效数据。',ai_market_identity_mismatch:'行情资料与当前标的不一致，请重新选择。',ai_market_demo_rejected:'演示数据不能作为此行情资料发送。',ai_market_future_rejected:'复盘资料超出游标范围，请重新选择。',ai_news_missing:'尚无可用资讯缓存，请先在快讯页获取消息，或取消附带资讯。',ai_configuration_required:'请在系统设置的 AI 服务中保存 Key 与模型。',ai_approval_required:'请在 AI 服务设置中允许研究调用。',ai_budget_required:'请设置有效的月预算与单次预算。',ai_entitlement_required:'当前服务尚未获得有效调用权限。',ai_preflight_blocked:'调用前检查未通过，可能触发调用频率限制，请检查设置或稍后重试。',ai_provider_request_failed:'模型调用或响应验证失败，请检查 Key、模型权限、账户额度与后端网络。本次请求可能已产生费用。',ai_question_invalid:'问题或工作区参数无效，请修改后重试。',ai_permission_required:'当前后端用户没有 AI 研究权限。'};
export function researchStatus(value){if(!value||typeof value.can_request!=='boolean'||value.external_call_attempted!==false||value.execution_available!==false||(value.can_request&&(!['openai','deepseek'].includes(value.provider)||typeof value.model!=='string'||!value.model)))throw Error('invalid AI status');return value;}
export function researchResult(value){
 if(!value||!['ok','blocked','failed'].includes(value.status)||value.execution_available!==false)throw Error('invalid AI response');
 if(value.status==='ok'){
  if(value.external_call_attempted!==true||!['bring_your_own','platform_managed'].includes(value.provider_mode)||!['openai','deepseek'].includes(value.provider)||typeof value.model!=='string'||!value.model||typeof value.summary!=='string'||!value.summary.trim()||typeof value.request_id!=='string'||!/^chat-[0-9a-f-]{36}$/.test(value.request_id)||!['question_history_and_workspace_labels_only','question_history_workspace_and_news_snapshot','question_history_workspace_and_market_snapshot','question_history_workspace_news_and_market_snapshots'].includes(value.context_scope))throw Error('invalid AI provenance');
  const news=value.provided_news;
  if(['question_history_workspace_and_news_snapshot','question_history_workspace_news_and_market_snapshots'].includes(value.context_scope)){
   if(!news||!['chinese_aggregate','panews','cointelegraph','nasdaq','newsapi'].includes(news.provider)||!Array.isArray(news.articles)||news.articles.length<1||news.articles.length>5||typeof news.fetched_at!=='string'||!Number.isFinite(Date.parse(news.fetched_at))||typeof news.stale!=='boolean'||typeof news.content_hash!=='string'||!/^[0-9a-f]{64}$/.test(news.content_hash)||typeof value.news_context_snapshot_id!=='string'||!/^[0-9a-f-]{36}$/.test(value.news_context_snapshot_id))throw Error('invalid news context');
   const ids=new Set();
   for(const item of news.articles){if(!item||typeof item.id!=='string'||!/^N[1-5]$/.test(item.id)||ids.has(item.id)||typeof item.title!=='string'||!item.title.trim()||!safeNewsURL(item.url))throw Error('invalid news source');ids.add(item.id);}
   if(!Array.isArray(value.cited_news_ids)||value.cited_news_ids.some(id=>!ids.has(id)))throw Error('invalid news citations');
  }else if(news||(value.cited_news_ids?.length))throw Error('unexpected news context');
  const market=value.provided_market;
  if(['question_history_workspace_and_market_snapshot','question_history_workspace_news_and_market_snapshots'].includes(value.context_scope)){
   if(!market||market.source_verified!==false||market.data_semantics!=='raw_ohlcv'||!['online','csv','replay'].includes(market.kind)||typeof market.symbol!=='string'||typeof market.venue!=='string'||typeof market.timeframe!=='string'||!['USDT','USD'].includes(market.quote_currency)||typeof market.content_hash!=='string'||!/^[0-9a-f]{64}$/.test(market.content_hash)||typeof value.market_context_snapshot_id!=='string'||!/^[0-9a-f-]{36}$/.test(value.market_context_snapshot_id)||!Array.isArray(market.bars)||market.bars.length<1||market.bars.length>240)throw Error('invalid market context');
   validateMarketBars(market.bars);
   if(!market.statistics||['first_open','last_close','sample_high','sample_low','sample_change_pct'].some(key=>typeof market.statistics[key]!=='number'||!Number.isFinite(market.statistics[key]))||(market.statistics.sample_volume!==null&&!Number.isFinite(market.statistics.sample_volume))||!Array.isArray(value.cited_market_ids)||value.cited_market_ids.some(id=>id!=='M1'))throw Error('invalid market statistics');
  }else if(market||value.cited_market_ids?.length)throw Error('unexpected market context');

 }
 return value;
}
export async function requestResearchChat(question,{page='home',symbol='',history=[],responseStyle='brief',includeNews=false,marketCapture=null,signal}={}){
 const result=researchResult(await apiRequest('/production/human-control/llm/chat',{method:'POST',body:{question,page,symbol,history,response_style:responseStyle,include_news:includeNews,market_context:marketCapture},signal,timeout:90000}));
 if(result.status==='ok'&&marketCapture){const value=result.provided_market;if(!value||['symbol','venue','quote_currency','timeframe','kind'].some(key=>value[key]!==marketCapture[key])||value.bars.length!==marketCapture.bars.length||value.bars.some((row,index)=>['time','open','high','low','close','volume'].some(key=>row[key]!==marketCapture.bars[index][key])))throw Error('market response identity mismatch');}
 return result;
}

export function researchText(value){return [value.summary,Array.isArray(value.key_risks)&&value.key_risks.length?`风险：\n${value.key_risks.join('\n')}`:'',value.limitations?`限制：${value.limitations}`:''].filter(Boolean).join('\n\n');}

export function researchHistory(messages){return messages.slice(-6).map(message=>{const context=message.result?.provided_news;const market=message.result?.provided_market;const marketPrior=market?`[Historical market snapshot ${message.result.market_context_snapshot_id}; M1 belonged to ${market.symbol}/${market.quote_currency} ${market.venue} ${market.timeframe} ${market.kind}, not the current market_context.]\n`:'';const prior=context?`[Historical news snapshot ${message.result.news_context_snapshot_id}; its IDs belong to that earlier reply, not the current news context. Sources: ${context.articles.map(item=>`${item.id}=${item.url.slice(0,200)}`).join('; ')}]\n`:'';return {role:message.role==='ai'?'assistant':'user',content:(marketPrior+prior+message.text).slice(0,2000)};});}
