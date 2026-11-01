import React, { useEffect, useMemo, useState } from "react";
import * as I from "@phosphor-icons/react";
import { filterIndicatorLibrary, INDICATOR_FAVORITES_KEY, readIndicatorFavorites, RENDERED_INDICATORS, toggleIndicatorFavorite } from "./indicator-library.js";
import { readScriptStore, SCRIPT_STORE_EVENT, SCRIPT_STORE_KEY } from "./script-drafts.js";

export function IndicatorCenter({ studies, setStudies, close, say, openOverlay, onOpenScript, onNewScript, layouts = [], onOpenLayout, onSaveLayout }) {
  const [tab, setTab] = useState("指标库"), [section, setSection] = useState("全部"), [category, setCategory] = useState("全部"), [query, setQuery] = useState("");
  const [favorites, setFavorites] = useState([]), [documents, setDocuments] = useState([]), [favoriteError, setFavoriteError] = useState(""), [scriptError, setScriptError] = useState("");
  const [classic, setClassic] = useState(false);
  useEffect(() => {
    const reload = () => {
      try { setFavorites(readIndicatorFavorites(window.localStorage)); setFavoriteError(""); }
      catch (failure) { setFavoriteError(failure.message); }
      try { setDocuments(readScriptStore(window.localStorage).data.documents.filter(item => !item.archived)); setScriptError(""); }
      catch (failure) { setScriptError(failure.message); }
    };
    const storage = event => { if ([SCRIPT_STORE_KEY, INDICATOR_FAVORITES_KEY, null].includes(event.key)) reload(); };
    reload(); window.addEventListener("storage", storage); window.addEventListener(SCRIPT_STORE_EVENT, reload);
    return () => { window.removeEventListener("storage", storage); window.removeEventListener(SCRIPT_STORE_EVENT, reload); };
  }, []);
  const rows = useMemo(() => filterIndicatorLibrary({ section, category, query, favorites, studies }), [section, category, query, favorites, studies]);
  const favorite = name => {
    try { setFavorites(toggleIndicatorFavorite(window.localStorage, name)); setFavoriteError(""); }
    catch (failure) { setFavoriteError(failure.message); }
  };
  const scriptRows = documents.filter(item => item.name.toLowerCase().includes(query.toLowerCase()));
  let content;
  if (tab === "指标库" && ["我的", "编写指标"].includes(section)) content = <div className="indicator-script-list"><header><b>本机脚本</b><button disabled={!!scriptError} onClick={onNewScript}>新建脚本</button></header>{scriptRows.length ? scriptRows.map(item => <article key={item.id}><span><b>{item.name}</b><small>v{item.version} · {new Date(item.updatedAt).toLocaleString()} · 未编译</small></span><button disabled={!!scriptError} onClick={() => onOpenScript(item.id)}>编辑</button></article>) : <p>尚无已保存的本机脚本。可新建、导入并保存后在这里打开。</p>}</div>;
  else if (tab === "指标库") content = <div className={`indicator-catalog ${classic ? "classic" : ""}`}>{rows.length ? rows.map(row => {
    const active = studies.includes(row[0]); const supported = RENDERED_INDICATORS.has(row[0]);
    return <article key={row[0]}><button aria-label={`收藏${row[0]}`} className={favorites.includes(row[0]) ? "fav" : ""} onClick={() => favorite(row[0])}><I.Star weight={favorites.includes(row[0]) ? "fill" : "regular"} /></button><span><b>{row[0]}</b><small>{row[1]}</small></span>{row[2] && <em>{row[2]}</em>}<button className={active ? "added" : ""} onClick={() => {
      if (!supported) return openOverlay("help", `${row[0]}数据需求`, { description: "该指标需要扩展数据与专用计算接口，当前尚未接入，不会添加虚假的图表结果。" });
      setStudies(active ? studies.filter(item => item !== row[0]) : [...studies, row[0]]); say(`${row[0]} 已${active ? "移除" : "添加到图表"}`);
    }}>{supported ? active ? "已添加" : "添加" : "需数据接口"}</button></article>;
  }) : <p className="indicator-library-empty">暂无匹配指标；可切换分类或清除搜索条件。</p>}</div>;
  else if (tab === "布局广场") content = <div className="indicator-script-list"><header><b>本机布局</b><button onClick={onSaveLayout}>保存当前布局</button></header>{layouts.map(layout => <article key={layout.id}><span><b>{layout.name}</b><small>{layout.symbol} · {layout.saved ? "已保存" : "未保存"}</small></span><button onClick={() => onOpenLayout(layout)}>打开</button></article>)}<p>当前展示本机布局；原版社区布局服务尚未接入。</p></div>;
  else if (tab === "信号预警") content = <div className="indicator-subpage"><I.BellRinging /><h3>指标信号预警</h3><p>打开已有预警中心配置本地提醒；自定义脚本信号仍需编译和执行服务。</p><button onClick={() => openOverlay("alertCenter", "指标信号预警", { initialTab: "信号", alertType: "指标预警" })}>打开信号预警</button></div>;
  else content = <div className="indicator-subpage"><I.ChartLine /><h3>{tab}</h3><p>{tab === "指标广场" ? "原版社区指标目录服务尚未接入；可以先管理本机脚本。" : "指标胜率需要可追溯的信号与回测结果；当前没有可计算的真实记录。"}</p><button onClick={() => { setTab("指标库"); setSection("我的"); }}>查看本机脚本</button></div>;
  return <div className="chart-center-backdrop" onClick={close}><section className="indicator-center" role="dialog" aria-label="指标中心" onClick={event => event.stopPropagation()}>
    <header><nav>{["指标库", "指标广场", "指标胜率", "信号预警", "布局广场"].map(item => <button className={tab === item ? "on" : ""} key={item} onClick={() => setTab(item)}>{item}</button>)}</nav><button onClick={() => setClassic(value => !value)}>{classic ? "切换新版" : "切换经典版"}</button><button aria-label="关闭指标中心" onClick={close}><I.X /></button></header>
    <div className="indicator-center-body"><aside>{[["全部", I.ChartLine], ["收藏", I.Star], ["我的", I.UserCircle], ["快捷", I.CursorClick], ["编写指标", I.Code]].map(([item, Icon]) => <button className={section === item ? "on" : ""} key={item} onClick={() => { setSection(item); setTab("指标库"); }}><Icon />{item}</button>)}</aside><main>
      {(favoriteError || scriptError) && <p className="script-error" role="alert">{[favoriteError, scriptError].filter(Boolean).join("；")}</p>}<label className="indicator-search"><I.MagnifyingGlass /><input aria-label="搜索指标" value={query} onChange={event => setQuery(event.target.value)} placeholder="搜索指标或本机脚本" /></label>
      {tab === "指标库" && !["我的", "编写指标"].includes(section) && <nav>{["全部", "技术指标", "特色指标", "市场指数"].map(item => <button className={category === item ? "on" : ""} key={item} onClick={() => setCategory(item)}>{item}</button>)}</nav>}
      {content}
    </main></div>
  </section></div>;
}
