import json
import os
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.core import local_secrets
from app.db.base import Base
from app.models import LocalUserConfig
from app.services.news_feed import NewsFeedError, NewsFeedService, normalize_articles


@pytest.fixture()
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(local_secrets, "store_path", lambda: tmp_path / "fixture-secrets.env")
    before = set(os.environ)
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    for name in set(os.environ) - before:
        if name.startswith("NEWSAPI_"):
            os.environ.pop(name, None)
    Base.metadata.drop_all(engine)


def article(title="Fixture headline", url="https://example.com/fixture", at="2026-10-29T12:00:00Z"):
    return {"title": title, "url": url, "publishedAt": at, "source": {"name": "Fixture source"}, "description": "Fixture summary"}


def configured(db, **kwargs):
    service = NewsFeedService(db, "user-a", **kwargs)
    service.configure({"provider": "newsapi", "api_key": "fixture-news-key-123"})
    return service


def test_settings_and_key_are_user_scoped_and_redacted(db):
    a = configured(db)
    b = NewsFeedService(db, "user-b")
    assert a.settings()["key_configured"] is True
    assert b.settings()["key_configured"] is False
    assert b.settings()["provider"] == "chinese_aggregate"
    data = json.dumps([row.value_json for row in db.scalars(select(LocalUserConfig)).all()])
    assert "fixture-news-key-123" not in data
    assert "fixture-news-key-123" not in json.dumps(a.settings())
    assert "secret_reference" not in a.settings()


@pytest.mark.parametrize("payload", [{"query": ""}, {"symbols": ["x&apiKey=leak"]}, {"refresh_seconds": True}, {"refresh_seconds": 12}, {"auto_refresh": "true"}, {"language": "fr"}, {"api_key": "line\nbreak"}, {"symbols": []}])
def test_invalid_settings_do_not_replace_key_or_configuration(db, payload):
    service = configured(db)
    before = service.settings()
    secret = os.environ[service._secret_name()]
    with pytest.raises(NewsFeedError):
        service.configure({**payload, **({} if "api_key" in payload else {"api_key": "fixture-new-key-456"})})
    assert service.settings() == before
    assert os.environ[service._secret_name()] == secret


def test_refresh_uses_fixed_host_header_key_and_persists_sorted_deduplicated_news(db):
    calls = []
    def fetch(url, headers):
        calls.append((url, headers))
        return {"status": "ok", "articles": [article(), article("Newer", "https://example.com/new", "2026-10-29T13:00:00Z"), article()]}
    service = configured(db, fetch=fetch)
    result = service.refresh()
    assert result["status"] == "ready"
    assert [item["title"] for item in result["articles"]] == ["Newer", "Fixture headline"]
    assert calls[0][0].startswith("https://newsapi.org/v2/everything?")
    assert "fixture-news-key-123" not in calls[0][0]
    assert calls[0][1]["X-Api-Key"] == "fixture-news-key-123"
    db.expire_all()
    assert NewsFeedService(db, "user-a").latest()["articles"] == result["articles"]
    assert NewsFeedService(db, "user-b").latest()["status"] == "missing"
    assert service.refresh()["refresh_skipped"] == "cooldown"
    assert len(calls) == 1


def test_failed_refresh_retains_last_success_and_actual_fetch_time(db):
    instant = [datetime(2026, 10, 29, 13, tzinfo=timezone.utc)]
    failed = [False]
    def fetch(url, headers):
        if failed[0]:
            raise RuntimeError("sensitive provider error fixture-news-key-123")
        return {"status": "ok", "articles": [article()]}
    service = configured(db, fetch=fetch, now=lambda: instant[0])
    original = service.refresh()
    failed[0] = True
    instant[0] += timedelta(hours=1)
    result = service.refresh()
    assert result["status"] == "error"
    assert result["stale"] is True
    assert result["fetched_at"] == original["fetched_at"]
    assert result["articles"] == original["articles"]
    assert result["last_error"] == "news_source_unavailable"
    assert "sensitive" not in json.dumps(result)
    assert "fixture-news-key-123" not in json.dumps(result)


def test_changing_query_hides_incompatible_cache(db):
    service = configured(db, fetch=lambda *args: {"status": "ok", "articles": [article()]})
    service.refresh()
    service.configure({"query": "ethereum"})
    assert service.latest()["status"] == "missing"
    assert service.latest()["articles"] == []


