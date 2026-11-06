import React, {useEffect, useState} from 'react';
import './ai-integration-settings.css';
import {API_BASE, loginBackend, logoutBackend} from './backend-api.js';
import {getBackendSession, subscribeBackendSession} from './backend-session.js';

export function BackendSessionSettings() {
  const [session, setSession] = useState(getBackendSession);
  const [token, setToken] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => subscribeBackendSession(() => setSession(getBackendSession())), []);
  useEffect(() => {
    if (!session) return;
    const timer = setTimeout(() => setSession(getBackendSession()), Math.min(Math.max(0, Date.parse(session.expires_at) - Date.now()) + 10, 2147483647));
    return () => clearTimeout(timer);
  }, [session]);
  async function login(event) {
    event.preventDefault();
    if (busy || !token.trim()) return;
    setBusy(true); setError('');
    const value = token.trim(); setToken('');
    try { await loginBackend(value); }
    catch (e) { setError(e.status === 401 ? '身份验证失败，请检查访问令牌及后端身份配置。' : '无法完成登录，请检查后端连接和托管认证配置。'); }
    finally { setBusy(false); }
  }
  async function logout() {
    if (busy) return;
    setBusy(true); setError('');
    try { await logoutBackend(); }
    catch { setError('当前页面已退出；服务端撤销未确认，请在身份服务中撤销会话。'); }
    finally { setBusy(false); }
  }
  return <section className="ai-integration-settings"><p>连接地址：{API_BASE}</p><p>托管服务需要登录。本地开发模式由后端配置决定，登录不改变账户交易权限。</p>
    {session ? <><p role="status">已登录 · {session.user_id} · {session.role} · 到期 {new Date(session.expires_at).toLocaleString('zh-CN')}</p><div className="integration-actions"><button type="button" disabled={busy} onClick={logout}>退出当前后端会话</button></div></> :
      <form onSubmit={login}><label className="integration-wide">身份服务访问令牌<input type="password" aria-label="身份服务访问令牌" autoComplete="off" value={token} disabled={busy} onChange={event => setToken(event.target.value)}/></label><p className="integration-wide">只发送至上方后端进行身份验证；令牌与会话仅保存在当前页面内存，刷新后需重新登录。</p><div className="integration-actions"><button type="submit" disabled={busy || !token.trim()} onClick={login}>{busy ? '正在验证…' : '登录后端'}</button></div></form>}
    {error && <p role="alert">{error}</p>}
  </section>;
}
