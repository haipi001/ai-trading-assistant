import assert from "node:assert/strict";
import { analyseSeries, compileFormula, normaliseBars, parseCandleCsv } from "../src/chart-analysis.js";
const a = [{ time: 100, close: 10 }, { time: 200, close: 20 }, { time: 300, close: 30 }, { time: 400, close: 40 }];
const b = [{ time: 200, close: 5 }, { time: 300, close: 10 }, { time: 400, close: 20 }, { time: 500, close: 30 }];
const legs = [{ label: "A", rows: a }, { label: "B", rows: b }];
const percent = analyseSeries(legs);
assert.deepEqual(percent.series[0].rows, [{ time: 200, value: 0 }, { time: 300, value: 50 }, { time: 400, value: 100 }]);
assert.deepEqual(percent.series[1].rows, [{ time: 200, value: 0 }, { time: 300, value: 100 }, { time: 400, value: 300 }]);
assert.deepEqual(percent.coverage, [{ input: 4, matched: 3, excluded: 1 }, { input: 4, matched: 3, excluded: 1 }]);
assert.deepEqual(analyseSeries(legs, { mode: "price" }).series[0].rows.map(row => row.value), [20, 30, 40]);
assert.deepEqual(analyseSeries(legs, { mode: "formula", formula: "A-B" }).series[0].rows.map(row => row.value), [15, 20, 20]);
assert.deepEqual(analyseSeries(legs, { mode: "formula", formula: "(A-B)/B*100" }).series[0].rows.map(row => row.value), [300, 200, 100]);
assert.equal(compileFormula("-A + B * (2 + .5)", ["A", "B"])({ A: 10, B: 8 }), 10);
assert.equal(compileFormula("A/B/2", ["A", "B"])({ A: 20, B: 5 }), 2);
for (const formula of ["", "A+C", "A.toString()", "globalThis.alert(1)", "A;B", "A**2", "A B", "(A+B", "A+", "1e5", "[A]", "Math.max(A,B)"]) assert.throws(() => compileFormula(formula, ["A", "B"]));
assert.throws(() => compileFormula("A/(B-B)", ["A", "B"])({ A: 1, B: 2 }), /分母/);
assert.throws(() => compileFormula("(".repeat(34) + "A" + ")".repeat(34), ["A"]), /嵌套/);
assert.throws(() => compileFormula("9".repeat(199) + "*A", ["A"]), /最长/);
assert.throws(() => compileFormula("9999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999*A", ["A"])({ A: 1e300 }), /有限/);
assert.throws(() => analyseSeries([{ rows: a }, { rows: [{ time: 500, close: 1 }] }]), /共同时间/);
assert.throws(() => analyseSeries([{ rows: a }, { rows: [{ time: 100, close: 0 }, { time: 200, close: 1 }] }]), /起点价格/);
assert.throws(() => analyseSeries(legs, { field: "high" }), /价格无效/);
assert.throws(() => normaliseBars([{ time: 100, close: true }]), /无效/);
assert.throws(() => normaliseBars([{ time: true, close: 1 }]), /无效/);
assert.throws(() => normaliseBars([{ time: 100, close: "0x20" }]), /无效/);
assert.throws(() => normaliseBars([{ time: 100, close: 1 }, { time: 100, close: 2 }]), /重复/);
assert.throws(() => normaliseBars([{ time: 100, close: NaN }]), /无效/);
const imported = parseCandleCsv('\uFEFFdate,open,high,low,close,note\r\n2026-01-02,2,3,1,2.5,"test, comma"\r\n2026-01-01,1,2,0.5,1.5,"test ""quote"""');
assert.equal(imported[0].close, 1.5);
assert.ok(imported[0].time < imported[1].time);
assert.deepEqual(parseCandleCsv("time,close\n1700000000000,5\n1700000060000,6").map(row => row.time), [1700000000, 1700000060]);
assert.equal(parseCandleCsv("timestamp,close\n2026-01-01T08:00:00+08:00,10")[0].time, Date.parse("2026-01-01T00:00:00Z") / 1000);
for (const csv of [
  "time,close\n2026-02-30,1", "time,close\n2026-01-01T24:00:00Z,1", "time,close\n2026-01-01T12:00:00,1", "time,close\n100,", "time,close\n100,NaN",
  "time,close\n100,-2", "time,close\n100,1\n100,2", "time,close\n100,1,extra", "time,close\n100,\"1", "time,close\n100,\"1\"junk",
  "time,close,close\n100,1,1", "time,timestamp,close\n100,100,1", "time,open\n100,1", "time,close\n100,=1+1",
  "time,open,high,low,close\n100,2,1,3,2", "time,close\n100,0x20",
]) assert.throws(() => parseCandleCsv(csv), `Must reject malformed CSV: ${csv}`);
assert.equal(a[0].close, 10); // Analysis did not rewrite imported prices.
console.log("Chart analysis: time alignment, shared baselines, price/formula arithmetic, zero/overflow, strict CSV and non-executable formula checks passed.");
