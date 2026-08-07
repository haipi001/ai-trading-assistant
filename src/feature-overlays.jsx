import React, { useMemo, useState } from "react";
import * as I from "@phosphor-icons/react";
import { UtilityToolPanel } from "./utility-tools.jsx";

export const FEATURE_OVERLAY_TYPES = [
  "aceResult",
  "aiChart",
  "attachment",
  "automationCreate",
  "basketPreview",
  "chartSnapshots",
  "copyTrade",
  "coin",
  "dateLocator",
  "dateRange",
  "flash",
  "hyperMarket",
  "reserveDetail",
  "searchResults",
  "shareArticle",
  "submit",
  "summary",
  "tool",
  "trader",
  "transfer",
];

const attachmentOptions = {
  "添加图表快照": ["当前 K 线视图", "主力挂单面板", "深度图", "技术指标参数"],
  "添加自选币种": ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT"],
};

function MetricCards({ items }) {
  return (
    <div className="feature-metrics">
      {items.map(([label, value, tone]) => (
        <article key={label}>
          <small>{label}</small>
          <b className={tone || ""}>{value}</b>
        </article>
      ))}
    </div>
  );
}

export function FeatureOverlayPanel({ model, close, say, go }) {
  const [tab, setTab] = useState("综合结论");
  const [selected, setSelected] = useState([]);
  const [copied, setCopied] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [amount, setAmount] = useState("1000");
  const [stopLoss, setStopLoss] = useState("12");
  const [riskAccepted, setRiskAccepted] = useState(false);
  const [automationPeriod, setAutomationPeriod] = useState("每天");
  const [automationConfirmed, setAutomationConfirmed] = useState(false);
  const [source, setSource] = useState("现货账户");
  const [target, setTarget] = useState("合约账户");
  const [asset, setAsset] = useState(model.title?.split(" ")[0] || "USDT");
  const [date, setDate] = useState("2026-07-22T22:30");
  const [start, setStart] = useState("2026-07-01");
  const [end, setEnd] = useState("2026-07-22");
  const [form, setForm] = useState({ title: "", category: "行情分析", content: "" });
  const [aiAction, setAiAction] = useState("");
  const [snapshotRows, setSnapshotRows] = useState(model.snapshots || []);
  const options = useMemo(
    () => attachmentOptions[model.title] || attachmentOptions["添加图表快照"],
    [model.title],
  );
  const finish = (message) => {
    say(message);
    close();
  };
  const applyDatePreset = (preset) => {
    const ranges = {
      今天: ["2026-07-22", "2026-07-22"],
      近7天: ["2026-07-16", "2026-07-22"],
      近30天: ["2026-06-23", "2026-07-22"],
      今年: ["2026-01-01", "2026-07-22"],
    };
    const [nextStart, nextEnd] = ranges[preset];
    setStart(nextStart);
    setEnd(nextEnd);
    if (model.type === "dateLocator") setDate(`${nextStart}T09:00`);
  };

  if (model.type === "chartSnapshots") {
    const removeSnapshot = (id) => {
      setSnapshotRows(snapshotRows.filter((snapshot) => snapshot.id !== id));
      model.onDeleteSnapshot?.(id);
    };
    return (
      <div className="feature-panel snapshot-manager">
        <header><div><small>最多保留最近 20 条</small><h3>行情快照记录</h3></div>{snapshotRows.length > 0 && <button className="danger-text" onClick={() => { setSnapshotRows([]); model.onClearSnapshots?.(); say("行情快照记录已清空"); }}>清空记录</button>}</header>
        {snapshotRows.length ? <div className="snapshot-list">{snapshotRows.map((snapshot) => (
          <article key={snapshot.id}>
            <span><b>{snapshot.symbol}/USDT · {snapshot.period}</b><small>{snapshot.createdAt} · {snapshot.source}</small></span>
            <div><em>{snapshot.layoutName}</em><small>{snapshot.studies?.length || 0} 个指标 · {snapshot.drawingCount} 个绘图</small></div>
            <button onClick={() => { model.onRestoreSnapshot?.(snapshot); finish(`已恢复 ${snapshot.symbol}/USDT ${snapshot.period} 快照`); }}>应用到图表</button>
            <button aria-label={`删除${snapshot.symbol}${snapshot.period}快照`} onClick={() => removeSnapshot(snapshot.id)}><I.Trash /></button>
          </article>
        ))}</div> : <div className="utility-empty"><I.Images/><b>暂无行情快照</b><small>使用顶部“快照”或图表相机按钮保存当前工作区</small></div>}
        <footer className="feature-actions"><span>{snapshotRows.length} 条本地快照</span><button onClick={close}>关闭</button></footer>
      </div>
    );
  }

  if (model.type === "aiChart" || model.type === "aceResult") {
    return (
      <div className="feature-panel ai-feature-panel">
        <div className="feature-tabs">
          {["综合结论", "趋势", "主力", "风险"].map((name) => (
            <button key={name} className={tab === name ? "on" : ""} onClick={() => setTab(name)}>{name}</button>
          ))}
        </div>
        <div className="ai-conclusion">
          <span><I.Sparkle /></span>
          <div><small>AI 实时结论 · 可信度 78%</small><h3>{tab === "风险" ? "波动正在放大，注意仓位" : "短线中性偏强，等待突破确认"}</h3></div>
          <b>62</b>
        </div>
        <p className="feature-copy">{model.description || "当前买盘承接增强，但主动成交尚未形成连续放量。建议观察关键价位，不将单一信号作为交易依据。"}</p>
        <MetricCards items={[["关键支撑", "65,553", "green"], ["关键阻力", "66,120", "red"], ["主力挂单差", "+$12.4M", "green"]]} />
        <div className="evidence-list">
          {["MA20 仍位于 MA60 下方", "买方深度较 30 分钟前增加 18%", "资金费率 0.0081%，暂无拥挤"].map((x) => <p key={x}><I.CheckCircle />{x}</p>)}
        </div>
        <div className="ai-action-grid">
          {[["画线",I.LineSegment],["创建预警",I.BellRinging],["模拟下单",I.Receipt],["一键分享",I.ShareNetwork]].map(([name,Icon])=><button className={aiAction===name?"on":""} key={name} onClick={()=>{setAiAction(name);say(name==="画线"?"关键支撑与阻力已添加到本地图表":name==="创建预警"?"已创建 65,553 支撑位本地预警":name==="模拟下单"?"已生成 BTC/USDT 风险受控模拟订单草稿":"AI 解读分享卡片已生成")}}><Icon/><span><b>{name}</b><small>{name==="画线"?"支撑与阻力":name==="创建预警"?"关键价位提醒":name==="模拟下单"?"带止损的草稿":"复制分析卡片"}</small></span>{aiAction===name&&<I.Check/>}</button>)}
        </div>
        {aiAction&&<div className="ai-action-result"><I.CheckCircle/><span><b>{aiAction}已准备</b><small>所有动作均为本地演示，不会触发真实交易。</small></span><button onClick={()=>setAiAction("")}>撤销</button></div>}
        <footer className="feature-actions"><button onClick={() => { close(); go("market"); }}>打开完整行情</button><button onClick={() => finish("AI 解读已复制")}>复制结论</button><button className="overlay-primary" onClick={() => finish("已基于当前解读创建策略草稿")}>生成策略草稿</button></footer>
      </div>
    );
  }

  if (model.type === "searchResults") {
    const query = model.query || "BTC/USDT";
    const symbol = query.toUpperCase().match(/BTC|ETH|SOL|XRP|BNB|HYPE/)?.[0] || "BTC";
    const results = [
      ["行情", `${symbol}/USDT 永续`, "最新价、K线、盘口与资金数据", "market"],
      ["快讯", `${symbol} 最新市场异动`, "聚合重要事件、链上与主力变化", "flash"],
      ["要闻", `${symbol} 深度研究与教程`, "文章、报告和 AI 摘要", "news"],
      ["策略", `${symbol} 策略模板`, "网格、指标、套利与跟单方案", "strategy"],
    ];
    return (
      <div className="feature-panel search-result-panel">
        <div className="search-result-query"><I.MagnifyingGlass/><span><small>搜索关键词</small><b>{query}</b></span><em>{results.length} 项结果</em></div>
        <div className="select-list">{results.map(([type,title,description,page])=><button key={type} onClick={()=>{close();go(page);}}><span><small>{type}</small><b>{title}</b><em>{description}</em></span><I.CaretRight/></button>)}</div>
        <footer className="feature-actions"><span>已识别交易标的：{symbol}/USDT</span><button onClick={close}>关闭</button></footer>
      </div>
    );
  }

  if (model.type === "attachment") {
    return (
      <div className="feature-panel">
        <p className="feature-copy">{model.description}</p>
        <div className="select-list">{options.map((x) => <button key={x} className={selected.includes(x) ? "on" : ""} onClick={() => setSelected(selected.includes(x) ? selected.filter((v) => v !== x) : [...selected, x])}><span><I.ChartLine />{x}</span><I.Check /></button>)}</div>
        <footer className="feature-actions"><span>已选 {selected.length} 项</span><button className="overlay-primary" onClick={() => selected.length ? finish(`已添加上下文：${selected.join("、")}`) : say("请至少选择一项")}>添加到对话</button></footer>
      </div>
    );
  }

  if (model.type === "dateLocator" || model.type === "dateRange") {
    const range = model.type === "dateRange";
    return (
      <div className="feature-panel date-feature-panel">
        <div className="preset-row">{["今天", "近7天", "近30天", "今年"].map((x) => <button key={x} className={start === ({今天:"2026-07-22",近7天:"2026-07-16",近30天:"2026-06-23",今年:"2026-01-01"})[x] ? "on" : ""} onClick={() => applyDatePreset(x)}>{x}</button>)}</div>
        {range ? <div className="date-inputs"><label>开始日期<input type="date" value={start} onChange={(e) => setStart(e.target.value)} /></label><span>至</span><label>结束日期<input type="date" value={end} onChange={(e) => setEnd(e.target.value)} /></label></div> : <label className="single-date">定位日期与时间<input type="datetime-local" value={date} onChange={(e) => setDate(e.target.value)} /></label>}
        <div className="date-preview"><I.CalendarDots /><span><b>{range ? `${start} — ${end}` : date.replace("T", " ")}</b><small>应用后将更新 K 线可见范围</small></span></div>
        <footer className="feature-actions"><button onClick={close}>取消</button><button className="overlay-primary" onClick={() => {
          if (range) model.onApplyRange?.({ start, end });
          else model.onApplyDate?.(date);
          finish(range ? `K线范围已切换为 ${start} 至 ${end}` : `已定位到 ${date.replace("T", " ")}`);
        }}>应用</button></footer>
      </div>
    );
  }

  if (model.type === "basketPreview") {
    return (
      <div className="feature-panel order-preview">
        <div className="risk-note"><I.ShieldWarning />模拟预览不会发送真实订单；连接交易账户后仍需二次确认。</div>
        {(model.orders || [['BTC/USDT','买入','限价','65,720','0.01'],['ETH/USDT','买入','限价','3,180','0.20']]).map((r, rowIndex) => <div className="preview-order" key={`${r.pair || r[0]}-${rowIndex}`}>{[r.pair||r[0],r.side||r[1],r.type||r.price||r[3]||"市价",r.amount||r[4]].map((x, i) => <span className={i === 1 ? ((r.side||r[1]) === "买入" ? "green" : "red") : ""} key={`${i}-${x}`}>{x}</span>)}</div>)}
        <MetricCards items={[["订单数", `${model.orders?.length || 2} 笔`], ["预计占用", model.estimatedTotal || "1,293 USDT"], ["最大滑点", "0.15%"]]} />
        <footer className="feature-actions"><button onClick={close}>返回修改</button><button className="overlay-primary" onClick={() => finish("组合订单模拟校验通过，未发送真实交易")}>确认模拟</button></footer>
      </div>
    );
  }

  if (model.type === "copyTrade") {
    return (
      <div className="feature-panel copytrade-panel">
        <p className="feature-copy">{model.description}</p>
        <MetricCards items={[["30D收益", "+84.2%", "green"], ["最大回撤", "-18.6%", "red"], ["胜率", "68%"]]} />
        <label>最大跟单金额（USDT）<input type="number" value={amount} onChange={(e) => setAmount(e.target.value)} /></label>
        <label>止损比例（%）<input type="number" value={stopLoss} onChange={(e) => setStopLoss(e.target.value)} /></label>
        <label className="risk-confirm"><input type="checkbox" checked={riskAccepted} onChange={(e) => setRiskAccepted(e.target.checked)} />我已阅读策略风险与历史回撤说明</label>
        <footer className="feature-actions"><button onClick={close}>取消</button><button className="overlay-primary" onClick={() => Number(amount) > 0 && Number(stopLoss) > 0 && riskAccepted ? finish(`跟单方案已保存：${amount} USDT，止损 ${stopLoss}%`) : say(riskAccepted ? "请输入有效的金额和止损比例" : "请先确认风险说明")}>保存跟单方案</button></footer>
      </div>
    );
  }

  if (model.type === "automationCreate") {
    const isGrid = model.mode?.includes("网格");
    const isIndicator = model.mode?.includes("指标");
    return (
      <div className="feature-panel automation-create">
        <div className="automation-template"><I.Robot /><span><small>{model.mode}</small><h3>{model.title.replace("创建 ", "")}</h3><p>{model.symbol} · {model.risk}</p></span></div>
        <label>投入金额（USDT）<input type="number" min="20" value={amount} onChange={(e)=>setAmount(e.target.value)} /></label>
        {isGrid ? <div className="automation-grid-fields"><label>最低价格<input defaultValue="63,200" /></label><label>最高价格<input defaultValue="68,400" /></label><label>网格数量<input defaultValue="24" /></label></div> : isIndicator ? <><label>运行周期<select value={automationPeriod} onChange={(e)=>setAutomationPeriod(e.target.value)}><option>5分钟</option><option>15分钟</option><option>1小时</option><option>4小时</option></select></label><label>触发规则<input defaultValue="信号确认后生成模拟委托" /></label></> : <><label>执行频率<select value={automationPeriod} onChange={(e)=>setAutomationPeriod(e.target.value)}><option>每天</option><option>每周</option><option>每月</option></select></label><label>止盈目标（可选）<input placeholder="例如 20%" /></label></>}
        <div className="risk-note"><I.ShieldWarning />该模板只会生成本地模拟任务；连接账户后仍需独立授权和二次确认。</div>
        <label className="risk-confirm"><input type="checkbox" checked={automationConfirmed} onChange={(e)=>setAutomationConfirmed(e.target.checked)} />我已核对参数与风险说明</label>
        <footer className="feature-actions"><button onClick={close}>取消</button><button className="overlay-primary" onClick={()=>Number(amount)>=20&&automationConfirmed?finish(`${model.title}的模拟任务已创建`):say(automationConfirmed?"投入金额不能低于 20 USDT":"请先确认参数与风险")}>创建模拟任务</button></footer>
      </div>
    );
  }

  if (model.type === "transfer") {
    return (
      <div className="feature-panel transfer-panel">
        <div className="transfer-accounts"><label>从<select value={source} onChange={(e) => setSource(e.target.value)}><option>现货账户</option><option>合约账户</option><option>资金账户</option></select></label><button onClick={() => { setSource(target); setTarget(source); }}><I.ArrowsLeftRight /></button><label>到<select value={target} onChange={(e) => setTarget(e.target.value)}><option>合约账户</option><option>现货账户</option><option>资金账户</option></select></label></div>
        <label>币种<select value={asset} onChange={(e) => setAsset(e.target.value)}><option>USDT</option><option>BTC</option><option>ETH</option></select></label>
        <label>划转数量<input type="number" value={amount} onChange={(e) => setAmount(e.target.value)} /><small>可用 5,000.00 {asset}</small></label>
        <div className="risk-note"><I.Info />当前为本地演示，不会提交真实资产划转。</div>
        <footer className="feature-actions"><button onClick={close}>取消</button><button className="overlay-primary" onClick={() => Number(amount) > 0 ? finish(`已生成 ${source} → ${target} 的 ${amount} ${asset} 划转预览`) : say("请输入划转数量")}>生成预览</button></footer>
      </div>
    );
  }

  if (model.type === "submit") {
    return (
      <div className="feature-panel submit-panel">
        <label>文章标题<input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="输入清晰、准确的标题" /></label>
        <label>分类<select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}><option>行情分析</option><option>Web3.0</option><option>行业报告</option><option>科普</option></select></label>
        <label>正文<textarea value={form.content} onChange={(e) => setForm({ ...form, content: e.target.value })} placeholder="支持 Markdown，至少 50 字" /></label>
        <div className="submit-meta"><span>{form.content.length} 字</span><span>草稿自动保存在本机</span></div>
        <footer className="feature-actions"><button onClick={() => finish("投稿草稿已保存")}>保存草稿</button><button className="overlay-primary" onClick={() => { if (!form.title.trim() || form.content.trim().length < 50) return say("请填写标题，正文至少 50 字"); setSubmitted(true); }}>提交审核</button></footer>
        {submitted && <div className="submitted-state"><I.CheckCircle /><b>投稿已进入模拟审核队列</b><button onClick={close}>完成</button></div>}
      </div>
    );
  }

  if (model.type === "shareArticle") {
    return (
      <div className="feature-panel share-panel">
        <div className="share-preview"><I.Article /><span><b>AI交易助手 深度文章</b><small>{model.description}</small></span></div>
        <div className="choice-grid">{["复制链接", "生成分享卡片", "X / Twitter", "微信"].map((x) => <button className={copied === x ? "on" : ""} key={x} onClick={() => { setCopied(x); say(`${x}已准备`); }}>{x}</button>)}</div>
        <footer className="feature-actions"><button onClick={close}>取消</button><button className="overlay-primary" onClick={() => copied ? finish(`已完成：${copied}`) : say("请选择分享方式")}>完成分享</button></footer>
      </div>
    );
  }

  if (model.type === "tool") {
    return <UtilityToolPanel model={model} close={close} say={say} go={go} />;
  }

  if (model.type === "coin") {
    const symbol = model.title?.replace("/USDT", "") || "BTC";
    return (
      <div className="feature-panel detail-feature-panel">
        <div className="ai-conclusion">
          <span><I.CurrencyCircleDollar /></span>
          <div><small>{model.title} · 综合行情</small><h3>{symbol} 当前处于震荡整理区间</h3></div>
          <b className="green">+0.88%</b>
        </div>
        <p className="feature-copy">{model.description || `${symbol} 的价格、成交、资金与市场热度概览。`}</p>
        <MetricCards items={[["最新价", symbol === "BTC" ? "$65,731.77" : "$148.32"], ["24H成交额", "$2.84B"], ["资金净流入", "+$18.6M", "green"]]} />
        <div className="feature-tabs">{["价格", "成交", "资金", "资讯"].map((name) => <button key={name} className={tab === name ? "on" : ""} onClick={() => setTab(name)}>{name}</button>)}</div>
        <div className="feature-timeline"><p><i />{tab === "资金" ? "主动买入占比 56.8%" : `${tab}数据已同步至最新周期`}</p><p><i />关键支撑与阻力已完成计算</p><p><i />相关快讯与链上异动已聚合</p></div>
        <footer className="feature-actions"><button onClick={() => { close(); go("market"); }}>打开完整行情</button><button onClick={() => finish(`${symbol} 已加入自选`)}>加入自选</button><button className="overlay-primary" onClick={() => { close(); go("strategy"); }}>创建策略</button></footer>
      </div>
    );
  }

  if (["flash", "hyperMarket", "reserveDetail", "summary", "trader"].includes(model.type)) {
    const labels = {
      flash: ["事件影响", "中性偏多", "更新时间", "刚刚", "关联标的", "BTC · ETH"],
      hyperMarket: ["资金费率", "0.0081%", "持仓量变化", "+4.2%", "多空比", "1.18"],
      reserveDetail: ["本期变化", "+2,480 BTC", "披露日期", "2026-07-22", "数据状态", "已核验"],
      summary: ["阅读时间", "5 分钟", "核心观点", "3 条", "影响周期", "短中期"],
      trader: ["30D收益", "+42.8%", "胜率", "71%", "最大回撤", "-12.4%"],
    }[model.type];
    const metrics = [[labels[0], labels[1], labels[1].startsWith("+") ? "green" : ""], [labels[2], labels[3]], [labels[4], labels[5]]];
    return (
      <div className="feature-panel detail-feature-panel">
        <p className="feature-copy">{model.description || `${model.title} 的完整数据详情。`}</p>
        <MetricCards items={metrics} />
        <div className="feature-timeline"><p><i />数据源已完成交叉核验</p><p><i />关联市场指标已同步</p><p><i />下次自动刷新：5 分钟后</p></div>
        <footer className="feature-actions"><button onClick={() => { close(); go(model.type === "trader" ? "chain" : model.type === "reserveDetail" ? "data" : "market"); }}>打开关联页面</button><button onClick={() => finish("已加入关注")}>{model.type === "trader" ? "关注交易员" : "加入关注"}</button><button className="overlay-primary" onClick={() => finish("详情已复制")}>复制数据</button></footer>
      </div>
    );
  }

  return null;
}
