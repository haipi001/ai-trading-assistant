export function safeNewsURL(value) {
  if (typeof value !== 'string' || value.length > 3000) return null;
  try { const url = new URL(value); return url.protocol === 'https:' && !url.username && !url.password && (!url.port || url.port === '443') ? url.href : null; } catch { return null; }
}
export function newsSnapshot(value) {
  if (!value || !['chinese_aggregate','panews','cointelegraph','nasdaq','newsapi'].includes(value.provider) || !Array.isArray(value.articles) || value.articles.length > 200 || !['ready','missing','error'].includes(value.status)) throw new Error('news_response_invalid');
  const articles = [], seen = new Set();
  for (const item of value.articles) {
    const url = safeNewsURL(item?.url);
    if (!url || typeof item.title !== 'string' || !item.title.trim() || seen.has(url)) continue;
    seen.add(url);
    const date = typeof item.published_at === 'string' && /(?:Z|[+-]\d\d:\d\d)$/.test(item.published_at) && Number.isFinite(Date.parse(item.published_at)) ? item.published_at : null;
    articles.push({sourceStale:item.source_stale===true,sourceFailed:Boolean(item.source_error),sourceFetchedAt:typeof item.source_fetched_at==='string'?item.source_fetched_at:null,kind:item.kind==='flash'?'flash':item.kind==='article'?'article':value.provider==='panews'?'flash':'article',sourceId:typeof item.source_id==='string'?item.source_id:value.provider,id:url,title:item.title.slice(0,500),description:typeof item.description==='string'?item.description.slice(0,1200):'',url,publisher:typeof item.publisher==='string'?item.publisher:'来源未提供',publishedAt:date,rawTime:typeof item.published_at_raw==='string'?item.published_at_raw.slice(0,100):'',symbol:typeof item.symbol==='string'?item.symbol:''});
  }
  articles.sort((a,b)=>(b.publishedAt||'').localeCompare(a.publishedAt||''));
  const fetchedAt = typeof value.fetched_at==='string' && Number.isFinite(Date.parse(value.fetched_at)) ? value.fetched_at : null;
  return {...value, articles, fetchedAt};
}
export const NEWS_ERRORS = {
 news_key_required:'请在系统设置的“资讯服务”中保存 NewsAPI Key。',news_key_rejected:'资讯服务拒绝了 Key，请检查 Key 是否正确及账户权限。',news_access_denied:'资讯来源拒绝访问，请检查套餐权限或稍后重试。',news_rate_limited:'资讯来源请求额度已用尽或触发限流，请降低刷新频率。',news_response_invalid:'资讯来源返回的数据无法验证，请稍后重试。',news_source_unavailable:'资讯来源暂时无法连接，保留上次成功获取的消息。',news_redirect_rejected:'资讯来源发生重定向，本次请求已停止。',news_settings_invalid:'请检查关键词、股票代码和刷新频率。',news_key_invalid:'Key 格式不正确，请重新输入。',news_key_storage_failed:'后端无法保存 Key，请检查本机凭证文件权限。'
};
const CHANNELS = {
 'Web3.0':/web3|blockchain|区块链/i,分析:/analysis|outlook|分析|展望/i,科普:/guide|explainer|how to|科普|教程/i,
 巨鲸:/whale|巨鲸/i,主力:/institution|fund flow|主力|机构/i,推特:/twitter|tweet|社交/i,市场:/market|price|市场|行情/i,
 特朗普:/trump|特朗普/i,上新:/listing|listed|上新|上线/i,链上:/on.chain|blockchain|链上/i,ETF:/\betf\b/i,宏观:/inflation|federal reserve|interest rate|cpi|宏观|美联储|通胀/i,
 币股:/coinbase|microstrategy|strategy inc|stock|nasdaq|矿企|股票/i,产品教程:/guide|tutorial|教程/i,行业报告:/report|research|报告/i,
 直播:/live stream|直播/i,直播回顾:/replay|直播回顾/i,活动FUN放:/conference|summit|活动|峰会/i,长推:/thread|长推/i,媒体报道:/media|媒体/i,AI号:/artificial intelligence|\bai\b|人工智能/i
};
export function filterNews(articles, channel, query='', allChannels=false) {
 const matcher = channel==='精选'||allChannels ? null : CHANNELS[channel];
 if (!matcher && channel!=='精选' && !allChannels) return [];
 const needle=query.normalize('NFKC').trim().toLocaleLowerCase();
 return articles.filter(item=>{const text=`${item.title} ${item.description} ${item.publisher} ${item.symbol}`.normalize('NFKC');return (!matcher||matcher.test(text))&&(!needle||text.toLocaleLowerCase().includes(needle));});
}

export const newsProviderLabel=value=>({chinese_aggregate:"中文多源聚合",panews:"PANews 中文快讯",cointelegraph:"Cointelegraph RSS（英文）",nasdaq:"Nasdaq 股票新闻",newsapi:"NewsAPI"}[value]||"正在读取资讯来源");
