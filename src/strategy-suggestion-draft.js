import {strategyContext} from './research-strategy.js';
import {strategyParameterChanges,applyStrategyChanges} from './strategy-parameter-changes.js';
export function strategySuggestionDraft(result,edits,context,now=Date.now()){
 const material=strategyContext(result?.provided_strategy),changes=strategyParameterChanges(result.strategy_parameter_changes||[],material);
 if(!changes.length||!context?.identityUserId||!context.accountVerified||context.accountId!==material.account_id||context.market!==material.market||context.contextVersion!==material.context_version||now-Date.parse(material.captured_at)<-30000||now-Date.parse(material.captured_at)>600000)throw Error('请回到原账户和参数上下文，或重新准备策略研究。');
 if(!/^[-a-f0-9]{36}$/.test(result.strategy_context_snapshot_id||'')||!/^chat-[-a-f0-9]{36}$/.test(result.request_id||''))throw Error('缺少策略研究来源记录');
 if(!edits||Object.keys(edits).length!==changes.length||Object.keys(edits).some(key=>!changes.some(c=>c.field===key)))throw Error('参数编辑范围无效');
 const reviewed=changes.map(change=>({...change,after:edits[change.field]}));strategyParameterChanges(reviewed,material);
 return {...applyStrategyChanges(material.parameters,reviewed),name:(material.parameters.name+' · 审阅草稿').slice(0,200),status:'草稿',source_snapshot_id:result.strategy_context_snapshot_id,source_request_id:result.request_id,source_content_hash:material.content_hash};
}
