const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

async function getJson(path, signal) {
  const response = await fetch(`${API_BASE}${path}`, { signal, credentials: "include" });
  if (!response.ok) throw new Error(`API ${response.status}`);
  return response.json();
}

export async function loadBackendCandles(symbol, timeframe = "1d") {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 3500);
  try {
    const assets = await getJson("/assets?limit=1000", controller.signal);
    const normalized = symbol.replace("/USDT", "").toUpperCase();
    const asset = assets.find((item) => item.symbol?.replace("-USD", "").replace("USDT", "").toUpperCase() === normalized);
    if (!asset) return { status: "missing", candles: [], source: "后端暂无该标的" };
    const rows = await getJson(`/candles?asset_id=${encodeURIComponent(asset.id)}&timeframe=${encodeURIComponent(timeframe)}&limit=240`, controller.signal);
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

