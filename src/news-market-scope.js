// Which news feed scope follows each terminal market. Kept free of JSX and CSS
// imports so it can be tested and reused without a bundler.
export const MARKET_NEWS_SCOPE = { stocks: 'us', web3: 'crypto', cex: 'crypto', onchain: 'crypto' };

export function newsScopeForMarket(marketMode) {
  return MARKET_NEWS_SCOPE[marketMode] || 'all';
}

export const NEWS_SCOPE_LABELS = { all: '全部市场', cn: 'A股 / 中国财经', hk: '港股 / 香港财经', us: '美股 / 美国财经', crypto: '加密资产' };
