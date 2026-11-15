import assert from 'node:assert/strict';
import {candleAgeLabel} from '../src/candle-age-label.js';
const time=Date.parse('2026-06-18T13:30:00Z')/1000;
assert.match(candleAgeLabel({time},Date.parse('2026-11-15T13:30:00Z')),/2026-06-18 13:30:00 UTC · 距今150天/);
assert.match(candleAgeLabel({time},time*1000),/快照不保证实时/);
assert.equal(candleAgeLabel(null),'');assert.equal(candleAgeLabel({time:NaN}),'');
console.log('PASS candle age shows UTC bar start independently of fetch time');
