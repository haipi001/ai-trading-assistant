export const SCRIPT_STORE_KEY = "ai-trading-assistant-script-workspace-v1";
export const SCRIPT_STORE_EVENT = "ai-trading-assistant-script-drafts";
export const SCRIPT_BUFFER_KEY = SCRIPT_STORE_KEY + ":editing-buffer";
const LIMIT = 2 * 1024 * 1024;
const validTime = value => typeof value === "string" && Number.isFinite(Date.parse(value));
const validName = value => typeof value === "string" && value.trim().length > 0 && value.length <= 80;
const validCode = value => typeof value === "string" && value.length <= 100000;

export function readScriptBuffer(storage) {
  const raw = storage.getItem(SCRIPT_BUFFER_KEY);
  if (raw === null) return null;
  let value;
  try { value = JSON.parse(raw); } catch { throw new Error("编辑缓冲格式损坏，原数据未改写；请保存或导出当前代码"); }
  if (raw.length > 700000 || value?.schema !== 1 || typeof value.name !== "string" || value.name.length > 80 || !validCode(value.code) || !(value.activeId === null || (typeof value.activeId === "string" && value.activeId.length <= 100))) throw new Error("编辑缓冲版本或结构不支持，原数据未改写；请保存或导出当前代码");
  return value;
}

export function readScriptStore(storage) {
  const raw = storage.getItem(SCRIPT_STORE_KEY);
  if (raw === null) return { raw, data: { schema: 1, revision: 0, selectedId: null, documents: [] } };
  if (raw.length > LIMIT) throw new Error("草稿库超出大小限制，原数据未改写");
  let data;
  try { data = JSON.parse(raw); } catch { throw new Error("草稿库格式损坏，原数据未改写"); }
  if (data?.schema !== 1 || !Number.isSafeInteger(data.revision) || data.revision < 0 || !Array.isArray(data.documents) || data.documents.length > 100) throw new Error("草稿库版本或结构不支持，原数据未改写");
  const ids = new Set();
  for (const document of data.documents) {
    if (typeof document.id !== "string" || !document.id || document.id.length > 100 || ids.has(document.id) || !validName(document.name) || !validCode(document.code) || !validTime(document.updatedAt) || typeof document.archived !== "boolean" || !Number.isSafeInteger(document.version) || document.version < 1 || !Array.isArray(document.history) || document.history.length > 50) throw new Error("草稿记录不完整，原数据未改写");
    ids.add(document.id);
    let previous = 0;
    for (const item of document.history) {
      if (!validName(item.name) || !validCode(item.code) || !validTime(item.savedAt) || !Number.isSafeInteger(item.version) || item.version <= previous || item.version >= document.version) throw new Error("草稿历史版本损坏，原数据未改写");
      previous = item.version;
    }
  }
  if (data.selectedId !== null && (!ids.has(data.selectedId) || data.documents.find(item => item.id === data.selectedId).archived)) throw new Error("草稿选中记录无效，原数据未改写");
  return { raw, data };
}

export function commitScriptStore(storage, expectedRaw, action, { now = new Date().toISOString(), id } = {}) {
  const snapshot = readScriptStore(storage);
  if (snapshot.raw !== expectedRaw) throw new Error("草稿库已被其他页面修改；请刷新列表或导出当前代码后再处理");
  if (!validTime(now)) throw new Error("保存时间无效");
  const data = structuredClone(snapshot.data);
  let document = data.documents.find(item => item.id === action.id);
  if (action.type === "save" || action.type === "copy") {
    if (!validName(action.name) || !validCode(action.code)) throw new Error("名称需为1–80字符，代码最多100,000字符");
    if (action.type === "copy" || action.id === null) {
      if (data.documents.length >= 100) throw new Error("草稿库已达100项上限，请先导出备份");
      if (typeof id !== "string" || !id || id.length > 100 || data.documents.some(item => item.id === id)) throw new Error("新草稿标识无效");
      document = { id, name: action.name.trim(), code: action.code, version: 1, updatedAt: now, archived: false, history: [] };
      data.documents.unshift(document);
    } else {
      if (!document || document.archived) throw new Error("该草稿已移除或不存在，请另存为副本");
      if (document.name !== action.name.trim() || document.code !== action.code) {
        if (!Number.isSafeInteger(document.version + 1)) throw new Error("脚本版本号超出范围");
        if (document.history.length >= 50) throw new Error("历史已达50个版本上限，请另存为副本；未删除旧版本");
        document.history.push({ version: document.version, name: document.name, code: document.code, savedAt: document.updatedAt });
        Object.assign(document, { name: action.name.trim(), code: action.code, version: document.version + 1, updatedAt: now });
      }
    }
    data.selectedId = document.id;
  } else if (action.type === "select") {
    if (!document || document.archived) throw new Error("该草稿不存在或已归档");
    data.selectedId = document.id;
  } else if (action.type === "archive" || action.type === "unarchive") {
    if (!document) throw new Error("该草稿不存在");
    document.archived = action.type === "archive";
    if (document.archived && data.selectedId === document.id) data.selectedId = null;
  } else if (action.type === "restore-version") {
    if (!document || document.archived) throw new Error("该草稿不存在或已归档");
    const version = document.history.find(item => item.version === action.version);
    if (!version) throw new Error("找不到所选历史版本");
    if (document.history.length >= 50) throw new Error("历史版本已满，请另存为副本");
    if (!Number.isSafeInteger(document.version + 1)) throw new Error("脚本版本号超出范围");
    document.history.push({ version: document.version, name: document.name, code: document.code, savedAt: document.updatedAt });
    Object.assign(document, { name: version.name, code: version.code, version: document.version + 1, updatedAt: now });
    data.selectedId = document.id;
  } else throw new Error("不支持的草稿操作");
  data.revision++;
  if (!Number.isSafeInteger(data.revision)) throw new Error("草稿修订号超出范围");
  const raw = JSON.stringify(data);
  if (raw.length > LIMIT) throw new Error("草稿库已达2MB限制，请先导出；原数据未改写");
  // Storage quota/access failures propagate. UI must retain the unsaved buffer.
  storage.setItem(SCRIPT_STORE_KEY, raw);
  return { raw, data };
}

