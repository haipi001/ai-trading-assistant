import {researchResult} from './research-ai.js';
import {validateMarketBars} from './market-chart-model.js';
import {safeNewsURL} from './news-feed-model.js';
const uuid=value=>typeof value==='string'&&/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(value);
const requestID=value=>typeof value==='string'&&value.startsWith('chat-')&&uuid(value.slice(5));
const fields=['symbol','venue','market_type','quote_currency','timeframe','kind'];
function scope(row){
 if(!row||typeof row.symbol!=='string'||!/^[-A-Za-z0-9.^_]{1,24}$/.test(row.symbol)||typeof row.venue!=='string'||!row.venue||row.venue.length>50||/[\x00-\x1f]/.test(row.venue)||!['stock','spot'].includes(row.market_type)||row.quote_currency!==(row.market_type==='stock'?'USD':'USDT')||!/^([1-9]\d{0,3})(s|m|h|d|wk|mo|y)$/.test(row.timeframe)||!['online','csv','replay'].includes(row.kind))throw Error('历史材料身份无效');
}
export function marketHistoryList(value){
 if(!value||value.execution_available!==false||typeof value.has_more!=='boolean'||!Array.isArray(value.items)||value.items.length>20)throw Error('历史列表格式无效');
 const seen=new Set();
 for(const row of value.items){scope(row);if(!uuid(row.snapshot_id)||seen.has(row.snapshot_id)||!Number.isFinite(Date.parse(row.created_at))||row.request_id!=null&&!requestID(row.request_id)||!['ok','failed',null].includes(row.reply_status??null))throw Error('历史列表条目无效');seen.add(row.snapshot_id);}
 return value;
}
export function marketHistoryArtifact(value,row){
 scope(row);
 if(!value||value.execution_available!==false||!uuid(row.snapshot_id)||value.snapshot_id!==row.snapshot_id||row.request_id!=null&&value.request_id!==row.request_id||fields.some(key=>value.provided_market?.[key]!==row[key]))throw Error('历史材料与所选记录不一致');
 if(value.workspace_labels!=null&&(!value.workspace_labels||value.workspace_labels.symbol!==row.symbol||typeof value.workspace_labels.page!=='string'||!/^[a-z_]{1,32}$/.test(value.workspace_labels.page)))throw Error('历史工作区标识无效');
 if(value.question!=null&&(typeof value.question!=='string'||!value.question.trim()||value.question.length>4000)||value.response_style!=null&&!['brief','detailed'].includes(value.response_style))throw Error('历史研究问题格式无效');
 const material=value.provided_market;
 if(material.source_verified!==false||material.data_semantics!=='raw_ohlcv'||!Array.isArray(material.bars)||material.bars.length<1||material.bars.length>240||typeof material.content_hash!=='string'||!/^[0-9a-f]{64}$/.test(material.content_hash)||!Number.isFinite(Date.parse(material.captured_at))||material.observed_at!==null&&!Number.isFinite(Date.parse(material.observed_at)))throw Error('历史行情来源无效');
 validateMarketBars(material.bars);
 if(!material.statistics||['first_open','last_close','sample_high','sample_low','sample_change_pct'].some(key=>typeof material.statistics[key]!=='number'||!Number.isFinite(material.statistics[key]))||(material.statistics.sample_volume!==null&&(typeof material.statistics.sample_volume!=='number'||!Number.isFinite(material.statistics.sample_volume))))throw Error('历史行情统计无效');
 if(value.provided_news){const news=value.provided_news,ids=new Set();if(!uuid(value.news_context_snapshot_id)||!Array.isArray(news.articles)||news.articles.length<1||news.articles.length>5)throw Error('历史资讯来源无效');for(const item of news.articles){if(!item||!/^N[1-5]$/.test(item.id)||ids.has(item.id)||typeof item.title!=='string'||!item.title.trim()||!safeNewsURL(item.url))throw Error('历史资讯引用无效');ids.add(item.id);}}
 else if(value.news_context_snapshot_id)throw Error('历史资讯材料缺失');
 const reply=value.validated_reply;
 if(value.reply_status==='ok'){
  if(!reply||reply.status!=='ok'||typeof reply.bullish_case!=='string'||typeof reply.bearish_case!=='string'||typeof reply.limitations!=='string'||!Array.isArray(reply.key_risks)||reply.key_risks.length>10||reply.key_risks.some(item=>typeof item!=='string')||reply.suggested_action!=null&&typeof reply.suggested_action!=='string'||reply.confidence!=null&&(typeof reply.confidence!=='number'||!Number.isFinite(reply.confidence)||reply.confidence<0||reply.confidence>1))throw Error('历史研究回复无效');
  researchResult({...reply,request_id:value.request_id,provider:value.provider,provider_mode:value.provider_mode,model:value.model,execution_available:false,external_call_attempted:true,context_scope:value.provided_news?'question_history_workspace_news_and_market_snapshots':'question_history_workspace_and_market_snapshot',provided_market:value.provided_market,market_context_snapshot_id:value.snapshot_id,provided_news:value.provided_news,news_context_snapshot_id:value.news_context_snapshot_id});
 }else if(!['failed',null].includes(value.reply_status??null)||reply!=null)throw Error('失败或未知状态不能附带有效回复');
 return value;
}
