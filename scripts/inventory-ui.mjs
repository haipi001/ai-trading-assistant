import { readdirSync, readFileSync, mkdirSync, writeFileSync } from 'node:fs';
import { parse } from '@babel/parser';
import { relative, resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

// Static inventory only: handlers are evidence of wiring, never proof of business success.
const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const output = process.argv[2];
if (!output) throw new Error('Usage: node scripts/inventory-ui.mjs <output.json>');
const files = readdirSync(resolve(root, 'src'), { recursive: true })
  .filter(name => /\.(jsx|js)$/.test(name)).sort();
const controls = [];
const navigation = {};
function visit(node, file, source) {
  if (!node || typeof node !== 'object') return;
  if (node.type === 'VariableDeclarator' && ['NAV', 'META', 'STRATEGY_CATEGORY_LABELS'].includes(node.id?.name)) {
    navigation[node.id.name] = { file, line: node.loc.start.line, source: source.slice(node.init.start, node.init.end) };
  }
  if (node.type === 'JSXOpeningElement') {
    const tag = node.name?.name;
    if (['button', 'input', 'select', 'textarea', 'dialog'].includes(tag)) {
      const attributes = Object.fromEntries(node.attributes.filter(a => a.type === 'JSXAttribute').map(a => [a.name.name, a]));
      const text = name => {
        const v = attributes[name]?.value;
        return v?.type === 'StringLiteral' ? v.value : v?.expression ? source.slice(v.expression.start, v.expression.end) : null;
      };
      controls.push({ id: `${file}:${node.loc.start.line}:${node.loc.start.column}`, file, line: node.loc.start.line,
        tag, label: text('aria-label') || text('title') || text('placeholder'),
        handlers: Object.keys(attributes).filter(k => /^on[A-Z]/.test(k)),
        disabled: attributes.disabled ? source.slice(attributes.disabled.start, attributes.disabled.end) : null,
        runtimeStatus: 'NOT_RETESTED', journey: null, api: null, dataMode: 'NOT_AUDITED', evidence: null });
    }
  }
  for (const [key, value] of Object.entries(node)) {
    if (['loc', 'start', 'end', 'comments', 'tokens'].includes(key)) continue;
    if (Array.isArray(value)) value.forEach(v => visit(v, file, source));
    else if (value && typeof value === 'object') visit(value, file, source);
  }
}
for (const name of files) {
  const file = `src/${name}`;
  const source = readFileSync(resolve(root, file), 'utf8');
  visit(parse(source, { sourceType: 'module', plugins: ['jsx'] }), file, source);
}
const report = { scope: 'Static JSX controls across all src JavaScript/JSX; dynamic components need runtime expansion',
  proofLevel: 'STATIC', filesScanned: files.length, navigation, controls };
const target = resolve(root, output);
mkdirSync(resolve(target, '..'), { recursive: true });
writeFileSync(target, JSON.stringify(report, null, 2) + '\n');
console.log(`${relative(root, target)}: ${files.length} files, ${controls.length} static controls; runtime unverified`);
