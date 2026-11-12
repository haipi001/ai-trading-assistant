import {safeNewsURL} from './news-feed-model.js';
import {strategyContext} from './research-strategy.js';
import {researchResult} from './research-ai.js';
export function strategyHistoryList(value,accountId,market){
 if(value?.execution_available!==false||!Array.isArray(value.items)||value.items.length>20||typeof value.has_more!=='boolean')throw Error('invalid strategy history');
 const ids=new Set();for(const row of value.items){if(!row||typeof row.snapshot_id!=='string'||!/^[-a-f0-9]{36}$/.test(row.snapshot_id)||ids.has(row.snapshot_id)||row.account_id!==accountId||row.market!==market||!['ok','failed',null].includes(row.reply_status??null)||!Number.isSafeInteger(row.context_version)||typeof row.account_id!=='string'||!['stocks','cex'].includes(row.market)||!Number.isFinite(Date.parse(row.created_at)))throw Error('invalid strategy history row');ids.add(row.snapshot_id);}
 return value;
}
export function strategyHistoryArtifact(value,row){
 const material=strategyContext(value?.provided_strategy);
 if(value.execution_available!==false||value.snapshot_id!==row.snapshot_id||row.request_id!=null&&row.request_id!==value.request_id||material.account_id!==row.account_id||material.market!==row.market||material.context_version!==row.context_version)throw Error('strategy history scope mismatch');
 if(value.provided_news){const news=value.provided_news;if(!Array.isArray(news.articles)||!news.articles.length||news.articles.length>5||news.articles.some(item=>typeof item?.title!=='string'||!safeNewsURL(item?.url))||!value.news_context_snapshot_id)throw Error('invalid saved news source');}else if(value.news_context_snapshot_id)throw Error('saved news material missing');
 if(value.reply_status==='ok'){
  const reply=value.validated_reply;
  if(!reply||reply.status!=='ok'||typeof reply.bullish_case!=='string'||typeof reply.bearish_case!=='string'||typeof reply.limitations!=='string'||!Array.isArray(reply.key_risks)||reply.key_risks.some(item=>typeof item!=='string'))throw Error('invalid saved strategy reply');
  researchResult({...reply,request_id:value.request_id,provider:value.provider,provider_mode:value.provider_mode,model:value.model,external_call_attempted:true,execution_available:false,context_scope:value.provided_news?'question_history_workspace_news_and_strategy_snapshots':'question_history_workspace_and_strategy_snapshot',provided_strategy:material,strategy_context_snapshot_id:value.snapshot_id,provided_news:value.provided_news,news_context_snapshot_id:value.news_context_snapshot_id});
 }else if(!['failed',null].includes(value.reply_status??null)||value.validated_reply!=null)throw Error('failed strategy research cannot contain a validated reply');
 return value;
}
