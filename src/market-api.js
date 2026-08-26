import { apiRequest } from "./backend-api.js";

export async function loadBackendCandles(symbol, timeframe = "1d") {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 12000);
  try {
    const assets = await apiRequest("/assets?limit=1000", { signal: controller.signal });
    const normalized = symbol.replace("/USDT", "").toUpperCase();
    const asset = assets.find((item) => item.symbol?.replace("-USD", "").replace("USDT", "").toUpperCase() === normalized);
    if (!asset) return { status: "missing", candles: [], source: "后端暂无该标的" };
    const rows = await apiRequest(`/candles?asset_id=${encodeURIComponent(asset.id)}&timeframe=${encodeURIComponent(timeframe)}&limit=240`, { signal: controller.signal });
    return {
      status: rows.length ? "connected" : "empty",
      source: rows[0]?.source || "ai-trading-os",
      asset,
      candles: rows.slice().reverse().map((row) => ({
        time: Math.floor(new Date(row.timestamp).getTime() / 1000),
        open: Number(row.open), high: Number(row.high), low: Number(row.low), close: Number(row.close), volume: Number(row.volume || 0),
      })),
    };
  } catch (error) {
    return { status: "offline", candles: [], source: error.name === "AbortError" ? "后端响应超时" : "后端未连接" };
  } finally { clearTimeout(timer); }
}