export function parseScriptImport(text, filename = "导入指标") {
  if (typeof text !== "string" || text.length > 150000) throw new Error("导入文件过大");
  let name = filename.replace(/\.(aiscript|txt|json)$/i, "").slice(0, 80) || "导入指标";
  let code = text.replace(/^\uFEFF/, "");
  if (/\.json$/i.test(filename)) {
    let data;
    try { data = JSON.parse(code); } catch { throw new Error("脚本JSON无法解析"); }
    if (data?.format !== "ai-trading-script" || data.version !== 1 || !validName(data.name) || !validCode(data.code)) throw new Error("仅支持 ai-trading-script v1 格式，不自动导入未知结构");
    name = data.name; code = data.code;
  }
  if (!validName(name) || !validCode(code)) throw new Error("脚本名称或代码长度无效");
  return { name, code };
}

// Basic lexical checks only. No execution or claim of full AiScript compilation.
export function checkScriptText(code) {
  const diagnostics = [];
  if (!validCode(code)) return [{ severity: "error", line: 1, column: 1, message: "代码类型或长度无效" }];
  const stack = []; let line = 1, column = 0, quote = null, escaped = false, comment = null, content = false, start = null;
  const pairs = { ")": "(", "]": "[", "}": "{" };
  for (let i = 0; i < code.length; i++) {
    const char = code[i], next = code[i + 1]; column++;
    if (char === "\n") { line++; column = 0; if (comment === "line") comment = null; }
    if (comment === "line") continue;
    if (comment === "block") { if (char === "*" && next === "/") { comment = null; i++; column++; } continue; }
    if (quote) {
      if (escaped) { escaped = false; continue; }
      if (char === "\\") { escaped = true; continue; }
      if (char === quote) quote = null;
      else if (char === "\n") { diagnostics.push({ severity: "error", ...start, message: "字符串在换行前未闭合" }); quote = null; }
      continue;
    }
    if (char === "/" && next === "/") { comment = "line"; i++; column++; continue; }
    if (char === "/" && next === "*") { comment = "block"; start = { line, column }; i++; column++; continue; }
    if (char === '"' || char === "'") { quote = char; start = { line, column }; content = true; continue; }
    if ("([{ ".includes(char) && char !== " ") stack.push({ char, line, column });
    if (Object.hasOwn(pairs, char)) {
      if (stack.at(-1)?.char !== pairs[char]) diagnostics.push({ severity: "error", line, column, message: `括号 ${char} 缺少匹配的起始符` });
      else stack.pop();
    }
    if (!/\s/.test(char)) content = true;
  }
  if (quote) diagnostics.push({ severity: "error", ...start, message: "字符串未闭合" });
  if (comment === "block") diagnostics.push({ severity: "error", ...start, message: "多行注释未闭合" });
  stack.forEach(item => diagnostics.push({ severity: "error", line: item.line, column: item.column, message: `括号 ${item.char} 未闭合` }));
  if (!content) diagnostics.push({ severity: "warning", line: 1, column: 1, message: "尚无可检查的脚本语句" });
  if (!/^\s*\/\/\s*@version=\d+/m.test(code)) diagnostics.push({ severity: "warning", line: 1, column: 1, message: "未声明脚本版本" });
  return diagnostics.sort((a, b) => a.line - b.line || a.column - b.column);
}
