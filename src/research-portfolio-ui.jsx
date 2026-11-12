import React,{useEffect,useRef,useState} from 'react';
import {apiRequest} from './backend-api.js';
import {portfolioContext,portfolioAttachmentMatches} from './research-portfolio.js';
export function ResearchPortfolioControl({context,attachment,enabled,onChange,onAttachment,disabled,identity}){
 const key=JSON.stringify([identity,context?.identityUserId,context?.accountId,context?.market,context?.contextVersion]),latest=useRef(key);latest.current=key;
 const job=useRef(null),[state,setState]=useState({});const current=state.key===key?state:{};
 useEffect(()=>()=>job.current?.abort(),[key]);
 if(!context||!['stocks','cex'].includes(context.market))return null;
 const valid=portfolioAttachmentMatches(attachment,context);
 async function prepare(){
  job.current?.abort();const controller=new AbortController();job.current=controller;onAttachment(null);setState({key,busy:true});
  try{
   const response=await apiRequest('/production/human-control/llm/chat/portfolio-context/prepare',{method:'POST',body:{account_id:context.accountId,market:context.market,context_version:context.contextVersion},signal:controller.signal});
   if(controller.signal.aborted||job.current!==controller||latest.current!==key)return;
   if(response.execution_available!==false)throw Error();const material=portfolioContext(response.provided_portfolio);
   const next={reference:response.reference,preview:material};if(!portfolioAttachmentMatches(next,context))throw Error();
   onAttachment(next);setState({key,busy:false});
  }catch{if(!controller.signal.aborted&&job.current===controller&&latest.current===key)setState({key,busy:false,error:'读取账本材料失败；请检查所选账户、市场、后端会话与记录状态。'});}
 }
 return <section className="research-portfolio-context"><h4>所选账户账本持仓</h4><p>这条路径读取应用账本，不会刷新交易所或券商余额。发送会把所选账户标识、记录数量、成本和记录估值交给配置的模型；记录时间不是报价时间。</p><button type="button" disabled={disabled||current.busy||!context.accountVerified||!context.accountId} onClick={prepare}>读取所选账户账本材料</button>{!context.accountVerified&&<p>请先在顶部刷新并选择已校验的兼容账户。</p>}{current.busy&&<p role="status">正在读取账户账本…</p>}{current.error&&<p role="alert">{current.error}</p>}<label><input type="checkbox" checked={enabled} onChange={event=>onChange(event.target.checked)} disabled={disabled||!valid}/>附带所选账户账本材料</label>{attachment&&<><p>{valid?'当前材料':'材料失效，请重新读取'} · 账户 {attachment.reference.account_id.slice(0,8)} · 原上下文 {attachment.reference.context_version}<br/>{attachment.preview.included_count}/{attachment.preview.total_position_count} 条记录{attachment.preview.truncated?' · 仅前20条，不能代表完整组合':''}</p><ResearchPortfolioSources result={{provided_portfolio:attachment.preview,cited_portfolio_ids:[]}}/></>}</section>;
}
export function ResearchPortfolioSources({result,historical=false}){
 const material=result?.provided_portfolio;if(!material)return null;
 return <section className="research-portfolio-sources"><h4>{historical?'原请求':'本次'}账户账本材料</h4><p>账户 {material.account_id.slice(0,8)} · {material.account.mode} · {material.market} · 上下文 {material.context_version}<br/>读取 {new Date(material.captured_at).toLocaleString()} · 估值时效未知</p><p>账本记录值未经独立核实，零值/缺项不代表真实零暴露；不提供跨账户总资产、汇率换算或实时盈亏。</p><ul>{material.entries.map(row=><li key={row.id}><b>[{row.id}] {result.cited_portfolio_ids?.includes(row.id)?'所列引用 · ':''}{row.kind==='account_ledger'?'账户账本范围':row.instrument.symbol}</b>{row.kind==='account_ledger'?<p>记录 {row.included_count}/{row.total_position_count}{row.truncated?' · 不完整摘录':''}</p>:<p>{row.instrument.venue} · {row.instrument.currency} · 标的 {row.instrument.asset_id.slice(0,8)}{row.instrument.chain_id?' · 链 '+row.instrument.chain_id:''}{row.instrument.contract_address?' · 合约 '+row.instrument.contract_address:''}<br/>数量 {row.quantity} · 记录成本 {row.recorded_average_cost}<br/>实时估值未知；账本原价格 {row.recorded_market_price} · 原估值 {row.recorded_market_value}（未核实）<br/>记录更新 {new Date(row.record_updated_at).toLocaleString()}；报价时间未知</p>}</li>)}</ul><small>来源 {material.source_snapshot_id} · 研究包 {result.portfolio_context_snapshot_id||'尚未发送'}。仅解释原材料，不应用再平衡或订单。</small></section>;
}
