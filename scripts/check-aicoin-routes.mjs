import assert from "node:assert/strict";
import fs from "node:fs";
import { AICOIN_ROUTES, getAicoinRouteLabel, resolveAicoinRoute } from "../src/aicoin-routes.js";
import { AICOIN_PATHS, AICOIN_LABELS } from "../src/aicoin-navigation.generated.js";

const app = fs.readFileSync(new URL("../src/main.jsx", import.meta.url), "utf8");
for (const [route, target] of Object.entries(AICOIN_ROUTES)) {
  assert.deepEqual(resolveAicoinRoute(`#${route}`), target);
  assert.ok(app.includes(`\"${target.tab}\"`), `Missing destination tab: ${route}`);
  const result = resolveAicoinRoute(`#${route}`);
  result.page = "invalid";
  assert.notEqual(resolveAicoinRoute(`#${route}`).page, "invalid");
}
// Recovered module 99719 names EXCHANGE=行情, INFO=要闻, NEWS=快讯.
assert.deepEqual(resolveAicoinRoute("#/main/exchange"), { page: "market", tab: "图表" });
assert.deepEqual(resolveAicoinRoute("#/main/info"), { page: "news", tab: "精选" });
assert.deepEqual(resolveAicoinRoute("#/main/news"), { page: "flash", tab: "精选" });
assert.deepEqual(resolveAicoinRoute("#/chart/multiline"), { page: "market", tab: "图表", chartMode: "compare" });
assert.deepEqual(resolveAicoinRoute("#/chart/spread"), { page: "market", tab: "图表", chartMode: "spread" });
assert.deepEqual(resolveAicoinRoute("#/script-window"), { page: "market", tab: "图表", marketPanel: "自定义指标/回测/实盘", indicatorSection: "指标编辑" });
assert.equal(AICOIN_LABELS[AICOIN_PATHS.EXCHANGE], "行情");
assert.equal(getAicoinRouteLabel("#/chart/proBacktest"), "专业回测");
assert.equal(getAicoinRouteLabel("#/__proto__"), null);
for (const [query, panel, section] of [
  ["fundPanel=editor", "自定义指标/回测/实盘", "指标编辑"],
  ["fundPanel=editor&tab=backtest", "自定义指标/回测/实盘", "策略回测"],
  ["fundPanel=grid", "AI网格", undefined], ["fundPanel=dca", "现货DCA", undefined],
]) {
  const target = resolveAicoinRoute(`#/main/exchange?${query}`);
  assert.equal(target.page, "market");
  assert.equal(target.marketPanel, panel);
  assert.equal(target.indicatorSection, section);
}
for (const query of ["fundPanel=constructor", "fundPanel=__proto__", "fundPanel=grid&fundPanel=dca", "fundPanel=editor&tab=start", "fundPanel=editor&scriptId=12", "fundPanel=dca&tab=backtest", "account=1", "fundPanel=grid?x"]) assert.equal(resolveAicoinRoute(`#/main/exchange?${query}`), null);
for (const route of ["", "https://aicoin.com/main/info", "#/script-window?scriptId=unknown", "#/order", "#/main/info?tab=0", "#/main/info/unknown", "#/__proto__"]) {
  assert.equal(resolveAicoinRoute(route), null, `Unexpected supported route: ${route}`);
}
const inventory = new URL("../reference/aicoin/literal-index.json", import.meta.url);
if (fs.existsSync(inventory)) {
  const paths = new Set(JSON.parse(fs.readFileSync(inventory, "utf8")).routes.map(route => route.path));
  for (const route of Object.keys(AICOIN_ROUTES)) assert.ok(paths.has(route), `Route not observed in artifact: ${route}`);
}
console.log(`Verified ${Object.keys(AICOIN_ROUTES).length} base navigation mappings and 4 workbench queries; unsupported parameters remain rejected.`);
