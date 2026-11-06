import {OnchainResearchHistory} from './onchain-research-history.jsx';
import React,{useEffect,useRef,useState} from 'react';
import {apiRequest} from './backend-api.js';
import {onchainScope,onchainSelection,onchainPath,onchainPacket,onchainStale,onchainResearchQuestion,onchainResearchAttachment} from './terminal-onchain.js';
import './terminal-onchain.css';
const time=value=>new Date(value).toLocaleString();
function ReadStatus({source,asOf,now}){return <small>{source} · {time(asOf)} · {onchainStale(asOf,now)?'已陈旧':'10分钟内记录'}</small>;}
export function TerminalOnchainWorkspace({context}){
 const key=onchainScope(context),job=useRef(null),[state,setState]=useState({}),[now,setNow]=useState(Date.now),[notice,setNotice]=useState('');
 const data=state.key===key?state.data:null,busy=state.key===key&&state.busy,error=state.key===key?state.error:'';
 async function read(refresh=false){
  if(!context.walletId)return;
  job.current?.abort();const controller=new AbortController();job.current=controller;
  setState(old=>({key,data:old.key===key?old.data:null,busy:true,error:''}));setNotice('');
  try{const selection=onchainSelection(context),base='/api/v2/workspaces/onchain/'+encodeURIComponent(context.walletId);
   const result=await apiRequest(refresh?base+'/refresh':onchainPath(context),{...(refresh?{method:'POST',body:selection}:{}),signal:controller.signal,timeout:30000});
   if(controller.signal.aborted||job.current!==controller)return;
   const packet=onchainPacket(result,context);
   setState({key,data:packet,busy:false,error:packet.last_read_error?'最近一次RPC读取失败（'+time(packet.last_read_error.as_of)+'）；以下仍为已存材料，请重试公共RPC读取。':''});setNow(Date.now());
  }catch(err){if(controller.signal.aborted||job.current!==controller)return;const message=err.code==='onchain_rpc_unavailable'?'公共RPC读取失败或网络不匹配；上次材料保留，未写入部分结果。':err.status===404?'钱包不存在、已停用或不属于当前用户。':err.status===422?'链、合约或钱包不兼容，请核对全局选择。':err.status===401?'会话已过期，请重新登录。':err.name==='AbortError'?'读取超时；后端只读请求可能仍在完成。':err.status?'无法读取链上资料（HTTP'+err.status+'）。':err.message||'链上服务不可用。';setState(old=>({key,data:old.key===key?old.data:null,busy:false,error:message}));}
 }
 useEffect(()=>{setState({key,data:null,busy:false,error:''});setNotice('');read();return()=>{job.current?.abort();};},[key]);
 useEffect(()=>{const timer=setInterval(()=>setNow(Date.now()),30000);return()=>clearInterval(timer);},[]);
 function research(kind){try{const onchainAttachment=onchainResearchAttachment(data,context);window.dispatchEvent(new CustomEvent('terminal:research',{detail:{question:kind+'，请区分事实、推断与缺失项，并引用本次材料。',includeMarket:false,onchainAttachment}}));setNotice('已准备链上材料引用，请在AI面板审阅附件后发送；尚未调用模型。');}catch(err){setNotice(err.message);}}
 return <section className="onchain-workspace" aria-label="链上只读研究">
  <header><div><small>Web3 / 只读数据</small><h2>钱包、授权与协议</h2></div><span>无签名权限 · Live关闭</span></header>
  <dl className="onchain-identity"><div><dt>链</dt><dd>{context.chainId}</dd></div><div><dt>钱包</dt><dd>{data?.wallet.label||context.walletId||'请在顶部选择钱包'}</dd></div><div><dt>合约</dt><dd>{context.contractAddress||'原生币 / 钱包记录'}</dd></div></dl>
  {data&&<p className="onchain-address">公开地址：{data.wallet.address}</p>}
  <div className="onchain-actions"><button disabled={!context.walletId||busy} onClick={()=>read()}>读取已存材料</button><button disabled={!context.walletId||busy} onClick={()=>read(true)}>从公共RPC读取余额</button>{busy&&<button onClick={()=>{job.current?.abort();setState(old=>({...old,busy:false}));setNotice('已停止等待；后端只读请求可能仍在完成。');}}>停止等待</button>}</div>
  {!context.walletId&&<p role="status">选择当前链已登记的钱包后读取。此处不会连接钱包扩展或请求签名。</p>}
  {busy&&<p role="status">{data?'正在更新，以下仍为上次材料。':'正在读取当前钱包材料…'}</p>}{error&&<p role="alert">{error}</p>}
  {data&&<><h3>余额观察</h3>{data.snapshot?<><p>快照 {data.snapshot.id} · 区块 {data.snapshot.block_number} · {error?'更新失败 / 上次材料':data.snapshot.stale||onchainStale(data.snapshot.as_of,now)?'已陈旧':'近期观察'} · 未证明最终确认</p><ReadStatus source={data.snapshot.source} asOf={data.snapshot.as_of} now={now}/><div className="onchain-table"><table><thead><tr><th>资产身份</th><th>精确数量</th><th>USD估值</th></tr></thead><tbody>{data.snapshot.balances.map(row=><tr key={row.contract_address||'native'}><td>{row.contract_address||row.symbol+' · 原生币'}</td><td className="onchain-amount">{row.amount}</td><td>未接入</td></tr>)}</tbody></table></div></>:<p>当前钱包、链与合约尚无RPC快照。点击公共RPC读取；不会用演示余额补齐。</p>}
  <h3>授权记录</h3><p>仅已存记录，尚未进行完整授权索引。{data.coverage.allowances_truncated?'记录超过200条，当前结果已截断。':''}</p>{!data.recorded_allowances.length?<p>没有匹配记录，不能据此判断没有授权。</p>:<div className="onchain-table"><table><thead><tr><th>合约 / spender</th><th>额度</th><th>记录风险与来源</th></tr></thead><tbody>{data.recorded_allowances.map(row=><tr key={row.id}><td>{row.contract_address||'合约未知'}<br/>{row.spender}</td><td className="onchain-amount">{row.amount}</td><td>{row.risk_level}<ReadStatus source={row.source} asOf={row.as_of} now={now}/></td></tr>)}</tbody></table></div>}
  <h3>协议暴露记录</h3><p>仅已存记录，尚未进行完整协议索引。{data.coverage.protocols_truncated?'记录超过200条，当前结果已截断。':''}</p>{!data.recorded_protocols.length?<p>没有匹配记录，不能据此判断没有协议仓位。</p>:<div className="onchain-table"><table><thead><tr><th>协议 / 类型</th><th>合约</th><th>记录估值 / 来源</th></tr></thead><tbody>{data.recorded_protocols.map(row=><tr key={row.id}><td>{row.protocol} / {row.position_type}</td><td>{row.contract_address||'未知'}</td><td>{row.usd_value===null?'未定价':row.usd_value+' USD（历史记录）'}<ReadStatus source={row.source} asOf={row.as_of} now={now}/></td></tr>)}</tbody></table></div>}
  <ul>{data.limitations.map(value=><li key={value}>{value}</li>)}</ul><div className="onchain-actions"><button disabled={busy||!!error||!data.snapshot||data.snapshot.stale||onchainStale(data.snapshot.as_of,now)} onClick={()=>research('解释当前授权风险')}>准备授权风险研究</button><button disabled={busy||!!error||!data.snapshot||data.snapshot.stale||onchainStale(data.snapshot.as_of,now)} onClick={()=>research('梳理当前钱包与协议暴露')}>准备钱包暴露研究</button></div></>}
  <OnchainResearchHistory context={context}/>
  {notice&&<p role="status">{notice}</p>}
 </section>;
}
