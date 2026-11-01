"""Per-user news settings and cache. Fetch only fixed provider hosts; never fetch article URLs."""
from __future__ import annotations

import hashlib
import json
import os
import re
import ssl
import threading
from weakref import WeakValueDictionary
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

import certifi
from sqlalchemy import select

from app.core.local_secrets import LocalSecretError, set_user_secret
from app.models import LocalUserConfig
from app.services.chinese_news_sources import SOURCES
from concurrent.futures import ThreadPoolExecutor

DEFAULTS = {"provider": "chinese_aggregate", "sources":list(SOURCES), "query": "bitcoin OR ethereum", "symbols": ["COIN", "MSTR"], "language": "zh", "refresh_seconds": 60, "auto_refresh": True}


_REFRESH_LOCKS = WeakValueDictionary()
_LOCK_GUARD = threading.Lock()

def _refresh_lock(user_id):
    with _LOCK_GUARD:
        lock = _REFRESH_LOCKS.get(user_id)
        if lock is None:
            lock = threading.Lock()
            _REFRESH_LOCKS[user_id] = lock
        return lock


class NewsFeedError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class NoNewsRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise NewsFeedError("news_redirect_rejected")


def fetch_news_json(url, headers):
    parsed = urlsplit(url)
    if parsed.scheme != "https" or (parsed.netloc, parsed.path) not in {("newsapi.org", "/v2/everything"), ("api.nasdaq.com", "/api/news/topic/articlebysymbol"), ("cointelegraph.com", "/rss"), ("www.panewslab.com", "/rss.xml"),('rss.odaily.news','/rss/newsflash'),('rss.odaily.news','/rss/post'),('api.theblockbeats.news','/v2/rss/newsflash'),('api.theblockbeats.news','/v2/rss/article')}:
        raise NewsFeedError("news_host_rejected")
    opener = build_opener(HTTPSHandler(context=ssl.create_default_context(cafile=certifi.where())), NoNewsRedirect())
    try:
        with opener.open(Request(url, headers=headers, method="GET"), timeout=20 if parsed.hostname == "www.panewslab.com" else 10) as response:
            body = response.read(2_000_001)
        if len(body) > 2_000_000:
            raise NewsFeedError("news_response_invalid")
        publisher={'www.panewslab.com':'PANews','rss.odaily.news':'Odaily 星球日报','api.theblockbeats.news':'律动 BlockBeats','cointelegraph.com':'Cointelegraph'}.get(parsed.hostname)
        return parse_public_rss(body,publisher) if publisher else json.loads(body)
    except HTTPError as exc:
        raise NewsFeedError({401: "news_key_rejected", 403: "news_access_denied", 429: "news_rate_limited"}.get(exc.code, "news_source_unavailable")) from None
    except NewsFeedError:
        raise
    except Exception:
        raise NewsFeedError("news_source_unavailable") from None


