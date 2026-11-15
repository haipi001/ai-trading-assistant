// Every tool id the rail can emit must have somewhere to render.
// A missing branch is invisible in tests but shows as a blank or error panel,
// which is exactly how 本机笔记 / 风险计算器 went unnoticed.
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const root = path.resolve(fileURLToPath(new URL('..', import.meta.url)));
const read = rel => fs.readFileSync(path.join(root, rel), 'utf8');

const catalog = read('terminal-ui/integration/tool-catalog.mjs');
const catalogIds = [...catalog.matchAll(/id:\s*'([a-zA-Z]+)'/g)].map(m => m[1]);

const main = read('src/main.jsx');

// Ids accepted by the terminal:tool listener. Anything absent is dropped silently.
const allowMatch = main.match(/if \(!\[([^\]]+)\]\.includes\(id\)\) return;/);
const allowed = allowMatch ? [...allowMatch[1].matchAll(/'([a-zA-Z]+)'/g)].map(m => m[1]) : [];

// Ids accepted as a saved market side tab.
const sideMatch = main.match(/const MARKET_SIDE_TABS = \[([^\]]+)\]/);
const sideTabs = sideMatch ? [...sideMatch[1].matchAll(/"([a-zA-Z]+)"/g)].map(m => m[1]) : [];

// RailPanel render branches, plus the ids handled before RailPanel is reached.
const branchIds = [...main.matchAll(/type === "([a-zA-Z]+)"/g)].map(m => m[1]);
const knownMatch = main.match(/const knownTypes = \[([^\]]+)\]/);
const knownTypes = knownMatch ? [...knownMatch[1].matchAll(/"([a-zA-Z]+)"/g)].map(m => m[1]) : [];

const problems = [];

if (!allowMatch) problems.push('无法解析 terminal:tool 白名单');
if (!sideMatch) problems.push('无法解析 MARKET_SIDE_TABS');
if (!knownMatch) problems.push('无法解析 knownTypes');

// Handled before RailPanel is reached, so they never need a side-tab entry
// or a RailPanel branch.
const PRE_RAIL = ['research', 'help', 'sidebarLayout'];

for (const id of catalogIds) {
  if (!allowed.includes(id)) problems.push(`工具目录 id "${id}" 不在 terminal:tool 白名单中，点击会被丢弃`);
  if (PRE_RAIL.includes(id) || id.endsWith('Settings')) continue;
  if (!sideTabs.includes(id)) problems.push(`工具目录 id "${id}" 不在 MARKET_SIDE_TABS 中，保存后会被重置`);
  if (!branchIds.includes(id) && !knownTypes.includes(id)) {
    problems.push(`工具目录 id "${id}" 没有任何渲染分支`);
  }
}

// A known type without a branch falls through to the final default return,
// which used to silently show the ETF view.
for (const id of knownTypes) {
  if (PRE_RAIL.includes(id)) continue;
  if (!branchIds.includes(id)) problems.push(`knownTypes 中的 "${id}" 没有对应的显式渲染分支`);
}

// Duplicates in any list mean one of them is dead weight.
for (const [label, list] of [['terminal:tool 白名单', allowed], ['MARKET_SIDE_TABS', sideTabs], ['knownTypes', knownTypes]]) {
  const seen = new Set();
  for (const id of list) {
    if (seen.has(id)) problems.push(`${label} 中 "${id}" 重复`);
    seen.add(id);
  }
}

if (problems.length === 0) {
  console.log(`Rail panels OK: ${catalogIds.length} catalog ids all route to a renderer.`);
} else {
  for (const line of problems) console.log(line);
  console.log(`\n${problems.length} rail routing problem(s).`);
  process.exitCode = 1;
}
