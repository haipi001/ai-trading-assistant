"""Bounded, user-scoped news material for an explicitly requested AI call."""
import hashlib
import json
import re
from urllib.parse import urlsplit
from app.services.news_feed import NewsFeedService


class ResearchContextError(ValueError):
    pass


def load_news_context(db, user_id):
    snapshot = NewsFeedService(db, user_id).latest()
    articles = []
    for item in snapshot.get('articles') or []:
        if len(articles) == 5:
            break
        if not isinstance(item, dict) or not isinstance(item.get('title'), str) or not item['title'].strip():
            continue
        url = item.get('url')
        if not isinstance(url, str) or len(url) > 3000:
            continue
        try:
            parsed = urlsplit(url)
            if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None, 443):
                continue
        except ValueError:
            continue
        articles.append({'id':f'N{len(articles)+1}', 'title':item['title'][:500], 'description':str(item.get('description') or '')[:600], 'url':url, 'publisher':str(item.get('publisher') or snapshot.get('provider') or '')[:120], 'published_at':item.get('published_at'), 'published_at_raw':str(item.get('published_at_raw') or '')[:100], 'kind':item.get('kind'), 'source_fetched_at':item.get('source_fetched_at'), 'source_stale':item.get('source_stale',snapshot.get('stale',True)), 'source_refresh_failed':bool(item.get('source_error'))})
    if not articles or not snapshot.get('fetched_at'):
        raise ResearchContextError('ai_news_missing')
    context = {'provider':snapshot['provider'], 'fetched_at':snapshot['fetched_at'], 'age_seconds':snapshot.get('age_seconds'), 'stale':snapshot.get('stale', True), 'last_refresh_failed':snapshot.get('status') == 'error', 'articles':articles, 'limitations':'Cached source claims, not independently verified facts. Fetch time is not publication time. Source plans and collection may introduce delays. These are the latest cached articles, not necessarily related to the selected symbol.'}
    context['content_hash'] = hashlib.sha256(json.dumps(context, sort_keys=True, ensure_ascii=True).encode()).hexdigest()
    return context


def validate_news_citations(report, context):
    ids = report.evidence.get('news_citation_ids', [])
    if not isinstance(ids, list) or len(ids) > 5 or any(not isinstance(value, str) for value in ids):
        raise ResearchContextError('ai_news_citation_invalid')
    allowed = {item['id'] for item in context['articles']} if context else set()
    texts = [report.summary, report.bullish_case, report.bearish_case, *report.key_risks, report.limitations, report.suggested_action]
    referenced = set(re.findall(r'\[(N\d+)\]', '\n'.join(texts)))
    if set(ids) - allowed or referenced - set(ids) or set(ids) - referenced:
        raise ResearchContextError('ai_news_citation_invalid')
    return list(dict.fromkeys(ids))
