"""Isolated browser fixture: memory DB, temporary secrets, no network fallback."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.core import local_secrets
from app.core.auth import AuthenticatedUser
from app.models import LocalUserConfig
from app.api.news_feed import router, production_user, get_db
from app.services import news_feed

KEY = 'fixture-news-key-123'
requests = []

def fixture_fetch(url, headers):
    parsed = urlsplit(url)
    assert parsed.netloc == 'newsapi.org' and parsed.path == '/v2/everything'
    assert headers.get('X-Api-Key') == KEY
    assert KEY not in url
    requests.append({'host': parsed.netloc, 'path': parsed.path, 'key_in_url': False})
    return {'status': 'ok', 'articles': [
        {'title': '合成验收数据：BTC ETF 测试消息', 'url': 'https://example.com/fixture-etf', 'publishedAt': '2026-10-29T15:00:00Z', 'source': {'name': '合成验收来源 A'}, 'description': '仅用于隔离浏览器测试，不是真实市场消息。'},
        {'title': '合成验收数据：宏观 CPI 测试消息', 'url': 'https://example.com/fixture-macro', 'publishedAt': '2026-10-29T14:00:00Z', 'source': {'name': '合成验收来源 B'}, 'description': 'Fixture summary; this is synthetic test data.'},
    ]}

if __name__ == '__main__':
    with TemporaryDirectory(prefix='news-browser-fixture-') as directory:
        local_secrets.store_path = lambda: Path(directory) / 'credentials.env'
        news_feed.fetch_news_json = fixture_fetch
        engine = create_engine('sqlite:///:memory:', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        LocalUserConfig.__table__.create(engine)
        app = FastAPI(title='Isolated news browser fixture')
        app.add_middleware(CORSMiddleware, allow_origins=['http://127.0.0.1:3003','http://localhost:3003'], allow_methods=['GET','POST','PUT'], allow_headers=['Content-Type'], allow_credentials=True)
        app.include_router(router)
        def fixture_db():
            with Session(engine) as session:
                yield session
        app.dependency_overrides[get_db] = fixture_db
        app.dependency_overrides[production_user] = lambda: AuthenticatedUser('news-browser-fixture','owner',['readiness:read','secrets:write'],True,True)
        @app.get('/health/status')
        def health():
            return {'status':'ok','service':'isolated-news-browser-fixture','fixture':True}
        @app.get('/fixture/status')
        def status():
            return {'requests': requests, 'fixture':True}
        uvicorn.run(app,host='127.0.0.1',port=8002,access_log=False)
