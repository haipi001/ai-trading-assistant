"""Thesis-delta report: what changed since the thesis was last reviewed.

Built only from locally stored evidence (candles + already synced research
feed snapshots). Fail-closed: missing candles and never-synced feeds are
reported as such; feeds synced before the baseline are stale. Review-only —
the human records the checkpoint verdict.
"""

from datetime import datetime
from datetime import timedelta
from datetime import timezone

from fastapi.testclient import TestClient

from app.db.session import get_db
from app.main import app
from app.models import Candle
from app.models import DataSnapshot


def _db_session():
    generator = app.dependency_overrides[get_db]()
    return generator, next(generator)


def _close(generator):
    try:
        next(generator)
    except StopIteration:
        pass


def create_asset(client: TestClient, symbol: str = "NVDA") -> dict:
    response = client.post(
        "/assets",
        json={
            "symbol": symbol,
            "name": f"{symbol} Corp.",
            "asset_type": "stock",
            "market": "US",
            "venue": "NASDAQ",
            "currency": "USD",
            "tradable": True,
            "manual_enabled": True,
            "auto_enabled": False,
            "risk_level": "medium",
        },
    )
    assert response.status_code == 201
    return response.json()


def create_thesis(client: TestClient, asset_id: str) -> dict:
    response = client.post(
        "/investment-theses",
        json={
            "user_id": "user-1",
            "asset_id": asset_id,
            "entry_reason": "Data center growth drives revenue.",
            "key_drivers_json": {"items": ["data center growth"]},
            "invalidation_conditions_json": {"items": ["growth decelerates"]},
            "expected_horizon": "long_term",
            "target_condition": "Hold while valid.",
            "max_loss_tolerance_pct": 0.2,
            "position_plan_json": {"sizing": "core"},
            "confidence": 0.75,
            "source": "manual",
            "status": "active",
        },
    )
    assert response.status_code == 201
    return response.json()


def insert_candle(asset_id: str, close: float, at: datetime) -> None:
    generator, db = _db_session()
    try:
        db.add(
            Candle(
                asset_id=asset_id,
                timeframe="1d",
                timestamp=at,
                open=close,
                high=close,
                low=close,
                close=close,
                volume=1000,
                source="test_thesis_delta",
            )
        )
        db.commit()
    finally:
        db.close()
        _close(generator)


def insert_snapshot(snapshot_type: str, data_json: dict) -> None:
    generator, db = _db_session()
    try:
        db.add(DataSnapshot(snapshot_type=snapshot_type, data_json=data_json, metadata_json={"provider": "test"}))
        db.commit()
    finally:
        db.close()
        _close(generator)


def test_thesis_delta_flags_price_pressure_and_new_facts(client: TestClient) -> None:
    asset = create_asset(client)
    now = datetime.now(timezone.utc)
    # Baseline candle before the thesis; a -30% candle after it (tolerance is 20%).
    insert_candle(asset["id"], 100.0, now - timedelta(days=1))
    thesis = create_thesis(client, asset["id"])
    insert_candle(asset["id"], 70.0, now + timedelta(hours=1))
    tomorrow = (now + timedelta(days=1)).date().isoformat()
    # Feed snapshots synced after the thesis -> fresh, with symbol-relevant facts.
    insert_snapshot("news", {"articles": [{"symbol": "NVDA", "title": "NVDA ships new chip", "publisher": "T", "published_at": tomorrow, "url": "https://example.com", "related_symbols": []}], "claims": [{"entity": "NVDA", "field": "forward_revenue", "as_of": tomorrow, "value": 10, "source": "Publisher T", "source_url": "https://example.com"}]})
    insert_snapshot("sec_filings_fundamentals", {"filings": [{"symbol": "NVDA", "form": "8-K", "filing_date": tomorrow, "url": "https://example.com/8k"}], "fundamentals": [{"symbol": "NVDA", "facts": {"Revenues": 1}}], "claims": [{"entity": "NVDA", "field": "forward_revenue", "as_of": tomorrow, "value": 9, "source": "SEC filing", "source_url": "https://example.com/8k"}]})

    response = client.get(f"/research-feeds/thesis-delta/{thesis['id']}")
    assert response.status_code == 200
    report = response.json()

    assert report["review_only"] is True
    assert report["execution_available"] is False
    assert report["baseline_source"] == "thesis_created"
    price = report["price_delta"]
    assert price["baseline_close"] == 100.0
    assert price["latest_close"] == 70.0
    assert price["max_loss_tolerance_breached"] is True
    assert "max_loss_tolerance_pressure" in report["flags"]
    assert "new_sec_filings_since_baseline" in report["flags"]
    assert report["feeds"]["news"]["status"] == "fresh"
    assert report["feeds"]["news"]["new_items_for_symbol"] == 1
    assert report["feeds"]["sec_filings_fundamentals"]["new_filings_since_baseline"][0]["form"] == "8-K"
    assert report["feeds"]["sec_filings_fundamentals"]["source_credibility"]["tier"] == "primary_official"
    assert report["feeds"]["news"]["source_credibility"]["human_review_required"] is True
    assert report["conflict_count"] == 1
    assert report["evidence_conflicts"][0]["field"] == "forward_revenue"
    assert report["evidence_conflicts"][0]["deterministic_conclusion_allowed"] is False
    assert "conflicting_evidence" in report["flags"]
    assert {item["type"] for item in report["evidence_timeline"]} >= {"news", "sec_filing"}
    # Feeds never synced are honestly missing, not silently empty.
    assert report["feeds"]["macro_series"]["status"] == "missing"
    assert client.get("/orders/drafts").json() == []


def test_thesis_delta_is_fail_closed_without_evidence(client: TestClient) -> None:
    asset = create_asset(client, symbol="AMD")
    thesis = create_thesis(client, asset["id"])

    response = client.get(f"/research-feeds/thesis-delta/{thesis['id']}")
    assert response.status_code == 200
    report = response.json()

    assert report["price_delta"] is None
    assert "no_local_candles" in report["flags"]
    assert all(feed["status"] in {"missing", "stale_since_baseline"} for feed in report["feeds"].values())
    assert any("Re-sync" in action or "Import" in action for action in report["next_actions"])

    missing = client.get("/research-feeds/thesis-delta/does-not-exist")
    assert missing.status_code == 404


def test_thesis_delta_marks_pre_baseline_snapshots_stale(client: TestClient) -> None:
    asset = create_asset(client, symbol="MSFT")
    # Snapshot synced BEFORE the thesis exists -> stale relative to the baseline.
    insert_snapshot("news", {"articles": [{"symbol": "MSFT", "title": "old news", "publisher": "T", "published_at": "2020-01-01", "url": "https://example.com", "related_symbols": []}]})
    thesis = create_thesis(client, asset["id"])

    report = client.get(f"/research-feeds/thesis-delta/{thesis['id']}").json()
    assert report["feeds"]["news"]["status"] == "stale_since_baseline"
