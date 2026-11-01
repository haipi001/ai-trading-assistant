"""Publisher-owned Chinese feeds. Classification follows the selected feed, not keywords."""
SOURCES = {
    'panews': {'name':'PANews', 'flash':'https://www.panewslab.com/rss.xml?lang=zh&type=NEWS', 'article':'https://www.panewslab.com/rss.xml?lang=zh&type=NORMAL'},
    'odaily': {'name':'Odaily 星球日报', 'flash':'https://rss.odaily.news/rss/newsflash', 'article':'https://rss.odaily.news/rss/post'},
    'blockbeats': {'name':'律动 BlockBeats', 'flash':'https://api.theblockbeats.news/v2/rss/newsflash', 'article':'https://api.theblockbeats.news/v2/rss/article'},
}
