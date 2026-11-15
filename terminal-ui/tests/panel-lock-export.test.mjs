import {test} from 'node:test';
import assert from 'node:assert/strict';

// Mirrors the export filter in panel-host.mjs. Tool-drawer keys and tab instance
// UUIDs live in the in-memory lock map but cannot appear in a saved workspace,
// so exporting them made every market switch throw invalid_workspace_lock.
const LOCK_KEY=/^(main|[0-3]):[A-Z][A-Z0-9_]{0,31}$/;
const exported=entries=>[...entries].filter(([key])=>LOCK_KEY.test(key)).map(([key,context])=>({key,context}));

test('slot keys are exportable',()=>{
 assert.deepEqual(exported([['main:R009',{}]]).map(row=>row.key),['main:R009']);
 assert.deepEqual(exported([['0:R042',{}],['3:HELP',{}]]).map(row=>row.key),['0:R042','3:HELP']);
});

test('tool drawer and tab instance keys never reach the snapshot',()=>{
 const rows=exported([
  ['main:R009',{market:'cex'}],
  ['global-tool-drawer:ai',{market:'cex'}],
  ['global-tool-drawer:trade',{market:'cex'}],
  ['3f2a6c10-1111-2222-3333-444455556666',{market:'stocks'}],
 ]);
 assert.deepEqual(rows.map(row=>row.key),['main:R009']);
 assert.equal(rows.length,1);
});

test('a drawer-only lock set exports as empty rather than failing the switch',()=>{
 assert.deepEqual(exported([['global-tool-drawer:ai',{}]]),[]);
 assert.deepEqual(exported([]),[]);
});

test('lowercase or overlong codes stay out of the snapshot',()=>{
 assert.deepEqual(exported([['main:help',{}],['main:'+('A'.repeat(33)),{}]]),[]);
});
