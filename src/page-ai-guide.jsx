import React,{useState} from 'react';
import {pageAIGuide} from '../terminal-ui/integration/ai-guide.mjs';
import {preparePageAIAction} from '../terminal-ui/integration/page-ai-actions.mjs';
import './page-ai-guide.css';
export function PageAIGuide({feature,context}){
 const [expanded,setExpanded]=useState(false),[error,setError]=useState('');
 const guide=pageAIGuide(feature,context);
 const prepare=()=>{try{const plan=preparePageAIAction(feature,guide.action.id,context);window.dispatchEvent(new CustomEvent('terminal:research',{detail:{question:plan.question,pageAction:plan}}));setError('');}catch{setError('页面上下文已变化，请重新选择研究对象。');}};
 return <section className="page-ai-guide" aria-label="本页AI工作流"><div className="page-ai-guide-main"><span className="page-ai-mark">AI</span><div><b>{guide.title} · 研究助手</b><small>{guide.status} · 自动匹配本页任务</small></div><button type="button" disabled={!guide.compatible} onClick={prepare}>{guide.canPrepare?'开始本页分析':'梳理资料缺口'}</button><button type="button" aria-expanded={expanded} onClick={()=>setExpanded(!expanded)}>流程{expanded?' −':' ＋'}</button></div>{expanded&&<div className="page-ai-guide-details"><ol>{guide.steps.map((step,index)=><li key={step}><span>{index+1}</span>{step}</li>)}</ol><p>{guide.sources.map(source=>source.label+' · '+(source.connected?'已接入，需读取核对':'尚未接入')).join('；')}</p><p>{guide.automation}。</p><small>{guide.limitations}</small></div>}{error&&<p role="alert">{error}</p>}</section>;
}
