import json

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import DataCatalogEntry, DataSnapshot, ExportArtifact
from app.services.research_feeds import ResearchFeedService
from app.services.research_feeds import detect_evidence_conflicts


@pytest.fixture()
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)


def test_news_and_sec_feeds_persist_cited_research_evidence(db):
    def fetch(url, headers, timeout):
        if "articlebysymbol" in url:
            return json.dumps({"data": {"rows": [{"title": "Apple update", "description": "Structured news fact", "publisher": "Publisher", "created": "Jun 20, 2026", "url": "/articles/apple-update", "related_symbols": ["aapl|stocks"]}]}})
        if "company_tickers" in url:
            return json.dumps({"0": {"ticker": "AAPL", "cik_str": 320193}})
        if "submissions" in url:
            return json.dumps({"name": "Apple Inc.", "filings": {"recent": {"form": ["10-Q"], "accessionNumber": ["0001-26-000001"], "filingDate": ["2026-05-01"], "reportDate": ["2026-03-31"], "primaryDocument": ["aapl-10q.htm"]}}})
        if "companyfacts" in url:
            return json.dumps({"entityName": "Apple Inc.", "facts": {"us-gaap": {"Revenues": {"units": {"USD": [{"val": 100, "filed": "2026-05-01", "end": "2026-03-31", "form": "10-Q", "accn": "0001-26-000001"}]}}}}})
        raise AssertionError(url)

    service = ResearchFeedService(db, fetch_text=fetch)
    news = service.sync_nasdaq_news(symbols=["AAPL"])
    sec = service.sync_sec_filings_and_fundamentals(symbols=["AAPL"])

    assert news["row_count"] == 1
    assert news["data"]["articles"][0]["url"].startswith("https://www.nasdaq.com/")
    assert sec["data"]["filings"][0]["form"] == "10-Q"
    assert sec["data"]["fundamentals"][0]["facts"]["revenue"]["value"] == 100
    assert db.scalar(select(func.count()).select_from(DataCatalogEntry)) == 2


def test_macro_and_onchain_feeds_keep_time_series(db):
    def fetch(url, headers, timeout):
        if "fredgraph" in url:
            series_id = url.split("id=")[-1]
            return f"observation_date,{series_id}\n2026-06-18,4.4\n2026-06-19,4.5\n"
        return json.dumps({"name": "Confirmed Transactions", "unit": "Transactions", "period": "day", "values": [{"x": 1, "y": 100}, {"x": 2, "y": 110}]})

    service = ResearchFeedService(db, fetch_text=fetch)
    macro = service.sync_fred_macro(series=["DGS10"])
    onchain = service.sync_onchain_metrics(metrics=["n-transactions"])

    assert macro["data"]["series"]["DGS10"][-1]["value"] == 4.5
    assert onchain["data"]["metrics"]["n-transactions"]["values"][-1]["y"] == 110


def test_duplicate_macro_observations_are_exposed_as_conflicting_evidence(db):
    snapshot = DataSnapshot(
        snapshot_type="macro_series",
        data_json={"series": {"DGS10": [{"date": "2026-06-19", "value": 4.4}, {"date": "2026-06-19", "value": 4.5}]}},
        metadata_json={"provider": "fred_public_csv"},
    )
    db.add(snapshot); db.commit()
    conflicts = detect_evidence_conflicts([snapshot], symbol="AAPL")
    assert len(conflicts) == 1
    assert conflicts[0]["entity"] == "MACRO"
    assert conflicts[0]["field"] == "DGS10"
    assert conflicts[0]["deterministic_conclusion_allowed"] is False


def test_catalyst_calendar_combines_earnings_and_dividends(db):
    corporate = DataSnapshot(snapshot_type="corporate_actions", data_json={"events": [{"symbol": "AAPL", "ex_date": "06/22/2026", "payment_date": "06/25/2026", "amount_per_share": 0.27}]}, metadata_json={})
    db.add(corporate); db.commit()

    service = ResearchFeedService(db, fetch_text=lambda url, headers, timeout: json.dumps({"data": {"rows": [{"symbol": "AAPL", "time": "after-hours", "fiscalQuarterEnding": "Jun/2026", "epsForecast": "1.5"}]}}))
    result = service.sync_catalyst_calendar(symbols=["AAPL"], days=7)

    assert any(item["event_type"] == "earnings" for item in result["data"]["events"])
    assert result["quality_status"] == "VALID"


