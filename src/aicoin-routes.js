import { AICOIN_PATHS as P, AICOIN_LABELS } from "./aicoin-navigation.generated.js";

// Explicit navigation equivalents, not a claim of complete feature parity.
// Paths were observed as literals in the installed AiCoin 2.16.28 renderer.
export const AICOIN_ROUTES = Object.freeze({
  [P.HOME]: { page: "home", tab: "AI智搜" },
  [P.HOMEPAGE]: { page: "home", tab: "AI智搜" },
  [P.EXCHANGE]: { page: "market", tab: "图表" },
  [P.INFO]: { page: "news", tab: "精选" },
  "/chart": { page: "market", tab: "图表" },
  [P.CHART_COMMON]: { page: "market", tab: "图表" },
  [P.CHART_NEW_COMMON]: { page: "market", tab: "图表" },
  [P.CHART_MULTILINE]: { page: "market", tab: "图表", chartMode: "compare" },
  [P.CHART_SPREAD]: { page: "market", tab: "图表", chartMode: "spread" },
  [P.SCRIPT_WINDOW]: { page: "market", tab: "图表", marketPanel: "自定义指标/回测/实盘", indicatorSection: "指标编辑" },
  [P.NEWS]: { page: "flash", tab: "精选" },
  [P.FLASH]: { page: "flash", tab: "精选" },
  [P.ASSET]: { page: "assets", tab: "总览" },
  [P.AUTH]: { page: "auth", tab: "已授权账户" },
  [P.DATA]: { page: "data", tab: "加密货币储备" },
  [P.DATA_CRYPTO_RESERVES]: { page: "data", tab: "加密货币储备" },
  [P.DATA_HYPERLIQUID]: { page: "data", tab: "Hyperliquid" },
  [P.WALLET]: { page: "more", tab: "钱包" },
  [P.DEX]: { page: "chain", tab: "聪明钱" },
  [P.TRADING_BOT]: { page: "strategy", tab: "自动赚币", strategyCategory: 1 },
  [P.FOLLOW]: { page: "strategy", tab: "自动赚币", strategyCategory: 5 },
  [P.COPY_TRADE]: { page: "strategy", tab: "自动赚币", strategyCategory: 5 },
});

export function resolveAicoinRoute(hash) {
  if (typeof hash !== "string" || !hash.startsWith("#/")) return null;
  const route = hash.slice(1);
  if (route.includes("?")) {
    const [pathname, query] = route.split("?");
    if (pathname !== P.EXCHANGE || route.split("?").length !== 2) return null;
    const params = new URLSearchParams(query);
    if ([...params.keys()].some(key => !["fundPanel", "tab"].includes(key) || params.getAll(key).length !== 1)) return null;
    const panels = { editor: "自定义指标/回测/实盘", grid: "AI网格", dca: "现货DCA" };
    if (!Object.hasOwn(panels, params.get("fundPanel"))) return null;
    const panel = panels[params.get("fundPanel")];
    if (params.has("tab") && !(params.get("fundPanel") === "editor" && params.get("tab") === "backtest")) return null;
    return { ...AICOIN_ROUTES[P.EXCHANGE], marketPanel: panel,
      ...(params.get("fundPanel") === "editor" ? { indicatorSection: params.get("tab") === "backtest" ? "策略回测" : "指标编辑" } : {}) };
  }
  // Account, order, credential and unsupported query semantics stay explicit.
  const target = Object.hasOwn(AICOIN_ROUTES, route) ? AICOIN_ROUTES[route] : null;
  return target ? { ...target } : null;
}

export function getAicoinRouteLabel(hash) {
  if (typeof hash !== "string" || !hash.startsWith("#/")) return null;
  const path = hash.slice(1).split("?")[0];
  return Object.hasOwn(AICOIN_LABELS, path) ? AICOIN_LABELS[path] : null;
}

export function clearAicoinRoute() {
  if (window.location.hash.startsWith("#/")) window.history.replaceState(null, "", window.location.pathname + window.location.search);
}
