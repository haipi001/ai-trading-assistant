import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { parse, parseExpression } from '@babel/parser';
import generator from '@babel/generator';
const generate = generator.default || generator;
const baseline = JSON.parse(readFileSync(new URL('../docs/planning/r127-master-2026-11-01/tasks/ui-control-inventory.json', import.meta.url), 'utf8'));
const canonical = expression => generate(expression, { compact: true, comments: false }).code;
const found = {};
const counts = {};
const expected = {};
for (const c of baseline.controls) {
  const key = `${c.file}:${c.tag}`;
  expected[key] = (expected[key] || 0) + 1;
}
function walk(node, file) {
  if (!node || typeof node !== 'object') return;
  if (node.type === 'VariableDeclarator' && baseline.navigation[node.id?.name]) found[node.id.name] = canonical(node.init);
  if (node.type === 'JSXOpeningElement') {
    const key = `${file}:${node.name?.name}`;
    counts[key] = (counts[key] || 0) + 1;
  }
  for (const [key, value] of Object.entries(node)) {
    if (['loc', 'start', 'end', 'comments', 'tokens'].includes(key)) continue;
    if (Array.isArray(value)) value.forEach(n => walk(n, file));
    else if (value && typeof value === 'object') walk(value, file);
  }
}
const files = new Set([...baseline.controls.map(c => c.file), ...Object.values(baseline.navigation).map(n => n.file)]);
for (const file of files) walk(parse(readFileSync(new URL(`../${file}`, import.meta.url), 'utf8'), { sourceType: 'module', plugins: ['jsx'] }), file);
for (const [name, nav] of Object.entries(baseline.navigation)) {
  assert.equal(found[name], canonical(parseExpression(nav.source)), `${name} changed: review all navigation/strategy entries before updating baseline`);
}
for (const [key, count] of Object.entries(expected)) {
  assert.ok(counts[key] >= count, `${key}: ${counts[key] || 0} < baseline ${count}; review relocation/removal before updating baseline`);
}
console.log(`UI preservation static guard: ${Object.keys(baseline.navigation).length} navigation contracts, ${baseline.controls.length} controls retained. Runtime behavior not verified.`);
