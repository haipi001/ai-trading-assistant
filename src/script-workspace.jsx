import React, { useEffect, useRef, useState } from "react";
import * as I from "@phosphor-icons/react";
import { checkScriptText, commitScriptStore, parseScriptImport, readScriptBuffer, readScriptStore, SCRIPT_BUFFER_KEY, SCRIPT_STORE_EVENT, SCRIPT_STORE_KEY } from "./script-drafts.js";
import "./script-workspace.css";

export const EMPTY_SCRIPT = "// @version=2\n// 在这里创建您的自定义脚本\n";
function loadSnapshot() {
  let snapshot = null, buffer = null, error = "", bufferError = "";
  try { snapshot = readScriptStore(window.localStorage); } catch (failure) { error = failure.message; }
  // A damaged permanent store must not prevent recovery of the tab's buffer.
  try { buffer = readScriptBuffer(window.sessionStorage); } catch (failure) { bufferError = failure.message; }
  return { snapshot, buffer, error, bufferError };
}

export function useScriptWorkspace(initialCode = EMPTY_SCRIPT) {
  const initial = useRef(null);
  if (!initial.current) initial.current = loadSnapshot();
  const selected = initial.current.snapshot?.data.documents.find(item => item.id === initial.current.snapshot.data.selectedId);
  const [snapshot, setSnapshot] = useState(initial.current.snapshot);
  const [activeId, setActiveId] = useState(initial.current.buffer ? initial.current.buffer.activeId : selected?.id || null);
  const [name, setNameState] = useState(initial.current.buffer?.name ?? selected?.name ?? "未命名指标");
  const [code, setCodeState] = useState(initial.current.buffer?.code ?? selected?.code ?? initialCode);
  const [bufferWarning, setBufferWarning] = useState(initial.current.bufferError);
  const bufferWritable = useRef(!initial.current.bufferError);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(initial.current.error);
  const [notice, setNotice] = useState("");
  const [check, setCheck] = useState(null);
  const busyRef = useRef(false);
  const live = useRef(true);
  const state = useRef(null);
  state.current = { snapshot, activeId, name, code };
  const current = snapshot?.data.documents.find(item => item.id === activeId);
  const dirty = current ? name !== current.name || code !== current.code : name !== "未命名指标" || code !== initialCode;
  const setCode = value => { setCodeState(value); setCheck(null); setNotice(""); };
  const setName = value => { setNameState(value); setNotice(""); };
  useEffect(() => {
    if (!bufferWritable.current) return;
    try { window.sessionStorage.setItem(SCRIPT_BUFFER_KEY, JSON.stringify({ schema: 1, activeId, name, code })); setBufferWarning(""); }
    catch { setBufferWarning("本标签页缓冲不可写，请保存或导出当前代码后再切换页面"); }
  }, [activeId, name, code]);
  useEffect(() => {
    live.current = true;
    const changed = event => { if (event.key === SCRIPT_STORE_KEY) setError("其他页面修改了草稿库；当前代码已保留，请先刷新草稿列表"); };
    window.addEventListener("storage", changed);
    return () => { live.current = false; window.removeEventListener("storage", changed); };
  }, []);
  useEffect(() => {
    if (!dirty) return;
    const warn = event => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const commit = (base, action) => commitScriptStore(window.localStorage, base.raw, action, { id: crypto.randomUUID() });
  const preserve = base => {
    const editor = state.current;
    const saved = base.data.documents.find(item => item.id === editor.activeId);
    if ((saved && saved.code === editor.code && saved.name === editor.name) || (!saved && editor.code === initialCode && editor.name === "未命名指标")) return base;
    return commit(base, { type: "save", id: editor.activeId, name: editor.name, code: editor.code });
  };
  const execute = async task => {
    if (busyRef.current) return false;
    busyRef.current = true; setBusy(true); setError(""); setNotice("");
    try {
      const work = async () => {
        const base = state.current.snapshot;
        if (!base) throw new Error("无法读取草稿库；请先导出当前代码，原数据未覆盖");
        return await task(base);
      };
      const result = navigator.locks?.request ? await navigator.locks.request(SCRIPT_STORE_KEY, work) : await work();
      window.dispatchEvent(new CustomEvent(SCRIPT_STORE_EVENT));
      if (live.current) {
        setSnapshot(result.snapshot);
        if (result.openId !== undefined) {
          const document = result.snapshot.data.documents.find(item => item.id === result.openId);
          setActiveId(document?.id || null); setNameState(document?.name || "未命名指标"); setCodeState(document?.code ?? initialCode); setCheck(null);
        }
        setNotice(result.notice || "已保存到本机草稿库");
      }
      return true;
    } catch (failure) {
      if (live.current) setError(failure.message);
      return false;
    } finally { busyRef.current = false; if (live.current) setBusy(false); }
  };
  const save = (copy = false) => execute(base => {
    const editor = state.current;
    const next = commit(base, { type: copy ? "copy" : "save", id: editor.activeId, name: copy ? editor.name.slice(0, 76) + " 副本" : editor.name, code: editor.code });
    return { snapshot: next, openId: next.data.selectedId, notice: copy ? "已另存为独立副本" : "已保存到本机草稿库" };
  });
  const open = id => execute(base => {
    const next = commit(preserve(base), { type: "select", id });
    return { snapshot: next, openId: id, notice: "已打开草稿，原有修改已保存" };
  });
  const create = () => execute(base => {
    const next = commit(preserve(base), { type: "save", id: null, name: "未命名指标", code: EMPTY_SCRIPT });
    return { snapshot: next, openId: next.data.selectedId, notice: "已新建本地草稿" };
  });
  const archive = id => execute(base => {
    const preserved = preserve(base);
    const next = commit(preserved, { type: "archive", id });
    const editor = state.current;
    return { snapshot: next, ...(id === editor.activeId ? { openId: null } : editor.activeId === null && preserved.raw !== base.raw ? { openId: preserved.data.selectedId } : {}), notice: "已归档，可在归档列表恢复" };
  });
  const unarchive = id => execute(base => ({ snapshot: commit(base, { type: "unarchive", id }), notice: "草稿已恢复" }));
  const restore = version => execute(base => {
    if (!state.current.activeId) throw new Error("请先打开已保存的草稿");
    const next = commit(preserve(base), { type: "restore-version", id: state.current.activeId, version });
    return { snapshot: next, openId: state.current.activeId, notice: "历史内容已恢复为新版本，原版本仍保留" };
  });
  const importFile = file => execute(async base => {
    if (file.size > 150000) throw new Error("导入文件最大150KB，代码最多100,000字符");
    const imported = parseScriptImport(await file.text(), file.name);
    const next = commit(preserve(base), { type: "copy", id: null, ...imported });
    return { snapshot: next, openId: next.data.selectedId, notice: "文件已导入为独立草稿" };
  });
  const refresh = () => {
    if (busyRef.current) return;
    const loaded = loadSnapshot(); setSnapshot(loaded.snapshot); setError(loaded.error);
    bufferWritable.current = !loaded.bufferError; setBufferWarning(loaded.bufferError);
    setNotice(loaded.error ? "" : "列表已刷新，编辑区内容保留；保存会追加新版本");
  };
  return { snapshot, activeId, name, setName, code, setCode, current, dirty, busy, error, bufferWarning, notice, check,
    save, open, create, archive, unarchive, restore, importFile, refresh,
    checkCode: () => setCheck({ code, diagnostics: checkScriptText(code) }),
    requestCompile: () => setError("原版编译服务尚未接入，未执行编译；本地检查只检查基础文本结构"),
  };
}

export function ScriptEditor({ workspace: w, onAI, onBacktest }) {
  const [query, setQuery] = useState("");
  const [archived, setArchived] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const codeArea = useRef(null);
  const documents = (w.snapshot?.data.documents || []).filter(item => item.archived === archived && item.name.toLowerCase().includes(query.toLowerCase()));
  const exportFile = json => {
    const content = json ? JSON.stringify({ format: "ai-trading-script", version: 1, name: w.name, code: w.code }, null, 2) : w.code;
    const url = URL.createObjectURL(new Blob([content], { type: json ? "application/json" : "text/plain;charset=utf-8" }));
    const anchor = document.createElement("a"); anchor.href = url; anchor.download = (w.name.replace(/[<>:"/\\|?*\x00-\x1f]/g, "_").slice(0, 80) || "indicator") + (json ? ".json" : ".aiscript"); anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  const diagnostics = w.check?.code === w.code ? w.check.diagnostics : null;
  const locate = item => {
    const lines = codeArea.current.value.split("\n"); const start = lines.slice(0, item.line - 1).reduce((sum, line) => sum + line.length + 1, 0) + item.column - 1;
    codeArea.current?.focus(); codeArea.current?.setSelectionRange(start, start + 1);
  };
  return <div className="script-editor-workspace">
    <aside><header><b>本机脚本</b><button disabled={w.busy} onClick={w.create} aria-label="新建指标脚本"><I.Plus /></button></header>
      <input aria-label="搜索本机脚本" value={query} onChange={event => setQuery(event.target.value)} placeholder="搜索已保存的指标" />
      <label className="script-archive-switch"><input type="checkbox" checked={archived} onChange={event => setArchived(event.target.checked)} />查看归档</label>
      <div className="script-document-list">{documents.length ? documents.map(item => <article key={item.id} className={w.activeId === item.id ? "on" : ""}><button disabled={w.busy || archived} onClick={() => w.open(item.id)}><b>{item.name}</b><small>v{item.version} · {new Date(item.updatedAt).toLocaleString()}</small></button>{archived ? <button disabled={w.busy} onClick={() => w.unarchive(item.id)}>恢复</button> : <button aria-label={`归档${item.name}`} disabled={w.busy} onClick={() => w.archive(item.id)}><I.Archive /></button>}</article>) : <p>暂无{archived ? "归档" : "保存的"}脚本</p>}</div>
      <button disabled={w.busy} onClick={w.refresh}><I.ArrowsClockwise />刷新列表</button>
    </aside>
    <section><header><input aria-label="指标脚本名称" value={w.name} disabled={w.busy} maxLength={80} onChange={event => w.setName(event.target.value)} /><em>{w.dirty ? "未保存" : w.current ? `已保存 v${w.current.version}` : "新草稿"}</em>
      <button disabled={w.busy} onClick={() => w.save(false)}>保存</button><button disabled={w.busy} onClick={() => w.save(true)}>另存副本</button><button disabled={w.busy} onClick={onAI}><I.Sparkle />AI写指标</button>
    </header>
    <nav><button onClick={w.checkCode}>本地检查</button><button onClick={w.requestCompile}>编译</button><button disabled={w.busy} onClick={onBacktest}>立即回测</button><button onClick={() => setHistoryOpen(value => !value)}>版本历史</button><button onClick={() => exportFile(false)}>导出脚本</button><button onClick={() => exportFile(true)}>导出JSON</button><label className="script-import">导入<input aria-label="导入指标脚本" type="file" disabled={w.busy} accept=".aiscript,.txt,.json,text/plain,application/json" onChange={event => { const file = event.target.files?.[0]; event.target.value = ""; if (file) w.importFile(file); }} /></label></nav>
    {w.error && <p className="script-error" role="alert">{w.error}</p>}{w.bufferWarning && <p className="script-error" role="alert">{w.bufferWarning}</p>}{w.notice && <p className="script-notice" role="status">{w.notice}</p>}
    <textarea ref={codeArea} aria-label="指标脚本代码" spellCheck={false} disabled={w.busy} maxLength={100000} value={w.code} onChange={event => w.setCode(event.target.value)} onKeyDown={event => { if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s") { event.preventDefault(); w.save(false); } }} />
    <footer><span>{w.busy ? "正在写入本机草稿…" : diagnostics ? `基础检查完成：${diagnostics.filter(item => item.severity === "error").length} 错误，${diagnostics.filter(item => item.severity === "warning").length} 提醒 · 未编译` : "尚未检查 · 未编译"}</span><small>{w.code.split("\n").length} 行 · {w.code.length}/100,000 字符</small></footer>
    {diagnostics && <div className="script-diagnostics">{diagnostics.length ? diagnostics.slice(0, 50).map((item, index) => <button key={index} className={item.severity} onClick={() => locate(item)}>L{item.line}:{item.column} · {item.severity === "error" ? "错误" : "提醒"} · {item.message}</button>) : <p>未发现括号、字符串或注释的基础结构错误；不代表语义正确或编译通过。</p>}{diagnostics.length > 50 && <p>仅显示前50条</p>}</div>}
    {historyOpen && <div className="script-history"><b>历史版本（恢复会新增版本，不删除原记录）</b>{w.current?.history.length ? [...w.current.history].reverse().map(item => <article key={item.version}><span>v{item.version} · {item.name} · {new Date(item.savedAt).toLocaleString()}</span><button disabled={w.busy} onClick={() => w.restore(item.version)}>恢复此版本</button><details><summary>查看代码</summary><pre>{item.code}</pre></details></article>) : <p>保存修改后会在这里保留之前的版本。</p>}</div>}
    </section>
  </div>;
}
