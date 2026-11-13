import {pageAIPolicy,PAGE_AI_SOURCES} from './page-ai-actions.mjs';

// Planning is deterministic and local; it does not call a provider or grant permissions.
export function pageAIGuide(feature,context){
 const policy=pageAIPolicy(feature),compatible=policy.supportedMarkets.includes(context?.market);
 const primary=policy.actions[0],missing=primary.requiredSources.filter(key=>PAGE_AI_SOURCES[key].adapter!=='implemented');
 const canPrepare=compatible&&primary.availability==='review_required';
 return {title:feature.label||feature.tab||feature.code,family:policy.family,compatible,canPrepare,
  action:canPrepare?primary:policy.actions.find(item=>item.id.endsWith('.gaps')),
  sources:primary.requiredSources.map(key=>({key,label:PAGE_AI_SOURCES[key].label,connected:PAGE_AI_SOURCES[key].adapter==='implemented'})),
  status:!compatible?'请切换适用市场':missing.length?'需要补充资料接入':feature.page==='terminal'?'请进入业务资料页':'准备材料后可分析',
  destination:primary.destination,limitations:primary.limitations,
  steps:['确认研究对象','读取并核对材料','发送模型分析','审阅证据与下一步'],
  automation:'自动匹配任务与资料要求；读取材料后校验，手动发送模型分析',autoSubmit:false,executionAvailable:false};
}
export function researchProgress({busy=false,error='',canRequest=false,issue='',hasResult=false}={}){
 if(busy)return {step:2,label:'模型分析中',detail:'正在等待回复；关闭面板不会撤销已发出的请求。'};
 if(error)return {step:1,label:'需要处理',detail:error};
 if(issue)return {step:1,label:'补齐研究材料',detail:issue};
 if(!canRequest)return {step:0,label:'连接 AI 服务',detail:'先配置服务并检查可用状态。'};
 if(hasResult)return {step:3,label:'审阅分析结果',detail:'核对引用和限制，再追问或导出研究记录。'};
 return {step:1,label:'等待确认发送',detail:'核对问题及选中材料后发送，将调用已配置模型。'};
}
export function followupQuestions(action){
 const subject=action?.label||'当前研究';
 return [`针对${subject}，把已提供证据、推断和未知项分开列出。`,`针对${subject}，列出结论失效条件和下一次需要核验的数据。`,`针对${subject}，整理一份供我审阅的后续研究清单，不执行交易或修改策略。`];
}
export function researchMarkdown(message){
 if(message?.role!=='ai'||!message.result||typeof message.text!=='string')throw Error('validated_result_required');
 const r=message.result;
 return ['# AI 研究记录',`研究上下文：${message.context||'未提供'}`,`请求：${r.request_id||message.id||'未提供'}`,message.text,
 '## 材料快照',...['market','news','onchain','portfolio','paper_review','strategy','backtest'].map(key=>`${key}: ${r[key+'_context_snapshot_id']||'未附带'}`),
 ...(r.provided_backtest?['## 回测来源 [BT1]',`回测：${r.provided_backtest.backtest_run_id}`,`冻结时间：${r.provided_backtest.captured_at}`,`内容哈希：${r.provided_backtest.content_hash}`,`数据范围：${r.provided_backtest.date_from} 至 ${r.provided_backtest.date_to}`,'历史模拟，不代表当前脚本执行、独立核验收益或交易授权。']:[]),
 '仅为研究回复；请核对材料来源、时点与限制。'].join('\n\n');
}
