import {assertTerminalTradeRequest} from './terminal-trading-policy.js';
import {getTerminalBackendBridge} from './terminal-backend-bridge.js';
import {getBackendSession, getSessionAuthorization, clearBackendSession, setBackendSession} from './backend-session.js';
export const API_BASE = (import.meta.env?.VITE_API_BASE_URL || "http://127.0.0.1:8001").replace(/\/$/, "");

export async function apiRequest(path, options = {}) {
  assertTerminalTradeRequest(path,options);
  const bridge=getTerminalBackendBridge();
  if(bridge){return bridge.request(path,{...options,authenticated:options.auth!==false});}
  const controller = new AbortController();
  const abort = () => controller.abort();
  const timer = setTimeout(abort, options.timeout || 6000);
  options.signal?.addEventListener("abort", abort, {once:true});
  if(options.signal?.aborted) controller.abort();
  const authorization = options.auth === false ? null : getSessionAuthorization();
  const session = authorization ? getBackendSession() : null;
  const body = session && options.body?.user_id === "default-user" ? {...options.body, user_id:session.user_id} : options.body;
  try {
    const response = await fetch(`${API_BASE}${path}`, {
      method: options.method || "GET",
      credentials: "include",
      headers: { "Content-Type": "application/json", ...options.headers, ...(authorization ? {Authorization:authorization} : {}) },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });
    if (!response.ok) {if(response.status===401&&authorization)clearBackendSession(authorization);const error=new Error(`API ${response.status}`);error.status=response.status;try{const value=await response.json();const code=value?.detail?.code;if(typeof code==="string"&&/^[a-z_]{1,80}$/.test(code))error.code=code;}catch{}throw error;}
    return response.status === 204 ? null : await response.json();
  } finally {
    clearTimeout(timer);
    options.signal?.removeEventListener("abort", abort);
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

let sessionAttempt = 0;
export async function loginBackend(accessToken) {
  const bridge=getTerminalBackendBridge();if(bridge)return bridge.login(accessToken);
  const attempt = ++sessionAttempt;
  const packet = await apiRequest('/production/auth/login', {method:'POST', auth:false, body:{access_token:accessToken}, timeout:15000});
  if (attempt !== sessionAttempt) throw new Error("session_attempt_superseded");
  setBackendSession(packet);
  return getBackendSession();
}
export async function logoutBackend() {
  const bridge=getTerminalBackendBridge();if(bridge)return bridge.logout();
  sessionAttempt++;
  const authorization = getSessionAuthorization();
  if (!authorization) return;
  try {
    await apiRequest('/production/auth/logout', {method:'POST', body:{session_token:authorization.slice(7)}});
  } finally { clearBackendSession(authorization); }
}
