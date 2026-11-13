import React from 'react';
export function ResearchBacktestSources({result}){
 const material=result?.provided_backtest;
 if(result?.status!=='ok'||result.context_scope!=='owned_frozen_backtest_material'||!material)return null;
 const source=material.research_packet?.data_contract;
 return <details><summary>回测来源 [BT1] · 历史模拟</summary><p>回测 {material.backtest_run_id} · AI材料快照 {result.backtest_context_snapshot_id}</p><p>冻结时间：{material.captured_at}；数据区间：{material.date_from} 至 {material.date_to}。</p><p>来源：{source?.source||'未记录'}；周期：{source?.timeframe||'未记录'}；K线数：{source?.candle_count??'未记录'}。</p><p>SHA-256：{material.content_hash}</p><p>引用校验只确认回复对应这份保存材料，不证明行情或模拟结果独立可靠。没有重新运行编辑器脚本，不表示当前账户绩效或交易授权。</p><details><summary data-terminal-label>冻结参数与阻断原因</summary><pre style={{whiteSpace:'pre-wrap'}}>{JSON.stringify({parameters:material.parameters,blockers:material.research_packet?.blockers,warnings:material.research_packet?.warnings},null,2)}</pre></details></details>;
}
