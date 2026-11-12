import React from 'react';
export function ResearchPaperReviewControl({attachment,enabled,onChange,onClear,valid,disabled}){
 if(!attachment)return null;
 const material=attachment.material;
 return <section className="research-page-action"><b data-terminal-label>已准备的Paper复盘材料</b><p>{material?.instrument?.symbol} · 成交 {material?.execution_id} · 账户 {material?.account_id}</p><p>勾选后会向配置的模型发送原始订单理由、Paper数量/价格/费用、保存的终端人工笔记、交易日志和历史门禁。材料按成交冻结，不读取实时账户或恢复审批。</p><label><input type="checkbox" checked={enabled} disabled={disabled} onChange={event=>onChange(event.target.checked)}/>附带此成交的Paper复盘材料</label><button type="button" disabled={disabled} onClick={onClear}>取消此复盘准备，转为手动提问</button>{!valid&&<p role="status">材料已过期或不属于当前工作区，请返回原成交重新读取。</p>}</section>;
}
export function ResearchPaperReviewSources({result}){
 const material=result?.provided_paper_review;if(!material)return null;
 return <section className="research-onchain-sources"><h4 data-terminal-label>本次Paper复盘来源</h4><p>{material.instrument?.symbol} · 成交 {material.execution_id} · 账户 {material.account_id}<br/>冻结 {material.captured_at} · 材料包 {result.paper_review_context_snapshot_id}</p><ul>{material.entries.map(entry=><li key={entry.id}><b>[{entry.id}] {entry.kind}{result.cited_paper_review_ids?.includes(entry.id)?' · 所列引用':''}</b><small>记录 {entry.record_id||'历史门禁汇总'}</small></li>)}</ul><small>仅校验结构、身份和引用；不是独立事实核验、正式交易报告或人工复盘完成凭据。</small></section>;
}
