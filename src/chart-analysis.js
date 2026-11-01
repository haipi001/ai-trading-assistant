// Close/selected-field line analysis over aligned bars, not synthetic OHLC.
export const PRICE_FIELDS = ["open", "high", "low", "close"];

export function normaliseBars(rows, field = "close") {
  if (!PRICE_FIELDS.includes(field) || !Array.isArray(rows) || !rows.length) throw new Error("缺少可计算的价格数据");
  const seen = new Set();
  return rows.map((row, index) => {
    const time = Number(row.time);
    const raw = row[field];
    const value = Number(raw);
    const numeric = /^(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i;
    if (!["number", "string"].includes(typeof row.time) || (typeof row.time === "string" && !/^\d+$/.test(row.time.trim())) || !Number.isSafeInteger(time) || time <= 0 || time > 253402300799 || !["number", "string"].includes(typeof raw) || (typeof raw === "string" && !numeric.test(raw.trim())) || !Number.isFinite(value) || value < 0) throw new Error(`第 ${index + 1} 行的时间或${field}价格无效`);
    if (seen.has(time)) throw new Error("存在重复时间戳，请先核对数据");
    seen.add(time);
    return { time, value };
  }).sort((a, b) => a.time - b.time);
}

function csvRows(text) {
  const rows = []; let row = [], cell = "", quoted = false, closed = false;
  text = text.replace(/^\uFEFF/, "");
  for (let i = 0; i <= text.length; i++) {
    const char = text[i];
    if (quoted) {
      if (char === undefined) throw new Error("CSV 引号未闭合");
      if (char === '"') {
        if (text[i + 1] === '"') { cell += '"'; i++; }
        else { quoted = false; closed = true; }
      } else cell += char;
    } else if (char === '"') {
      if (cell || closed) throw new Error("CSV 引号位置无效");
      quoted = true;
    } else if (char === "," || char === "\n" || char === "\r" || char === undefined) {
      row.push(cell); cell = ""; closed = false;
      if (char !== ",") {
        if (row.some(value => value.trim())) rows.push(row);
        row = [];
        if (char === "\r" && text[i + 1] === "\n") i++;
      }
    } else {
      if (closed && !/\s/.test(char)) throw new Error("CSV 引号后存在多余字符");
      if (!closed) cell += char;
    }
  }
  return rows;
}

export function parseChartTimestamp(value) {
  value = value.trim();
  if (/^\d+$/.test(value)) {
    const numeric = Number(value);
    const seconds = numeric >= 1e12 ? numeric / 1000 : numeric;
    if (!Number.isSafeInteger(seconds) || seconds <= 0 || seconds > 253402300799) throw new Error("时间戳须为整秒 Unix 秒或毫秒");
    return seconds;
  }
  if (!/^\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2}))?$/.test(value)) throw new Error("日期须使用 YYYY-MM-DD 或带时区的 ISO 时间");
  if (value.includes("T") && (Number(value.slice(11, 13)) > 23 || Number(value.slice(14, 16)) > 59 || Number(value.slice(17, 19)) > 59)) throw new Error("时间不存在");
  const time = Date.parse(value);
  if (!Number.isFinite(time) || time <= 0 || time % 1000) throw new Error("日期无效或不在整秒上");
  // Date.parse normalises e.g. February 30: reject those calendar dates.
  const [year, month, day] = value.slice(0, 10).split("-").map(Number);
  if (month < 1 || month > 12 || day < 1 || day > new Date(Date.UTC(year, month, 0)).getUTCDate()) throw new Error("日期不存在");
  return time / 1000;
}