def test_research_feed_overview_marks_missing_and_ready(db):
    service = ResearchFeedService(db, fetch_text=lambda *_: "")
    before = service.overview()
    assert before["ready_count"] == 0
    assert before["status"] == "action_required"
    assert "news" in before["missing"]
    assert before["execution_available"] is False
    assert [step["key"] for step in before["local_next_steps"]] == [
        "news",
        "sec_filings_fundamentals",
        "macro_series",
        "onchain_metrics",
        "catalyst_calendar",
        "evidence_packet",
    ]
    assert before["thesis_gate"]["status"] == "blocked"
    assert before["thesis_gate"]["can_create_trade_plan"] is False
    assert before["thesis_gate"]["can_unlock_order_approval"] is False
    db.add(DataSnapshot(snapshot_type="news", data_json={"articles": []}, metadata_json={"provider": "test", "row_count": 0}))
    db.commit()
    after = service.overview()
    assert after["ready_count"] == 1
    assert after["items"][0]["label"] == "新闻证据"


def test_empty_catalyst_window_is_valid_evidence_not_a_failure(db):
    service = ResearchFeedService(db, fetch_text=lambda *_: json.dumps({"data": {"rows": []}}))
    result = service.sync_catalyst_calendar(symbols=["AAPL"], days=2)
    assert result["row_count"] == 0
    assert result["quality_status"] == "VALID"
    assert result["data"]["events"] == []


def test_research_feed_evidence_packet_is_redacted_and_review_only(db):
    db.add(DataSnapshot(snapshot_type="news", data_json={"articles": [{"title": "AAPL fact"}]}, metadata_json={"provider": "test_news", "row_count": 1}))
    db.commit()
    service = ResearchFeedService(db, fetch_text=lambda *_: "")

    packet = service.evidence_packet(user_id="user-1")
    serialized = json.dumps(packet)

    assert packet["packet_type"] == "research_feed_evidence_packet"
    assert packet["ready_count"] == 1
    assert packet["contains_secrets"] is False
    assert packet["production_capability"] is False
    assert packet["execution_available"] is False
    assert "sk-" not in serialized.lower()
    assert "api_key" not in serialized.lower()
    artifact = db.get(ExportArtifact, packet["artifact_id"])
    assert artifact is not None
    assert artifact.export_type == "research_feed_evidence_packet"


def test_research_feed_thesis_gate_ready_does_not_unlock_plans_or_orders(db):
    for dataset_type in ["news", "sec_filings_fundamentals", "macro_series", "onchain_metrics", "catalyst_calendar"]:
        db.add(DataSnapshot(snapshot_type=dataset_type, data_json={"rows": [{"id": dataset_type}]}, metadata_json={"provider": "test", "row_count": 1}))
    db.commit()
    service = ResearchFeedService(db, fetch_text=lambda *_: "")

    overview = service.overview()

    assert overview["status"] == "ready_for_thesis_review"
    assert overview["thesis_gate"]["status"] == "ready_for_thesis_review"
    assert overview["thesis_gate"]["can_open_research_report"] is True
    assert overview["thesis_gate"]["can_create_thesis_delta"] is True
    assert overview["thesis_gate"]["can_create_trade_plan"] is False
    assert overview["thesis_gate"]["can_unlock_order_approval"] is False
    assert overview["local_next_steps"][-1]["status"] == "ready"


def test_latest_news_reports_missing_without_network(db):
    def unexpected(*args):
        raise AssertionError("cached read must not fetch")
    result = ResearchFeedService(db, fetch_text=unexpected).latest_news()
    assert result["status"] == "missing"
    assert result["articles"] == []
    assert result["stale"] is True
    assert result["fetched_at"] is None


def test_latest_news_preserves_publication_time_and_exposes_stale_partial_snapshot(db):
    from datetime import datetime, timedelta, timezone
    created = datetime.now(timezone.utc) - timedelta(minutes=10)
    article = {"title": "Fixture", "published_at": "Jun 20, 2026", "url": "https://www.nasdaq.com/articles/fixture"}
    db.add(DataSnapshot(snapshot_type="news", created_at=created, data_json={"articles": [article], "errors": [{"symbol": "OTHER", "error": "unavailable"}]}, metadata_json={"provider": "nasdaq_public_news"}))
    db.commit()
    result = ResearchFeedService(db).latest_news()
    assert result["status"] == "partial"
    assert result["stale"] is True
    assert result["age_seconds"] >= 600
    assert result["articles"] == [article]
    assert result["errors_count"] == 1
    assert "errors" not in result
    assert result["fetched_at"] != article["published_at"]
