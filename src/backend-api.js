export const API_BASE = (import.meta.env.VITE_API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");

export async function apiRequest(path, options = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), options.timeout || 6000);
  try {
    const response = await fetch(`${API_BASE}${path}`, {
      method: options.method || "GET",
      credentials: "include",
      headers: { "Content-Type": "application/json", ...options.headers },
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: options.signal || controller.signal,
    });
    if (!response.ok) throw new Error(`API ${response.status}`);
    return await response.json();
  } finally {
    clearTimeout(timer);
  }
}

export async function getBackendStatus() {
  try {
    const health = await apiRequest("/health/status", { timeout: 4000 });
    return { connected: true, status: health.status, health, baseUrl: API_BASE };
  } catch (error) {
    return { connected: false, status: "offline", error: error.name === "AbortError" ? "timeout" : error.message, baseUrl: API_BASE };
  }
}

export function runBackendQuery(rawQuery, assetId) {
  return apiRequest("/command-bar/query", {
    method: "POST",
    body: { user_id: "default-user", raw_query: rawQuery, ...(assetId ? { asset_id: assetId } : {}) },
    timeout: 15000,
  });
}

export const backendResources = {
  assets: (limit = 1000) => apiRequest(`/assets?limit=${limit}`),
  positions: () => apiRequest("/positions"),
  portfolio: () => apiRequest("/portfolio/current"),
  signals: () => apiRequest("/signals"),
  orderDrafts: () => apiRequest("/orders/drafts"),
  theses: () => apiRequest("/investment-theses"),
  riskBudgets: () => apiRequest("/risk-budgets"),
  reviews: () => apiRequest("/reviews/monthly"),
};
