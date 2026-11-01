import React, { useEffect, useMemo, useRef, useState } from "react";
import { createChart, LineSeries } from "lightweight-charts";
import * as I from "@phosphor-icons/react";
import { analyseSeries, parseCandleCsv, PRICE_FIELDS } from "./chart-analysis.js";
import { loadBackendCandles } from "./market-api.js";
import { clearAicoinRoute } from "./aicoin-routes.js";
import "./chart-analysis.css";

const COLORS = ["#3878df", "#ca8b2c", "#21a47d", "#975fd5", "#d85e7b", "#38a4b6", "#727bc1", "#b18463", "#737c85", "#c5a31f"];
const FIELDS = { open: "开盘价", high: "最高价", low: "最低价", close: "收盘价" };
const initialLeg = (id, label) => ({ id, label, source: "backend", status: "idle", rows: [], detail: "尚未载入数据" });

function AnalysisChart({ result, percent }) {
  const container = useRef(null);
  useEffect(() => {
    if (!container.current || !result) return;
    const chart = createChart(container.current, {
      autoSize: true, layout: { background: { color: "#ffffff" }, textColor: "#7a8490", fontSize: 11 },
      grid: { vertLines: { color: "#f1f3f5" }, horzLines: { color: "#f1f3f5" } },
      timeScale: { timeVisible: true }, rightPriceScale: { borderColor: "#e2e5e8" },
    });
    result.series.forEach((item, index) => {
      const line = chart.addSeries(LineSeries, { color: COLORS[index % COLORS.length], lineWidth: 2,
        priceFormat: { type: "custom", formatter: value => `${Number(value.toPrecision(8))}${percent ? "%" : ""}`, minMove: 0.00000001 } });
      line.setData(item.rows);
    });
    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [result, percent]);
  return <div className="analysis-chart" ref={container} aria-label="对齐数据计算图表" />;
}

export function ChartAnalysisWorkspace({ initialMode = "compare", symbol = "BTC", onModeChange, onClose }) {
  const mode = initialMode;
  const setMode = onModeChange;
  const [legs, setLegs] = useState(() => [initialLeg("leg-1", symbol), initialLeg("leg-2", symbol === "ETH" ? "BTC" : "ETH")]);
  const [field, setField] = useState("close");
  const [comparison, setComparison] = useState("percent");
  const [spread, setSpread] = useState("diff");
  const [formula, setFormula] = useState("A-B");
  const [timeframe, setTimeframe] = useState("1d");
  const [unit, setUnit] = useState("");
  const [unitConfirmed, setUnitConfirmed] = useState(false);
  const [tableOpen, setTableOpen] = useState(false);
  const requests = useRef(new Map());
  const nextId = useRef(3);
  const live = useRef(true);
  const dialog = useRef(null);
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => { live.current = true; return () => { live.current = false; requests.current.clear(); }; }, []);
  useEffect(() => {
    const previous = document.activeElement;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    dialog.current?.querySelector('button[aria-label="关闭K线分析工作区"]')?.focus();
    const keydown = event => {
      if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); close.current(); }
      if (event.key !== "Tab") return;
      const elements = [...dialog.current.querySelectorAll('button:not(:disabled),input:not(:disabled),select:not(:disabled),a[href]')].filter(element => element.offsetParent !== null);
      const first = elements[0], last = elements.at(-1);
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    };
    document.addEventListener("keydown", keydown, true);
    return () => { document.removeEventListener("keydown", keydown, true); document.body.style.overflow = overflow; if (previous?.isConnected) previous.focus(); };
  }, []);

  const patch = (id, values) => setLegs(items => items.map(item => item.id === id ? { ...item, ...values } : item));
  const invalidate = (id, values) => {
    requests.current.delete(id);
    patch(id, { ...values, rows: [], status: "idle", detail: "配置已变更，请重新载入数据" });
    setUnitConfirmed(false);
  };
  const remove = id => {
    requests.current.delete(id);
    setLegs(items => items.filter(item => item.id !== id));
    setUnitConfirmed(false);
  };
  const load = async (leg, file) => {
    const token = Symbol(leg.id);
    requests.current.set(leg.id, token);
    patch(leg.id, { status: "loading", rows: [], detail: "正在读取…" });
    setUnitConfirmed(false);
    try {
      let rows, detail;
      if (file) {
        if (file.size > 1024 * 1024) throw new Error("CSV 最大支持 1 MB");
        rows = parseCandleCsv(await file.text());
        detail = `本地 CSV · ${file.name} · ${rows.length} 根数据`;
      } else {
        const result = await loadBackendCandles(leg.label.trim(), timeframe);
        if (result.status !== "connected") throw new Error(result.source || "后端没有数据");
        rows = result.candles;
        detail = `${result.source} · ${result.asset.symbol} · ${result.asset.venue || "平台未注明"} · ${result.asset.currency || "报价币未注明"} · ${rows.length} 根数据 · ${timeframe}`;
      }
      if (live.current && requests.current.get(leg.id) === token) patch(leg.id, { rows, detail, status: "ready" });
    } catch (error) {
      if (live.current && requests.current.get(leg.id) === token) patch(leg.id, { rows: [], status: "error", detail: error.message });
    } finally {
      if (requests.current.get(leg.id) === token) requests.current.delete(leg.id);
    }
  };

  const expression = spread === "diff" ? "A-B" : spread === "diff_rate" ? "(A-B)/B*100" : formula;
  const analysis = useMemo(() => {
    if (legs.length < 2) return { error: "添加至少两个对比项" };
    if (legs.some(leg => leg.status !== "ready")) return { error: "请先为每个对比项载入数据" };
    if (mode === "spread" && (!unit.trim() || !unitConfirmed)) return { error: "请确认各项采用相同计价单位，再计算价差" };
    if (mode === "spread" && spread !== "formula" && legs.length !== 2) return { error: "价差和价差率使用 A、B 两项；多项组合请选择自定义公式" };
    try { return { result: analyseSeries(legs, { field, mode: mode === "spread" ? "formula" : comparison, formula: expression }) }; }
    catch (error) { return { error: error.message }; }
  }, [legs, field, mode, comparison, expression, spread, unit, unitConfirmed]);
  const result = analysis.result;
  const isPercent = mode === "spread" ? spread === "diff_rate" : comparison === "percent";
  const download = () => {
    if (!result) return;
    const cell = value => '"' + String(value).replace(/^[=+\-@]/, match => "'" + match).replaceAll('"', '""') + '"';
    const lines = [["time_utc", ...result.series.map(item => item.label)].map(cell).join(","),
      ...result.series[0].rows.map((row, index) => [new Date(row.time * 1000).toISOString(), ...result.series.map(item => item.rows[index].value)].map((value, i) => i ? value : cell(value)).join(","))];
    const url = URL.createObjectURL(new Blob(["\uFEFF" + lines.join("\r\n")], { type: "text/csv;charset=utf-8" }));
    const anchor = document.createElement("a"); anchor.href = url; anchor.download = `chart-${mode}-${field}.csv`; anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  return <div className="analysis-backdrop"><section ref={dialog} className="analysis-workspace" role="dialog" aria-modal="true" aria-label={mode === "spread" ? "价差K线工作区" : "对比K线工作区"}>
    <header><div><small>行情研究</small><h2>{mode === "spread" ? "价差 K 线" : "对比 K 线"}</h2></div><nav>
      <button className={mode === "compare" ? "on" : ""} onClick={() => { clearAicoinRoute(); setMode("compare"); }}>走势对比</button>
      <button className={mode === "spread" ? "on" : ""} onClick={() => { clearAicoinRoute(); setMode("spread"); }}>组合价差</button>
    </nav><button aria-label="关闭K线分析工作区" onClick={onClose}><I.X /></button></header>
    <div className="analysis-body"><aside>
      <div className="analysis-section-title"><b>对比项 <small>{legs.length}/10</small></b><button disabled={legs.length >= 10} onClick={() => { setLegs(items => [...items, initialLeg(`leg-${nextId.current++}`, "SOL")]); setUnitConfirmed(false); }}><I.Plus />添加</button></div>
      {legs.map((leg, index) => <article className="analysis-leg" key={leg.id}>
        <div><b style={{ color: COLORS[index] }}>{String.fromCharCode(65 + index)}</b><input aria-label={`对比项${index + 1}名称`} value={leg.label} maxLength={50} onChange={event => invalidate(leg.id, { label: event.target.value })} /><button aria-label={`移除对比项${index + 1}`} disabled={legs.length <= 2} onClick={() => remove(leg.id)}><I.Trash /></button></div>
        <select aria-label={`对比项${index + 1}来源`} value={leg.source} onChange={event => invalidate(leg.id, { source: event.target.value })}><option value="backend">后端 K 线</option><option value="csv">本地 CSV</option></select>
        {leg.source === "backend" ? <button className="analysis-load" disabled={leg.status === "loading" || !leg.label.trim()} onClick={() => load(leg)}>载入数据</button> : <input type="file" accept=".csv,text/csv" aria-label={`导入对比项${index + 1}CSV`} onChange={event => { const file = event.target.files?.[0]; event.target.value = ""; if (file) load(leg, file); }} />}
        <small role={leg.status === "error" ? "alert" : "status"} className={leg.status}>{leg.detail}</small>
      </article>)}
      <p className="analysis-csv-help">CSV 至少包含 time、close；可增加 open、high、low。时间使用 Unix 秒/毫秒或带时区 ISO 格式。文件仅在本页读取。</p>
    </aside><main>
      <div className="analysis-controls"><label>价格字段<select aria-label="分析价格字段" value={field} onChange={event => setField(event.target.value)}>{PRICE_FIELDS.map(value => <option value={value} key={value}>{FIELDS[value]}</option>)}</select></label>
        <label>后端周期<select aria-label="分析后端周期" value={timeframe} onChange={event => { setTimeframe(event.target.value); legs.filter(leg => leg.source === "backend").forEach(leg => requests.current.delete(leg.id)); setLegs(items => items.map(leg => leg.source === "backend" ? { ...leg, rows: [], status: "idle", detail: "周期已变更，请重新载入" } : leg)); setUnitConfirmed(false); }}><option value="1h">1 小时</option><option value="4h">4 小时</option><option value="1d">1 日</option><option value="1wk">1 周</option></select></label>
        {mode === "compare" ? <label>显示方式<select aria-label="对比显示方式" value={comparison} onChange={event => setComparison(event.target.value)}><option value="percent">共同起点涨跌幅</option><option value="price">原始价格叠加</option></select></label> : <label>公式<select aria-label="价差公式类型" value={spread} onChange={event => setSpread(event.target.value)}><option value="diff">价差 A − B</option><option value="diff_rate">价差率 (A − B) / B × 100</option><option value="formula">自定义公式</option></select></label>}
      </div>
      {mode === "spread" && <div className="analysis-formula"><label>公式<input aria-label="组合价差公式" value={expression} readOnly={spread !== "formula"} onChange={event => setFormula(event.target.value)} maxLength={200} /></label><label>计价单位<input aria-label="组合计价单位" value={unit} placeholder="例如 USDT" maxLength={20} onChange={event => { setUnit(event.target.value); setUnitConfirmed(false); }} /></label><label className="analysis-unit"><input type="checkbox" checked={unitConfirmed} onChange={event => setUnitConfirmed(event.target.checked)} />已确认各项计价单位一致</label></div>}
      <p className="analysis-method">{FIELDS[field]}折线 · 仅取全部数据共有的时间点，不插值、不自动换汇{mode === "compare" && comparison === "percent" ? " · 以首个共同时间点为 0%" : ""}。不从各腿高低价推算组合 K 线的高低价。</p>
      {result ? <><div className="analysis-legend">{result.series.map((item, index) => <span key={index}><i style={{ background: COLORS[index] }} /><b>{item.label}</b><strong>{Number(item.rows.at(-1).value.toPrecision(8))}{isPercent ? "%" : mode === "spread" && spread === "diff" ? ` ${unit}` : ""}</strong></span>)}</div><AnalysisChart result={result} percent={isPercent} /><div className="analysis-coverage" aria-label="数据对齐统计">{result.coverage.map((coverage, index) => <span key={legs[index].id}>{String.fromCharCode(65 + index)}：{coverage.input} 根 → 对齐 {coverage.matched} 根，排除 {coverage.excluded} 根</span>)}</div></> : <div className="analysis-empty" role="status"><I.ChartLine /><b>{analysis.error}</b><p>后端离线或数据缺失时不会生成替代曲线。</p></div>}
      <footer><button disabled={!result} onClick={() => setTableOpen(value => !value)}>{tableOpen ? "收起" : "查看"}计算数据</button><button disabled={!result} onClick={download}><I.DownloadSimple />导出 CSV</button><span>最多显示最近 20 行；导出包含全部对齐结果</span></footer>
      {tableOpen && result && <div className="analysis-table"><table><thead><tr><th>时间 UTC</th>{result.series.map((item, index) => <th key={index}>{item.label}</th>)}</tr></thead><tbody>{result.series[0].rows.slice(-20).map(row => { const index = result.series[0].rows.indexOf(row); return <tr key={row.time}><td>{new Date(row.time * 1000).toISOString()}</td>{result.series.map((item, seriesIndex) => <td key={seriesIndex}>{Number(item.rows[index].value.toPrecision(8))}</td>)}</tr>; })}</tbody></table></div>}
    </main></div>
  </section></div>;
}