def test_source_authentication_error_is_not_success(db):
    service = configured(db, fetch=lambda *args: {"status": "error", "code": "apiKeyInvalid", "message": "fixture secret"})
    result = service.refresh()
    assert result["status"] == "error"
    assert result["last_error"] == "news_key_rejected"
    assert result["fetched_at"] is None


def test_empty_success_is_distinct_from_invalid_response(db):
    service = configured(db, fetch=lambda *args: {"status": "ok", "articles": []})
    assert service.refresh()["status"] == "ready"
    assert service.latest()["articles"] == []


def test_article_links_and_unzoned_dates_are_not_invented(db):
    rows = [article(url="javascript:alert(1)"), article(url="https://user:password@example.com/a"), article(url="https://example.com:8443/a"), article(at="Oct 29, 2026")]
    result = normalize_articles(rows, "newsapi")
    assert len(result) == 1
    assert result[0]["published_at"] is None
    assert result[0]["published_at_raw"] == "Oct 29, 2026"


def test_partial_nasdaq_source_failure_is_visible(db):
    def fetch(url, headers):
        if "MSTR" in url:
            raise NewsFeedError("news_source_unavailable")
        return {"data": {"rows": [{"title": "Coinbase fixture", "url": "/articles/fixture", "created": "Oct 29, 2026"}]}}
    service = NewsFeedService(db, "user-a", fetch=fetch)
    service.configure({"provider": "nasdaq"})
    result = service.refresh()
    assert result["status"] == "ready"
    assert result["errors_count"] == 1
    assert result["articles"][0]["url"] == "https://www.nasdaq.com/articles/fixture"
    assert result["articles"][0]["published_at"] is None


def test_public_rss_parses_publication_time_and_strips_markup():
    from app.services.news_feed import parse_public_rss
    body = b"""<rss version="2.0"><channel><item><title>Fixture BTC ETF</title><link>https://cointelegraph.com/news/fixture</link><pubDate>Thu, 29 Oct 2026 13:00:00 +0000</pubDate><description>&lt;p&gt;Fixture &amp;amp; summary&lt;/p&gt;</description></item></channel></rss>"""
    value = parse_public_rss(body)
    result = normalize_articles(value["articles"], "cointelegraph")
    assert result[0]["published_at"] == "2026-10-29T13:00:00+00:00"
    assert result[0]["description"] == "Fixture & summary"
    with pytest.raises(NewsFeedError):
        parse_public_rss(b'<!DOCTYPE rss [<!ENTITY x "value">]><rss><channel/></rss>')


def test_default_public_rss_requires_no_secret_and_uses_fixed_url(db):
    def fetch(url, headers):
        assert url == "https://www.panewslab.com/rss.xml?lang=zh&type=NEWS"
        assert "X-Api-Key" not in headers
        return {"status": "ok", "articles": [article()]}
    service = NewsFeedService(db, "public-user", fetch=fetch)
    service.configure({"provider":"panews"})
    value = service.refresh()
    assert value["provider"] == "panews"
    assert value["status"] == "ready"
    assert value["settings"]["key_configured"] is False


def test_new_key_invalidates_previous_cache_and_has_conservative_newsapi_defaults(db):
    service = configured(db, fetch=lambda *args: {"status": "ok", "articles": [article()]})
    assert service.settings()["refresh_seconds"] == 900
    assert service.settings()["auto_refresh"] is False
    service.refresh()
    service.configure({"api_key": "fixture-rotated-key-456"})
    assert service.latest()["status"] == "missing"
    assert service.latest()["articles"] == []


def test_api_enforces_permissions_and_rejects_unknown_fields_without_echoing_key(db):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.news_feed import router, production_user, get_db
    from app.core.auth import AuthenticatedUser
    app = FastAPI()
    app.include_router(router)
    def database():
        yield db
    app.dependency_overrides[get_db] = database
    permissions = []
    app.dependency_overrides[production_user] = lambda: AuthenticatedUser("test-api-user", "viewer", permissions, True, True)
    with TestClient(app) as client:
        assert client.get('/news-feed/latest').status_code == 403
        assert client.put('/news-feed/settings', json={"api_key": "fixture-sensitive-key"}).status_code == 403
        permissions.extend(["readiness:read", "secrets:write"])
        response = client.get('/news-feed/latest')
        assert response.status_code == 200
        assert response.headers['cache-control'] == 'no-store'
        assert response.json()['status'] == 'missing'
        response = client.put('/news-feed/settings', json={"api_key": "fixture-sensitive-key", "arbitrary_url": "https://example.com"})
        assert response.status_code == 422
        assert 'fixture-sensitive-key' not in response.text


