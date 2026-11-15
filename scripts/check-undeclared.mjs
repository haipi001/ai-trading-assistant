// Static guard against "used but never imported" identifiers.
// The interaction audit only scans strings, so a missing import (e.g. an icon
// library or a scope helper) reaches the browser and blanks the panel at render
// time. This walks the real AST instead.
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import parser from '@babel/parser';
import traverseModule from '@babel/traverse';

const traverse = traverseModule.default || traverseModule;
const root = path.resolve(fileURLToPath(new URL('..', import.meta.url)));

const GLOBALS = new Set([
  'console', 'window', 'document', 'localStorage', 'sessionStorage', 'setTimeout', 'clearTimeout',
  'setInterval', 'clearInterval', 'fetch', 'URL', 'Blob', 'File', 'FormData', 'Headers', 'Request',
  'Response', 'AbortController', 'AbortSignal', 'CustomEvent', 'Event', 'MutationObserver',
  'requestAnimationFrame', 'cancelAnimationFrame', 'crypto', 'Promise', 'Map', 'Set', 'WeakMap',
  'WeakSet', 'Symbol', 'JSON', 'Math', 'Date', 'Number', 'String', 'Boolean', 'Array', 'Object',
  'RegExp', 'Error', 'TypeError', 'RangeError', 'SyntaxError', 'Infinity', 'NaN', 'undefined',
  'parseInt', 'parseFloat', 'isNaN', 'isFinite', 'encodeURIComponent', 'decodeURIComponent',
  'encodeURI', 'decodeURI', 'Intl', 'structuredClone', 'queueMicrotask', 'performance',
  'navigator', 'location', 'history', 'parent', 'top', 'self', 'confirm', 'alert', 'prompt',
  'getComputedStyle', 'matchMedia', 'ResizeObserver', 'IntersectionObserver', 'TextEncoder',
  'TextDecoder', 'atob', 'btoa', 'globalThis', 'arguments', 'require', 'module', 'exports',
  'process', 'NodeFilter', 'Node', 'Element', 'HTMLElement', 'CustomElementRegistry',
  'URLSearchParams', 'BigInt', 'XMLSerializer', 'Image', 'WebSocket', 'EventSource',
  'SpeechSynthesisUtterance', 'speechSynthesis', 'Notification', 'Worker', 'SharedWorker',
  'BroadcastChannel', 'MessageChannel', 'MessagePort', 'DOMRect', 'DOMParser', 'FileReader',
  'AudioContext', 'OffscreenCanvas', 'Path2D', 'CanvasRenderingContext2D', 'Proxy', 'Reflect',
  'WeakRef', 'FinalizationRegistry', 'AggregateError', 'EvalError', 'URIError', 'ArrayBuffer',
  'Uint8Array', 'Uint16Array', 'Uint32Array', 'Int8Array', 'Int16Array', 'Int32Array',
  'Float32Array', 'Float64Array', 'DataView', 'SharedArrayBuffer', 'Atomics', 'Intl',
  'requestIdleCallback', 'cancelIdleCallback', 'scrollTo', 'open', 'close', 'focus', 'blur',
]);

function collect(dir, out = []) {
  for (const entry of fs.readdirSync(dir, {withFileTypes: true})) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (!/node_modules|\.git|__pycache__/.test(full)) collect(full, out);
    } else if (/\.(jsx?|mjs)$/.test(entry.name)) out.push(full);
  }
  return out;
}

function declaredNames(ast) {
  const declared = new Set();
  const addPattern = node => {
    if (!node) return;
    if (node.type === 'Identifier') declared.add(node.name);
    else if (node.type === 'ObjectPattern') for (const prop of node.properties) addPattern(prop.value ?? prop.argument ?? prop.key);
    else if (node.type === 'ArrayPattern') for (const element of node.elements) addPattern(element);
    else if (node.type === 'AssignmentPattern') addPattern(node.left);
    else if (node.type === 'RestElement') addPattern(node.argument);
  };
  traverse(ast, {
    ImportDeclaration(p) { for (const spec of p.node.specifiers) declared.add(spec.local.name); },
    ExportNamedDeclaration(p) { for (const spec of p.node.specifiers || []) if (spec.local?.name) declared.add(spec.local.name); if (p.node.declaration?.id?.name) declared.add(p.node.declaration.id.name); },
    VariableDeclarator(p) { addPattern(p.node.id); },
    FunctionDeclaration(p) { if (p.node.id) declared.add(p.node.id.name); },
    FunctionExpression(p) { if (p.node.id) declared.add(p.node.id.name); },
    ClassDeclaration(p) { if (p.node.id) declared.add(p.node.id.name); },
    CatchClause(p) { addPattern(p.node.param); },
    // Any function or block scope parameter counts as declared for this guard.
    'Function|Program'(p) { for (const param of p.node.params || []) addPattern(param); },
  });
  return declared;
}

function usedNames(ast) {
  const used = new Map();
  const note = (name, line) => { if (!used.has(name)) used.set(name, line); };
  traverse(ast, {
    Identifier(p) {
      if (!p.isReferencedIdentifier()) return;
      const parent = p.parent;
      if (parent.type === 'MemberExpression' && parent.property === p.node && !parent.computed) return;
      if (parent.type === 'ObjectProperty' && parent.key === p.node && !parent.computed) return;
      note(p.node.name, p.node.loc?.start.line ?? 0);
    },
    JSXIdentifier(p) {
      const parent = p.parent;
      const isElement = (parent.type === 'JSXOpeningElement' || parent.type === 'JSXClosingElement') && parent.name === p.node;
      if (isElement && /^[A-Z]/.test(p.node.name)) note(p.node.name, p.node.loc?.start.line ?? 0);
    },
  });
  return used;
}

const files = collect(path.join(root, 'src'));
const problems = [];
for (const file of files) {
  let ast;
  try {
    ast = parser.parse(fs.readFileSync(file, 'utf8'), {sourceType: 'module', plugins: ['jsx']});
  } catch (error) {
    problems.push({file, name: 'PARSE_ERROR', line: 0, detail: error.message});
    continue;
  }
  const declared = declaredNames(ast);
  for (const [name, line] of usedNames(ast)) {
    if (declared.has(name) || GLOBALS.has(name)) continue;
    if (!/^[A-Za-z_$][\w$]*$/.test(name)) continue;
    problems.push({file: path.relative(root, file), name, line});
  }
}

if (problems.length === 0) {
  console.log(`No undeclared identifiers in ${files.length} source files.`);
} else {
  for (const row of problems) {
    console.log(`${row.file}:${row.line}  ${row.name}${row.detail ? `  (${row.detail})` : ''}`);
  }
  console.log(`\n${problems.length} undeclared identifier(s) across ${new Set(problems.map(r => r.file)).size} file(s).`);
  process.exitCode = 1;
}
