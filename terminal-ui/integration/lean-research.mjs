/** Research configuration only; does not execute or claim a LEAN connection. */
export function installLeanResearch({bar}) {
 const button=document.createElement('button');button.textContent='量化 / 策略研究';bar.append(button);
 const panel=document.createElement('dialog');panel.setAttribute('aria-label','量化策略研究');
 panel.style.cssText='width:min(920px,92vw);max-height:85vh;overflow:auto;background:var(--bg,#151a21);color:inherit;border:1px solid #536170;padding:24px;font:inherit';
 panel.innerHTML=`<form method="dialog"><button style="float:right">关闭</button></form><small>QUANT RESEARCH · 研究配置</small><h2>从信号到组合，逐层验证策略</h2><p>参考 LEAN 模块化框架 · 引擎未连接 · 实盘关闭</p><p>标的池 → Alpha 信号 → 组合构建 → 风险管理 → 执行模型</p><form data-config style="display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:16px">
 <label>策略模板<select name="alpha"><option>趋势跟随 / 均线交叉</option><option>均值回归 / 标准分数</option><option>动量轮动 / 横截面排名</option></select></label>
 <label>研究标的（逗号分隔）<input name="symbols" value="BTCUSDT,ETHUSDT" required maxlength="500"></label>
 <label>组合模型<select name="portfolio"><option>等权重</option><option>逆波动率</option></select></label>
 <label>信号周期<select name="resolution"><option>1D</option><option>1H</option></select></label>
 <label>单标的权重上限 %<input name="weight" type="number" min="1" max="100" value="25" required></label>
 <label>回撤研究阈值 %<input name="drawdown" type="number" min="1" max="100" value="10" required></label>
 <label>单边手续费 bps<input name="fee" type="number" min="0" max="1000" step="0.1" value="10" required></label>
 <label>单边滑点 bps<input name="slippage" type="number" min="0" max="1000" step="0.1" value="5" required></label>
 <label>样本内开始<input name="start" type="date" value="2023-01-01" required></label>
 <label>样本内结束<input name="end" type="date" value="2024-12-31" required></label>
 <label>样本外结束<input name="holdout" type="date" value="2025-12-31" required></label>
 <button type="submit">保存研究配置</button></form>
 <p data-status role="status"></p><h3>研究验证门槛</h3><ul><li>数据：复权、缺失值、时区、幸存者偏差与未来数据检查</li><li>验证：样本外测试、滚动验证、参数敏感性与基准比较</li><li>成本：手续费、滑点、换手率与流动性约束</li><li>结果待计算：净值、Sharpe、最大回撤、胜率、交易笔数</li></ul><p>保存仅记录本地研究假设。配置中的阈值尚未由执行引擎强制实施；没有真实历史回测结果，不能进入交易审批。</p><a href="https://github.com/QuantConnect/Lean" target="_blank" rel="noopener noreferrer">参考 LEAN 源码与文档 ↗</a>`;
 document.body.append(panel);
 const form=panel.querySelector('[data-config]'),status=panel.querySelector('[data-status]'),key='terminal-quant-research-v1';
 try {const saved=JSON.parse(localStorage.getItem(key)||'null');if(saved)for(const [name,value] of Object.entries(saved))if(form.elements.namedItem(name))form.elements.namedItem(name).value=String(value);}catch{status.textContent='本地配置无法读取，可重新填写。';}
 form.onsubmit=event=>{event.preventDefault();if(!form.reportValidity())return;const config=Object.fromEntries(new FormData(form));if(!(config.start<config.end&&config.end<config.holdout)){status.textContent='日期须满足：样本内开始 < 样本内结束 < 样本外结束。';return;}if(!config.symbols.split(',').some(s=>s.trim())){status.textContent='请填写至少一个研究标的。';return;}try{localStorage.setItem(key,JSON.stringify(config));status.textContent='研究配置已保存 · 待连接历史数据和回测引擎 · 未产生订单';}catch{status.textContent='保存失败：本地存储不可用。';}};
 button.onclick=()=>panel.showModal();
}
