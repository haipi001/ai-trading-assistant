// Conversation threads for the AI search entry.
// Pure helpers; storage stays with the caller so market scoping, ordering and
// retention rules are testable without a DOM.

export const THREAD_LIMIT = 80;

export const MARKET_SCOPES = { stocks: '股票', web3: '加密' };

export function scopeOf(marketMode) {
  return marketMode === 'stocks' ? 'stocks' : 'web3';
}

export function scopeLabel(scope) {
  return MARKET_SCOPES[scope] || '未知市场';
}

const stamp = value => {
  const parsed = Date.parse(value || '');
  return Number.isFinite(parsed) ? parsed : 0;
};
const text = value => (typeof value === 'string' ? value : '');
const uid = () => `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

export function makeMessage({ question, answer, status = 'ok', reason = '', provider = '', model = '', newsAttached = false, style = 'brief' }) {
  const q = text(question).trim().slice(0, 500);
  if (!q) return null;
  return {
    id: uid(),
    question: q,
    answer: text(answer).slice(0, 12000),
    status: status === 'ok' ? 'ok' : 'failed',
    reason: text(reason),
    provider: text(provider),
    model: text(model),
    newsAttached: Boolean(newsAttached),
    style: style === 'detailed' ? 'detailed' : 'brief',
    created: new Date().toISOString(),
  };
}

export function newThread(scope = 'web3', title = '') {
  return {
    id: uid(),
    title: text(title).slice(0, 60),
    scope: scope === 'stocks' ? 'stocks' : 'web3',
    archived: false,
    created: new Date().toISOString(),
    updated: new Date().toISOString(),
    messages: [],
  };
}

function normalizeMessage(row) {
  if (!row || typeof row !== 'object' || !text(row.question).trim()) return null;
  return {
    id: String(row.id || uid()),
    question: text(row.question),
    answer: text(row.answer),
    status: row.status === 'failed' ? 'failed' : 'ok',
    reason: text(row.reason),
    provider: text(row.provider),
    model: text(row.model),
    newsAttached: Boolean(row.newsAttached),
    style: row.style === 'detailed' ? 'detailed' : 'brief',
    created: text(row.created),
  };
}

export function normalizeThreads(value) {
  const list = Array.isArray(value) ? value : [];
  return list
    .filter(row => row && typeof row === 'object' && (row.id || Array.isArray(row.messages)))
    .map(row => ({
      id: String(row.id || uid()),
      title: text(row.title).slice(0, 60),
      scope: row.scope === 'stocks' ? 'stocks' : 'web3',
      archived: Boolean(row.archived),
      created: text(row.created),
      updated: text(row.updated) || text(row.created),
      messages: (Array.isArray(row.messages) ? row.messages : []).map(normalizeMessage).filter(Boolean),
    }))
    .sort((a, b) => stamp(b.updated) - stamp(a.updated));
}

export function createThread(threads, { scope = 'web3', title = '' } = {}) {
  const rows = normalizeThreads(threads);
  const thread = newThread(scope, title);
  // Two threads created in the same millisecond would tie on `updated` and
  // sort unpredictably, so keep the stamp strictly increasing.
  const latest = rows.reduce((max, row) => Math.max(max, stamp(row.updated)), 0);
  const now = Date.now();
  if (now <= latest) {
    const next = new Date(latest + 1).toISOString();
    thread.created = next;
    thread.updated = next;
  }
  const next = [thread, ...rows];
  return next.length <= THREAD_LIMIT ? next : next.slice(0, THREAD_LIMIT);
}

// Appends a message and lifts the thread to the top, since it is now active.
export function appendMessage(threads, threadId, message) {
  if (!message) return normalizeThreads(threads);
  const rows = normalizeThreads(threads);
  const latest = rows.reduce((max, row) => Math.max(max, stamp(row.updated)), 0);
  const now = Date.now();
  const updated = new Date(now <= latest ? latest + 1 : now).toISOString();
  return rows
    .map(row => (row.id === threadId ? { ...row, updated, archived: false, messages: [...row.messages, message] } : row))
    .sort((a, b) => stamp(b.updated) - stamp(a.updated));
}

export function removeThread(threads, id) {
  return normalizeThreads(threads).filter(row => row.id !== id);
}

export function renameThread(threads, id, title) {
  const clean = text(title).trim().slice(0, 60);
  return normalizeThreads(threads).map(row => (row.id === id ? { ...row, title: clean } : row));
}

export function toggleArchived(threads, id) {
  return normalizeThreads(threads).map(row => (row.id === id ? { ...row, archived: !row.archived } : row));
}

export function clearScopeThreads(threads, scope) {
  if (scope === 'all') return [];
  return normalizeThreads(threads).filter(row => row.scope !== scope);
}

// scope 'all' merges both markets; otherwise a stock thread never appears in
// the crypto list.
export function filterThreads(threads, { scope = 'all', query = '', archived = 'active' } = {}) {
  const rows = normalizeThreads(threads);
  const needle = text(query).trim().toLowerCase();
  return rows.filter(row => {
    if (scope !== 'all' && row.scope !== scope) return false;
    if (archived === 'active' && row.archived) return false;
    if (archived === 'archived' && !row.archived) return false;
    if (!needle) return true;
    return threadSearchText(row).includes(needle);
  });
}

export function threadSearchText(thread) {
  const title = text(thread?.title);
  const body = (Array.isArray(thread?.messages) ? thread.messages : [])
    .map(row => `${text(row.question)} ${text(row.answer)} ${text(row.reason)}`).join(' ');
  return `${title} ${body}`.toLowerCase();
}

// A thread is named after its first question unless the user renamed it.
export function threadTitle(thread) {
  const custom = text(thread?.title).trim();
  if (custom) return custom;
  const first = (Array.isArray(thread?.messages) ? thread.messages : []).find(row => text(row.question).trim());
  if (!first) return '新对话';
  const question = first.question.replace(/\s+/g, ' ').trim();
  return question.length > 26 ? `${question.slice(0, 26)}…` : question;
}

export function threadPreview(thread) {
  const messages = Array.isArray(thread?.messages) ? thread.messages : [];
  const last = messages[messages.length - 1];
  if (!last) return '还没有提问';
  const body = text(last.answer).replace(/\s+/g, ' ').trim();
  if (!body) return last.status === 'failed' ? (last.reason || '未获得回复') : '等待回复';
  return body.length > 46 ? `${body.slice(0, 46)}…` : body;
}

export function threadStats(threads) {
  const rows = normalizeThreads(threads);
  const messages = rows.reduce((total, row) => total + row.messages.length, 0);
  return {
    threads: rows.length,
    messages,
    active: rows.filter(row => !row.archived).length,
    archived: rows.filter(row => row.archived).length,
    stocks: rows.filter(row => row.scope === 'stocks').length,
    web3: rows.filter(row => row.scope === 'web3').length,
    failed: rows.reduce((total, row) => total + row.messages.filter(m => m.status === 'failed').length, 0),
  };
}

export function relativeTime(created, now = Date.now()) {
  const time = stamp(created);
  if (!time) return '时间未知';
  const seconds = Math.max(0, Math.round((now - time) / 1000));
  if (seconds < 60) return '刚刚';
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} 分钟前`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} 小时前`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days} 天前`;
  return new Date(time).toLocaleDateString('zh-CN');
}

export function messagePreview(message, limit = 48) {
  const body = text(message?.answer).replace(/\s+/g, ' ').trim();
  if (!body) return message?.status === 'failed' ? (message.reason || '未获得回复') : '尚无回复内容';
  return body.length > limit ? `${body.slice(0, limit)}…` : body;
}

export const STARTER_QUESTIONS = {
  stocks: [
    ['财报速读', 'NVDA 最新财报的增长质量如何？'],
    ['市场情绪', '利率变化如何影响科技股估值？'],
    ['价格分析', 'AAPL 当前关键支撑位在哪里？'],
  ],
  web3: [
    ['快速学习', '特朗普关税政策如何影响BTC？'],
    ['市场情绪', '当前恐惧与贪婪指数意味着什么？'],
    ['价格分析', 'BTC关键支撑位在哪里？'],
  ],
};
