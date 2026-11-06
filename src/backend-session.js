import {getTerminalBackendBridge} from './terminal-backend-bridge.js';
// Session secrets live only in this module; never localStorage/sessionStorage.
let session = null;
const listeners = new Set();
function notify() { for (const listener of listeners) listener(); }
export function getBackendSession() {
  const bridge=getTerminalBackendBridge();if(bridge)return bridge.session();
  if (session && Date.parse(session.expires_at) <= Date.now()) { session = null; }
  return session ? { user_id: session.user.user_id, role: session.user.role, expires_at: session.expires_at } : null;
}
export function getSessionIdentity() {
  const bridge=getTerminalBackendBridge();return bridge?bridge.identity():getSessionAuthorization();
}
export function getSessionAuthorization() {
  if(getTerminalBackendBridge())return null;
  return getBackendSession() ? `Bearer ${session.token}` : null;
}
export function setBackendSession(packet) {
  if (typeof packet?.session_token !== 'string' || !packet.session_token.trim() || !packet.user?.user_id || !Number.isFinite(Date.parse(packet.expires_at)) || Date.parse(packet.expires_at) <= Date.now()) {
    throw new Error('invalid_session_response');
  }
  session = { token: packet.session_token, expires_at: packet.expires_at, user: { user_id: packet.user.user_id, role: packet.user.role } };
  notify();
}
export function clearBackendSession(expectedAuthorization) {
  if (expectedAuthorization && getSessionAuthorization() !== expectedAuthorization) return;
  session = null;
  notify();
}
export function subscribeBackendSession(listener) {
  const bridge=getTerminalBackendBridge();if(bridge)return bridge.subscribe(listener);
  listeners.add(listener);
  return () => listeners.delete(listener);
}