class _TextOnly(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def parse_public_rss(body, publisher="Cointelegraph"):
    if len(body) > 2_000_000 or b"<!DOCTYPE" in body.upper() or b"<!ENTITY" in body.upper():
        raise NewsFeedError("news_response_invalid")
    try:
        root = ET.fromstring(body)
        channel = root.find("channel")
        if root.tag != "rss" or channel is None:
            raise ValueError()
        articles = []
        for item in channel.findall("item")[:100]:
            raw = item.findtext("pubDate") or ""
            try:
                published = parsedate_to_datetime(raw)
                date = published.astimezone(timezone.utc).isoformat() if published.tzinfo else None
            except (ValueError, TypeError, OverflowError):
                date = None
            text = _TextOnly()
            text.feed((item.findtext("description") or "")[:20000])
            articles.append({"title": item.findtext("title"), "url": item.findtext("link"), "publishedAt": date, "description": " ".join(text.parts).strip(), "source": {"name": publisher}})
        return {"status": "ok", "articles": articles}
    except (ET.ParseError, ValueError):
        raise NewsFeedError("news_response_invalid") from None


def _utc(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
    except ValueError:
        return None


def normalize_articles(rows, provider):
    if not isinstance(rows, list) or len(rows) > 500:
        raise NewsFeedError("news_response_invalid")
    found = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        title = row.get("title")
        url = row.get("url")
        if provider == "nasdaq" and isinstance(url, str) and url.startswith("/") and not url.startswith("//"):
            url = "https://www.nasdaq.com" + url
        if not isinstance(title, str) or not title.strip() or title == "[Removed]" or not isinstance(url, str):
            continue
        try:
            parsed = urlsplit(url)
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None, 443):
                continue
        except ValueError:
            continue
        publication = row.get("created") if provider == "nasdaq" else row.get("publishedAt")
        instant = _utc(publication)
        source = row.get("source")
        publisher = source.get("name") if isinstance(source, dict) else row.get("publisher")
        item = {"id": hashlib.sha256(url.encode()).hexdigest()[:24], "title": title.strip()[:500], "description": str(row.get("description") or "")[:1200], "url": url[:3000], "publisher": str(publisher or provider)[:120], "published_at": instant.isoformat() if instant else None, "published_at_raw": str(publication or "")[:100], "symbol": str(row.get("symbol") or "")[:20], "kind":'flash' if provider=='panews' else 'article'}
        if url not in found:
            found[url] = item
    return sorted(found.values(), key=lambda item: item["published_at"] or "", reverse=True)[:100]


class NewsFeedService:
    def __init__(self, db, user_id, *, fetch=None, now=None):
        self.db, self.user_id = db, user_id
        self.fetch = fetch or fetch_news_json
        self.now = now or (lambda: datetime.now(timezone.utc))

    def _row(self, key):
        return self.db.scalar(select(LocalUserConfig).where(LocalUserConfig.user_id == self.user_id, LocalUserConfig.config_key == "news_feed:" + key))

    def _read(self, key):
        row = self._row(key)
        return dict(row.value_json) if row else {}

    def _write(self, key, value):
        row = self._row(key)
        if row is None:
            row = LocalUserConfig(user_id=self.user_id, config_key="news_feed:" + key, value_json=json.loads(json.dumps(value)))
            self.db.add(row)
        else:
            row.value_json = json.loads(json.dumps(value))
        self.db.commit()

    def _secret_name(self):
        return "NEWSAPI_" + hashlib.sha256(self.user_id.encode()).hexdigest()[:32].upper()

    def settings(self):
        value = {**DEFAULTS, **self._read("settings")}
        return {**value, "key_configured": bool(os.environ.get(self._secret_name())), "storage": "local_file_0600_unencrypted"}

    def configure(self, payload):
        current = self.settings()
        provider = payload.get("provider", current["provider"])
        query = payload.get("query", current["query"])
        symbols = payload.get("symbols", current["symbols"])
        language = payload.get("language", current["language"])
        interval = payload.get("refresh_seconds", 900 if provider == "newsapi" and provider != current["provider"] else current["refresh_seconds"])
        auto = payload.get("auto_refresh", False if provider == "newsapi" and provider != current["provider"] else current["auto_refresh"])
        key = payload.get("api_key", "")
        sources=payload.get('sources',current['sources'])
        if not isinstance(sources,list) or not sources or len(sources)>len(SOURCES) or any(not isinstance(source,str) or source not in SOURCES for source in sources) or len(set(sources))!=len(sources):raise NewsFeedError('news_settings_invalid')
        if provider not in {"chinese_aggregate", "cointelegraph", "panews", "nasdaq", "newsapi"} or not isinstance(query, str) or not 1 <= len(query.strip()) <= 200 or any(ord(c) < 32 for c in query):
            raise NewsFeedError("news_settings_invalid")
        if not isinstance(symbols, list) or not 1 <= len(symbols) <= 6 or any(not isinstance(s, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9.\-]{0,9}", s) for s in symbols):
            raise NewsFeedError("news_settings_invalid")
        if language not in {"", "zh", "en"} or type(interval) is not int or interval not in {60, 300, 900, 3600} or type(auto) is not bool:
            raise NewsFeedError("news_settings_invalid")
        if not isinstance(key, str) or (key and not re.fullmatch(r"[A-Za-z0-9_-]{8,256}", key)):
            raise NewsFeedError("news_key_invalid")
        if provider == "newsapi" and not (key or current["key_configured"]):
            raise NewsFeedError("news_key_required")
        value = {"provider": provider, "sources":sources, "query": query.strip(), "symbols": list(dict.fromkeys(s.upper() for s in symbols)), "language": language, "refresh_seconds": interval, "auto_refresh": auto, "credential_version": current.get("credential_version", 0) + (1 if key else 0)}
        if key:
            try:
                set_user_secret(self._secret_name(), key)
            except LocalSecretError:
                raise NewsFeedError("news_key_storage_failed") from None
        self._write("settings", value)
        return self.settings()

    def _identity(self, config):
        return hashlib.sha256(json.dumps({**{k: config[k] for k in ("provider", "query", "symbols", "language", "sources")}, "credential_version": config.get("credential_version", 0)}, sort_keys=True).encode()).hexdigest()

    def latest(self):
        config = self.settings()
        cache = self._read("cache")
        if cache.get("identity") != self._identity(config):
            cache = {}
        fetched = _utc(cache.get("fetched_at"))
        now = self.now()
        age = max(0, (now - fetched).total_seconds()) if fetched else None
        statuses=[]
        for key,feed in cache.get('feeds',{}).items():
            stamp=_utc(feed.get('fetched_at'));feed_age=max(0,(now-stamp).total_seconds()) if stamp else None
            statuses.append({k:v for k,v in {**feed,'id':key,'age_seconds':feed_age,'stale':feed_age is None or feed_age>config['refresh_seconds']*2}.items() if k!='articles'})
        articles=[]
        status_by_id={row['id']:row for row in statuses}
        for item in cache.get('articles') or []:
            feed=status_by_id.get(item.get('source_id','')+':'+item.get('kind',''))
            articles.append({**item,**({'source_fetched_at':feed.get('fetched_at'),'source_stale':feed['stale'],'source_error':feed['last_error']} if feed else {})})
        articles.sort(key=lambda row:row.get('published_at') or '',reverse=True)
        return {"provider": config["provider"], "settings": config, "source_status":statuses,"status": "error" if cache.get("last_error") else ("ready" if fetched else "missing"), "articles": articles, "fetched_at": cache.get("fetched_at"), "checked_at": now.isoformat(), "age_seconds": round(age, 3) if age is not None else None, "stale": age is None or age > config["refresh_seconds"] * 2, "last_attempt_at": cache.get("last_attempt_at"), "last_error": cache.get("last_error"), "errors_count": cache.get("errors_count", 0), "execution_available": False}

    def refresh(self, *, automatic=False):
        lock = _refresh_lock(self.user_id)
        if not lock.acquire(blocking=False):
            return {**self.latest(), "refresh_skipped": "in_progress"}
        try:
            return self._refresh(automatic=automatic)
        finally:
            lock.release()

    def _refresh(self, *, automatic=False):
        config = self.settings()
        if automatic and not config["auto_refresh"]:
            return {**self.latest(), "refresh_skipped": "disabled"}
        cache = self._read("cache")
        identity = self._identity(config)
        if cache.get("identity") != identity:
            cache = {"identity": identity}
        attempted = _utc(cache.get("last_attempt_at"))
        if attempted and (self.now() - attempted).total_seconds() < (config["refresh_seconds"] if automatic else 30):
            return {**self.latest(), "refresh_skipped": "cooldown"}
        cache["last_attempt_at"] = self.now().isoformat()
        self._write("cache", cache)
        if config['provider']=='chinese_aggregate':
            return self._refresh_chinese(config,cache)
        try:
            rows, errors = [], 0
            if config["provider"] in {"newsapi", "cointelegraph", "panews"}:
                if config["provider"] == "newsapi":
                    key = os.environ.get(self._secret_name())
                    if not key:
                        raise NewsFeedError("news_key_required")
                    query = {"q": config["query"], "pageSize": 100, "sortBy": "publishedAt"}
                    if config["language"]:
                        query["language"] = config["language"]
                    url, headers = "https://newsapi.org/v2/everything?" + urlencode(query), {"X-Api-Key": key, "Accept": "application/json"}
                elif config["provider"] == "panews":
                    url, headers = "https://www.panewslab.com/rss.xml?lang=zh&type=NEWS", {"Accept": "application/rss+xml", "User-Agent": "AI-Trading-Assistant/1.0"}
                else:
                    url, headers = "https://cointelegraph.com/rss", {"Accept": "application/rss+xml", "User-Agent": "AI-Trading-Assistant/1.0"}
                payload = self.fetch(url, headers)
                if not isinstance(payload, dict) or payload.get("status") != "ok":
                    code = payload.get("code") if isinstance(payload, dict) else None
                    raise NewsFeedError({"apiKeyInvalid": "news_key_rejected", "apiKeyExhausted": "news_rate_limited", "rateLimited": "news_rate_limited"}.get(code, "news_response_invalid"))
                rows = payload.get("articles")
            else:
                for symbol in config["symbols"]:
                    try:
                        payload = self.fetch("https://api.nasdaq.com/api/news/topic/articlebysymbol?" + urlencode({"q": symbol + "|stocks", "limit": 30, "offset": 0}), {"Accept": "application/json", "User-Agent": "Mozilla/5.0"})
                        data = payload.get("data") if isinstance(payload, dict) else None
                        items = data.get("rows") if isinstance(data, dict) else None
                        if not isinstance(items, list) or len(items) > 100:
                            raise NewsFeedError("news_response_invalid")
                        rows.extend({**item, "symbol": symbol} for item in items if isinstance(item, dict))
                    except Exception:
                        errors += 1
                if errors == len(config["symbols"]):
                    raise NewsFeedError("news_source_unavailable")
            articles = normalize_articles(rows, config["provider"])
            if rows and not articles:
                raise NewsFeedError("news_response_invalid")
            cache.update(articles=articles, fetched_at=self.now().isoformat(), last_error=None, errors_count=errors)
        except NewsFeedError as exc:
            cache["last_error"] = exc.code
        except Exception:
            cache["last_error"] = "news_source_unavailable"
        self._write("cache", cache)
        return self.latest()

    def _refresh_chinese(self,config,cache):
        jobs=[(source,kind) for source in config['sources'] for kind in ('flash','article')]
        def retrieve(job):
            source,kind=job
            try:
                payload=self.fetch(SOURCES[source][kind],{'Accept':'application/rss+xml','User-Agent':'AI-Trading-Assistant/1.0','language':'cn'})
                if not isinstance(payload,dict) or payload.get('status')!='ok':raise NewsFeedError('news_response_invalid')
                rows=normalize_articles(payload.get('articles'),source)
                if payload.get('articles') and not rows:raise NewsFeedError('news_response_invalid')
                return job,[{**row,'kind':kind,'source_id':source,'publisher':SOURCES[source]['name']} for row in rows],None
            except NewsFeedError as exc:return job,None,exc.code
            except Exception:return job,None,'news_source_unavailable'
        feeds={};success=0
        with ThreadPoolExecutor(max_workers=6) as pool:
            for (source,kind),articles,error in pool.map(retrieve,jobs):
                key=source+':'+kind;old=cache.get('feeds',{}).get(key,{})
                feed={**old,'publisher':SOURCES[source]['name'],'source_id':source,'kind':kind,'checked_at':self.now().isoformat(),'last_error':error,'status':'error' if error else 'ready'}
                if articles is not None:
                    feed.update(articles=articles,fetched_at=self.now().isoformat());success+=1
                feed['count']=len(feed.get('articles',[]));feeds[key]=feed
        merged=[]
        for kind in ('flash','article'):
            unique={}
            for feed in feeds.values():
                for row in feed.get('articles',[]):
                    if row['kind']==kind:unique.setdefault(row['url'],row)
            merged.extend(sorted(unique.values(),key=lambda row:row['published_at'] or '',reverse=True)[:100])
        merged.sort(key=lambda row:row['published_at'] or '',reverse=True)
        cache.update(feeds=feeds,articles=merged,errors_count=len(jobs)-success,last_error=None if success else 'news_source_unavailable')
        if success:cache['fetched_at']=self.now().isoformat()
        self._write('cache',cache)
        return self.latest()
