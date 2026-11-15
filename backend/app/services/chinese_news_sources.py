"""Publisher-owned Chinese feeds. Classification follows the selected feed, not keywords."""
SOURCES = {
    'panews': {'name':'PANews', 'flash':'https://www.panewslab.com/rss.xml?lang=zh&type=NEWS', 'article':'https://www.panewslab.com/rss.xml?lang=zh&type=NORMAL'},
    'odaily': {'name':'Odaily 星球日报', 'flash':'https://rss.odaily.news/rss/newsflash', 'article':'https://rss.odaily.news/rss/post'},
    'blockbeats': {'name':'律动 BlockBeats', 'flash':'https://api.theblockbeats.news/v2/rss/newsflash', 'article':'https://api.theblockbeats.news/v2/rss/article'},
}

# Publisher-owned feeds; market tags indicate coverage, not company relevance.
SOURCES.update({
 'eastmoney': {'name':'东方财富 · 财经快讯','market':'cn','flash':'https://np-listapi.eastmoney.com/comm/web/getFastNewsList?client=web&biz=web_724&fastColumn=102&sortEnd=&pageSize=100&req_trace=stock-news'},
 'rthk': {'name':'香港电台 · 财经','market':'hk','article':'https://rthk9.rthk.hk/rthk/news/rss/c_expressnews_cfinance.xml'},
 'cnbc': {'name':'CNBC · Finance','market':'us','article':'https://www.cnbc.com/id/10000664/device/rss/rss.html'},
})

SOURCES['eastmoney_announcements'] = {'name':'东方财富 · A股公告/财报','market':'cn','article':'https://np-anotice-stock.eastmoney.com/api/security/ann?sr=-1&page_size=100&page_index=1&ann_type=A&client_source=web&f_node=0&s_node=0'}