export function parseCandleCsv(text) {
  if (text.length > 1024 * 1024) throw new Error("CSV 最大支持 1 MB");
  const rows = csvRows(text);
  const header = rows.shift()?.map(value => value.trim().toLowerCase());
  if (!header || new Set(header).size !== header.length) throw new Error("CSV 表头缺失或重复");
  const timeIndex = header.findIndex(value => ["time", "timestamp", "date"].includes(value));
  if (header.filter(value => ["time", "timestamp", "date"].includes(value)).length > 1) throw new Error("CSV 只能有一列时间，避免混用不同时间口径");
  if (timeIndex < 0 || !header.includes("close")) throw new Error("CSV 至少需要 time（或 timestamp/date）和 close 列");
  if (!rows.length || rows.length > 10000) throw new Error("CSV 需要 1–10,000 行价格数据");
  const result = rows.map((values, index) => {
    if (values.length !== header.length) throw new Error(`CSV 第 ${index + 2} 行列数不一致`);
    const bar = { time: parseChartTimestamp(values[timeIndex]) };
    for (const field of PRICE_FIELDS) {
      const column = header.indexOf(field);
      if (column < 0) continue;
      const value = values[column].trim();
      if (!/^(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i.test(value) || !Number.isFinite(Number(value))) throw new Error(`CSV 第 ${index + 2} 行 ${field} 价格无效`);
      bar[field] = Number(value);
    }
    if(header.includes("volume")){const value=values[header.indexOf("volume")].trim();if(!/^(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i.test(value)||!Number.isFinite(Number(value)))throw new Error(`CSV 第${index+2}行volume无效`);bar.volume=Number(value);}
    if (["open", "high", "low", "close"].every(field => Object.hasOwn(bar, field)) && (bar.high < Math.max(bar.open, bar.close, bar.low) || bar.low > Math.min(bar.open, bar.close))) throw new Error(`CSV 第 ${index + 2} 行高低价关系无效`);
    return bar;
  });
  normaliseBars(result);
  return result.sort((a, b) => a.time - b.time);
}

export function compileFormula(expression, variables) {
  if (typeof expression !== "string" || expression.length > 200) throw new Error("公式最长 200 字符");
  const tokens = expression.match(/(?:\d+(?:\.\d*)?|\.\d+)|[A-J]|[()+\-*/]|\s+|./g)?.filter(token => !/^\s+$/.test(token)) || [];
  let index = 0;
  function atom(depth) {
    if (depth > 32) throw new Error("公式嵌套过深");
    const token = tokens[index++];
    if (token === "+" || token === "-") return { op: token === "-" ? "neg" : "pos", value: atom(depth + 1) };
    if (token === "(") { const value = sum(depth + 1); if (tokens[index++] !== ")") throw new Error("公式括号未配对"); return value; }
    if (/^(?:\d+(?:\.\d*)?|\.\d+)$/.test(token || "")) return { number: Number(token) };
    if (variables.includes(token)) return { variable: token };
    throw new Error("公式仅支持已选 A–J、数字、括号及 + − × ÷");
  }
  function product(depth) {
    let value = atom(depth);
    while (["*", "/"].includes(tokens[index])) { const op = tokens[index++]; value = { op, left: value, right: atom(depth) }; }
    return value;
  }
  function sum(depth) {
    let value = product(depth);
    while (["+", "-"].includes(tokens[index])) { const op = tokens[index++]; value = { op, left: value, right: product(depth) }; }
    return value;
  }
  const ast = sum(0);
  if (index !== tokens.length) throw new Error("公式包含无法解析的内容");
  return values => {
    function evaluate(node) {
      if (Object.hasOwn(node, "number")) return node.number;
      if (node.variable) return values[node.variable];
      if (node.op === "neg") return -evaluate(node.value);
      if (node.op === "pos") return evaluate(node.value);
      const left = evaluate(node.left), right = evaluate(node.right);
      if (node.op === "/" && right === 0) throw new Error("公式分母为零，无法计算");
      return { "+": () => left + right, "-": () => left - right, "*": () => left * right, "/": () => left / right }[node.op]();
    }
    const result = evaluate(ast);
    if (!Number.isFinite(result)) throw new Error("公式结果超出有限数值范围");
    return result;
  };
}

export function analyseSeries(legs, { field = "close", mode = "percent", formula = "A-B" } = {}) {
  if (!Array.isArray(legs) || legs.length < 2 || legs.length > 10) throw new Error("请选择 2–10 个对比项");
  const series = legs.map(leg => normaliseBars(leg.rows, field));
  const maps = series.map(rows => new Map(rows.map(row => [row.time, row.value])));
  const times = series[0].map(row => row.time).filter(time => maps.every(map => map.has(time)));
  if (times.length < 2) throw new Error("至少需要两个共同时间点；不会补齐缺失数据");
  const variables = legs.map((_, i) => String.fromCharCode(65 + i));
  const coverage = series.map(rows => ({ input: rows.length, matched: times.length, excluded: rows.length - times.length }));
  if (mode === "formula") {
    const calculate = compileFormula(formula, variables);
    return { coverage, series: [{ label: formula, rows: times.map(time => ({ time, value: calculate(Object.fromEntries(maps.map((map, i) => [variables[i], map.get(time)]))) })) }] };
  }
  if (!["percent", "price"].includes(mode)) throw new Error("未知对比方式");
  return { coverage, series: maps.map((map, index) => {
    const base = map.get(times[0]);
    if (mode === "percent" && base === 0) throw new Error("共同起点价格为零，无法归一化");
    return { label: legs[index].label || variables[index], rows: times.map(time => {
      const value = mode === "percent" ? (map.get(time) / base - 1) * 100 : map.get(time);
      if (!Number.isFinite(value)) throw new Error("对比结果超出有限数值范围");
      return { time, value };
    }) };
  }) };
}
