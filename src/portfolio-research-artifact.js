import {portfolioContext} from './research-portfolio.js';
import {researchResult} from './research-ai.js';
import {safeNewsURL} from './news-feed-model.js';
export function portfolioHistoryArtifact(value,row,context){
 const material=portfolioContext(value?.provided_portfolio);
 if(value.execution_available!==false||value.snapshot_id!==row.snapshot_id||row.request_id!=null&&value.request_id!==row.request_id||material.account_id!==context.accountId||material.market!==context.market||material.context_version!==row.context_version)throw Error('历史账户材料不匹配');
 const reply=value.validated_reply;
 if(value.provided_news){if(!Array.isArray(value.provided_news.articles)||!value.provided_news.articles.length||value.provided_news.articles.some(item=>!safeNewsURL(item.url)))throw Error('历史资讯来源无效');}else if(value.news_context_snapshot_id)throw Error('历史资讯材料缺失');
 if(value.reply_status==='ok'){
  if(!reply||reply.status!=='ok'||typeof reply.bullish_case!=='string'||typeof reply.bearish_case!=='string'||typeof reply.limitations!=='string'||!Array.isArray(reply.key_risks)||reply.key_risks.some(item=>typeof item!=='string')||reply.confidence!=null&&(typeof reply.confidence!=='number'||!Number.isFinite(reply.confidence)||reply.confidence<0||reply.confidence>1))throw Error('历史账户回复无效');
  researchResult({...reply,request_id:value.request_id,provider:value.provider,provider_mode:value.provider_mode,model:value.model,execution_available:false,external_call_attempted:true,context_scope:value.provided_news?'question_history_workspace_news_and_portfolio_snapshots':'question_history_workspace_and_portfolio_snapshot',provided_portfolio:material,portfolio_context_snapshot_id:value.snapshot_id,provided_news:value.provided_news,news_context_snapshot_id:value.news_context_snapshot_id});
 }else if(!['failed',null].includes(value.reply_status??null)||reply!=null)throw Error('失败研究不得附带有效回复');
 return value;
}
