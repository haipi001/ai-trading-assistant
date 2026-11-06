import {onchainHistoryList,onchainHistoryArtifact} from './onchain-research-history.js';
import React,{useEffect,useRef,useState} from 'react';
import {apiRequest} from './backend-api.js';
import {onchainScope} from './terminal-onchain.js';
import {ResearchOnchainSources} from './research-onchain-ui.jsx';
export function OnchainResearchHistory({context}){
 const key=onchainScope(context),job=useRef(null),[state,setState]=useState({});
 const current=state.key===key?state:{};
 useEffect(()=>()=>job.current?.abort(),[key]);
 async function load(id){
  job.current?.abort();const controller=new AbortController();job.current=controller;
  setState(old=>({... (old.key===key?old:{}),key,busy:true,error:''}));
  try{
   const base='/production/human-control/llm/chat/';
   const value=await apiRequest(id?base+'onchain-context/'+encodeURIComponent(id):base+'onchain-contexts?'+new URLSearchParams({wallet_id:context.walletId,chain_id:context.chainId,contract_address:context.contractAddress||''}),{signal:controller.signal});
   if(controller.signal.aborted||job.current!==controller)return;
   if(value.execution_available!==false)throw Error('历史材料权限字段无效');
   if(id){onchainHistoryArtifact(value,context,id);setState(old=>({...old,key,busy:false,artifact:value}));}
   else{onchainHistoryList(value);setState({key,busy:false,items:value.items,hasMore:value.has_more});}
  }catch(error){if(!controller.signal.aborted&&job.current===controller)setState(old=>({...old,key,busy:false,error:'读取研究历史失败，请检查后端会话与连接。'}));}
 }
 const a=current.artifact,reply=a?.validated_reply;
 return <section aria-label="已保存链上研究"><h3>已保存链上研究</h3><button disabled={!context.walletId||current.busy} onClick={()=>load()}>读取最近研究记录</button>{current.busy&&<p role="status">正在读取服务端研究记录…</p>}{current.error&&<p role="alert">{current.error}</p>}{current.items&&<><p>{current.items.length}条{current.hasMore?' · 仅最近20条':''}，均为原请求上下文，不自动作为新研究附件。</p>{current.items.map(row=><button key={row.snapshot_id} disabled={current.busy} onClick={()=>load(row.snapshot_id)}>{row.reply_status||'未完成'} · 原上下文 {row.context_version} · {row.snapshot_id.slice(0,8)}</button>)}</>}{a&&<article><h4>历史研究 · 原上下文 {a.provided_onchain.context_version}</h4><p>{reply?.summary||'该请求未保存有效回复。'}</p>{reply&&<><h4>有利情景</h4><p>{reply.bullish_case}</p><h4>不利情景</h4><p>{reply.bearish_case}</p><h4>风险与未知项</h4><ul>{reply.key_risks.map((risk,index)=><li key={index}>{risk}</li>)}</ul>{reply.suggested_action&&<><h4>研究建议 · 不执行操作</h4><p>{reply.suggested_action}</p></>}{typeof reply.confidence==='number'&&<p>模型自报置信度 {reply.confidence}，不代表数据质量或事实核验。</p>}</>}<p>{reply?.limitations}</p><ResearchOnchainSources result={{provided_onchain:a.provided_onchain,onchain_context_snapshot_id:a.snapshot_id,cited_onchain_ids:reply?.cited_onchain_ids||[]}}/></article>}</section>;
}