def test_automatic_refresh_respects_interval_across_separate_components(db):
    instant = [datetime(2026, 10, 29, 13, tzinfo=timezone.utc)]
    calls = []
    def fetch(*args):
        calls.append(args)
        return {"status": "ok", "articles": [article()]}
    service = NewsFeedService(db, "public-user", fetch=fetch, now=lambda: instant[0])
    service.refresh(automatic=True)
    instant[0] += timedelta(seconds=31)
    other_component = NewsFeedService(db, "public-user", fetch=fetch, now=lambda: instant[0])
    assert other_component.refresh(automatic=True)["refresh_skipped"] == "cooldown"
    assert len(calls) == 6
    instant[0] += timedelta(seconds=30)
    assert other_component.refresh(automatic=True)["status"] == "ready"
    assert len(calls) == 12
    other_component.configure({"auto_refresh": False})
    instant[0] += timedelta(minutes=5)
    assert other_component.refresh(automatic=True)["refresh_skipped"] == "disabled"
    assert len(calls) == 12


def test_panews_rss_preserves_chinese_source_text_and_timezone():
    from app.services.news_feed import parse_public_rss,normalize_articles
    body='<rss><channel><item><title>合成测试：交易所暂停提现</title><link>https://www.panewslab.com/zh/articles/test</link><pubDate>Fri, 30 Oct 2026 03:00:00 GMT</pubDate><description>&lt;p&gt;中文来源摘要，不是真实事件。&lt;/p&gt;</description></item></channel></rss>'.encode()
    result=normalize_articles(parse_public_rss(body,'PANews')['articles'],'panews')
    assert result[0]['publisher']=='PANews'
    assert result[0]['title']=='合成测试：交易所暂停提现'
    assert result[0]['description']=='中文来源摘要，不是真实事件。'
    assert result[0]['published_at']=='2026-10-30T03:00:00+00:00'


def test_chinese_aggregate_keeps_feed_kind_publishers_and_independent_failure_cache(db):
    from app.services.chinese_news_sources import SOURCES
    stamp=[datetime(2026,10,30,3,tzinfo=timezone.utc)];failed=set()
    def fetch(url,headers):
        if url in failed:raise NewsFeedError('news_source_unavailable')
        source,kind=next((name,kind) for name,feeds in SOURCES.items() for kind in ('flash','article') if feeds[kind]==url)
        return {'status':'ok','articles':[article(title=f'{source} {kind} 独立材料',url=f'https://example.com/{source}/{kind}')]}
    service=NewsFeedService(db,'aggregate-user',fetch=fetch,now=lambda:stamp[0])
    service.configure({'provider':'chinese_aggregate','sources':['panews','odaily']})
    first=service.refresh()
    assert len(first['articles'])==4
    assert {row['kind'] for row in first['articles']}=={'flash','article'}
    assert {row['publisher'] for row in first['articles']}=={'PANews','Odaily 星球日报'}
    assert len(first['source_status'])==4 and first['errors_count']==0
    old_time=next(row['fetched_at'] for row in first['source_status'] if row['id']=='odaily:article')
    failed.add(SOURCES['odaily']['article']);stamp[0]+=timedelta(seconds=61)
    second=service.refresh()
    assert second['status']=='ready' and second['errors_count']==1
    assert len(second['articles'])==4  # Only the failed feed retains its old materials.
    feed=next(row for row in second['source_status'] if row['id']=='odaily:article')
    assert feed['status']=='error' and feed['fetched_at']==old_time
    assert feed['age_seconds']==61
    failed.update(SOURCES[source][kind] for source in ('panews','odaily') for kind in ('flash','article'))
    stamp[0]+=timedelta(seconds=121)
    third=service.refresh()
    assert third['status']=='error' and len(third['articles'])==4
    assert all(row['stale'] for row in third['source_status'])
    from app.services.research_chat_context import load_news_context
    context=load_news_context(db,'aggregate-user')
    assert all(row['source_refresh_failed'] and row['source_stale'] for row in context['articles'])
    assert NewsFeedService(db,'another').latest()['articles']==[]


@pytest.mark.parametrize('sources',[[],['unknown'],['panews','panews'],'panews',[None]])
def test_aggregate_source_settings_are_fixed_catalog_only(db,sources):
    with pytest.raises(NewsFeedError):NewsFeedService(db,'aggregate-user').configure({'sources':sources})
