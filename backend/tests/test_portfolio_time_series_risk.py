from datetime import datetime
from datetime import timedelta
from datetime import timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.adapters.types import AdapterCandle
from app.adapters.market_data_readonly import YahooFinancePublicMarketDataAdapter
from app.db.session import get_db
from app.main import app
from app.models import Reminder
from app.services.portfolio_time_series_risk import PortfolioTimeSeriesRiskService
from app.services.portfolio_time_series_risk import risk_change_evidence


def synthetic_candles(symbol: str, count: int) -> list[AdapterCandle]:
    symbol_offset = sum(ord(character) for character in symbol) % 13
    start = datetime.now(timezone.utc) - timedelta(days=count - 1)
    rows = []
    price = 100.0 + symbol_offset
    for index in range(count):
        daily_move = 0.001 + ((index + symbol_offset) % 9 - 4) * 0.0015
        price *= 1 + daily_move
        rows.append(
            AdapterCandle(
                symbol=symbol,
                timeframe="1d",
                timestamp=start + timedelta(days=index),
                open=price * 0.998,
                high=price * 1.006,
                low=price * 0.994,
                close=price,
                volume=1_000_000 + index * 1000,
                source="yfinance_public",
            )
        )
    return rows


def test_risk_change_evidence_requires_a_prior_artifact_and_detects_material_changes() -> None:
    baseline = risk_change_evidence(None, {"weights": {"AAPL": 0.5}, "correlation_matrix": {}, "drawdown": {"budget_used_pct": 20}}, previous_artifact_id=None)
    assert baseline["status"] == "baseline_created"
    assert baseline["concentration"]["alert"] is False

    changed = risk_change_evidence(
        {
            "weights": {"AAPL": 0.45, "SPY": 0.55},
            "correlation_matrix": {"AAPL": {"AAPL": 1, "SPY": 0.55}, "SPY": {"AAPL": 0.55, "SPY": 1}},
            "drawdown": {"budget_used_pct": 65},
        },
        {
            "weights": {"AAPL": 0.55, "SPY": 0.45},
            "correlation_matrix": {"AAPL": {"AAPL": 1, "SPY": 0.78}, "SPY": {"AAPL": 0.78, "SPY": 1}},
            "drawdown": {"budget_used_pct": 82},
        },
        previous_artifact_id="prior-risk-artifact",
    )
    assert changed["status"] == "compared"
    assert changed["previous_artifact_id"] == "prior-risk-artifact"
    assert changed["concentration"]["alert"] is True
    assert changed["concentration"]["top_change"]["symbol"] == "AAPL"
    assert changed["correlation"]["alert"] is True
    assert changed["drawdown_budget"]["alert"] is True


def test_risk_reminders_dedupe_and_auto_resolve_when_condition_clears(client: TestClient) -> None:
    session_gen = app.dependency_overrides[get_db]()
    db = next(session_gen)
    try:
        service = PortfolioTimeSeriesRiskService(db)
        packet = {
            "drawdown": {"budget_used_pct": 20},
            "var": {"historical_95": {"var_pct": 1}},
            "liquidity_summary": {"max_stressed_days": 1},
            "high_correlation_pairs": [],
            "risk_changes": {
                "concentration": {"alert": True, "detail": "AAPL weight increased 10.0 percentage points to 55.0%."},
                "correlation": {"alert": False},
                "drawdown_budget": {"alert": False},
            },
        }
        service._upsert_risk_reminders("default-user", "artifact-1", packet)
        service._upsert_risk_reminders("default-user", "artifact-2", packet)
        db.commit()
        reminders = list(db.scalars(select(Reminder).where(Reminder.reminder_type == "portfolio_risk")).all())
        assert len(reminders) == 1
        assert reminders[0].payload_json["artifact_id"] == "artifact-2"
        assert reminders[0].payload_json["condition_active"] is True

        packet["risk_changes"]["concentration"] = {"alert": False, "detail": "No threshold crossed."}
        service._upsert_risk_reminders("default-user", "artifact-3", packet)
        db.commit()
        db.refresh(reminders[0])
        assert reminders[0].status == "done"
        assert reminders[0].payload_json["condition_active"] is False
        assert reminders[0].payload_json["resolved_by_artifact_id"] == "artifact-3"
    finally:
        session_gen.close()


def test_portfolio_time_series_risk_api_and_today_queue(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(
        YahooFinancePublicMarketDataAdapter,
        "get_candles",
        lambda self, symbol, timeframe, limit: synthetic_candles(symbol, min(limit, 90)),
    )
    assert client.post("/mock/import-positions").status_code == 200
    assert client.post("/mock/update-quotes").status_code == 200
    assets = client.get("/assets").json()
    for asset in assets:
        if asset["symbol"] == "AAPL":
            classified = client.patch(
                f"/assets/{asset['id']}/classification",
                json={"sector": "Information Technology", "industry": "Technology Hardware", "themes_json": ["AI", "Consumer Devices"], "factor_tags_json": ["Quality", "Large Cap"], "classification_source": "manual_reviewed"},
            )
            assert classified.status_code == 200
        if asset["symbol"] == "SPY":
            unproven = client.patch(
                f"/assets/{asset['id']}/classification",
                json={"sector": "Broad Market", "themes_json": ["Index"], "factor_tags_json": ["Market Beta"], "classification_source": "external_provider"},
            )
            assert unproven.status_code == 422
            assert "trusted source snapshot" in unproven.json()["detail"]

    sync_response = client.post(
        "/portfolio-risk/time-series/sync-market-data",
        json={"lookback_days": 90, "sync_market_data": True, "drawdown_budget_pct": 0.01},
    )
    assert sync_response.status_code == 200, sync_response.text
    sync_packet = sync_response.json()
    assert sync_packet["status"] == "promotion_required"
    assert sync_packet["promotion_stage"] == "raw"
    entry_id = sync_packet["catalog_entry_id"]
    assert client.post(f"/data-catalog/entries/{entry_id}/promote").json()["current_stage"] == "reviewed"
    assert client.post(f"/data-catalog/entries/{entry_id}/promote").json()["current_stage"] == "trusted"

    response = client.post(
        "/portfolio-risk/time-series/sync-and-run",
        json={
            "lookback_days": 90,
            "sync_market_data": False,
            "drawdown_budget_pct": 0.01,
            "data_snapshot_ids": [sync_packet["snapshot_id"]],
        },
    )

    assert response.status_code == 200, response.text
    packet = response.json()
    assert packet["provider"] == "yfinance_public"
    assert packet["observations"] >= 60
    assert packet["coverage_pct"] > 90
    assert packet["var"]["historical_95"]["var_pct"] >= 0
    assert packet["drawdown"]["budget_used_pct"] is not None
    assert packet["correlation_matrix"]
    assert packet["liquidity"]
    assert packet["stress_tests"]
    assert packet["exposures"]["by_currency"]
    assert packet["exposures"]["by_market"]
    assert any(item["name"] == "Information Technology" for item in packet["exposures"]["by_sector"])
    assert any(item["name"] == "AI" for item in packet["exposures"]["by_theme"])
    assert packet["exposures"]["classification_coverage_pct"] > 0
    assert packet["exposures"]["classification_sources"] == ["manual_reviewed"]
    assert packet["factor_proxies"]["by_symbol"]
    assert packet["factor_proxies"]["named_factor_model_available"] is False
    assert packet["external_exposures"]["exchanges"] == []
    assert packet["local_next_steps"]
    assert packet["risk_gate"]["can_review_portfolio_risk"] is True
    assert packet["risk_gate"]["can_create_today_queue_alerts"] is True
    assert packet["risk_gate"]["can_open_risk_drilldown"] is True
    assert packet["risk_gate"]["can_unlock_order_approval"] is False
    assert packet["risk_gate"]["can_execute_trades"] is False
    assert packet["execution_available"] is False
    assert packet["input_data_snapshot_ids"] == [sync_packet["snapshot_id"]]

    latest = client.get("/portfolio-risk/time-series/latest")
    assert latest.status_code == 200
    assert latest.json()["artifact_id"] == packet["artifact_id"]

    evidence = client.post("/portfolio-risk/time-series/evidence-packet")
    assert evidence.status_code == 200
    evidence_packet = evidence.json()
    assert evidence_packet["packet_type"] == "portfolio_time_series_risk_evidence_packet"
    assert evidence_packet["status"] == "ready_for_risk_review"
    assert evidence_packet["latest_risk_artifact_id"] == packet["artifact_id"]
    assert evidence_packet["snapshot_id"] == packet["snapshot_id"]
    assert evidence_packet["quality_report_id"] == packet["quality_report_id"]
    assert evidence_packet["metrics_available"]["var"] is True
    assert evidence_packet["metrics_available"]["correlation_matrix"] is True
    assert evidence_packet["local_next_steps"][0]["key"] == "time_series"
    assert evidence_packet["risk_gate"]["can_review_portfolio_risk"] is True
    assert evidence_packet["risk_gate"]["can_unlock_order_approval"] is False
    assert evidence_packet["risk_gate"]["execution_available"] is False
    assert evidence_packet["contains_secrets"] is False
    assert evidence_packet["execution_available"] is False
    assert evidence_packet["production_capability"] is False
    assert "no orders" in evidence_packet["safe_boundary"].lower()

    queue = client.get("/daily-use/action-queue?source=portfolio_risk&limit=100")
    assert queue.status_code == 200
    actions = queue.json()["actions"]
    assert actions
    assert all(item["execution_available"] is False for item in actions)


def test_portfolio_risk_blocks_raw_snapshot_before_calculation(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(
        YahooFinancePublicMarketDataAdapter,
        "get_candles",
        lambda self, symbol, timeframe, limit: synthetic_candles(symbol, min(limit, 90)),
    )
    assert client.post("/mock/import-positions").status_code == 200
    assert client.post("/mock/update-quotes").status_code == 200
    synced = client.post(
        "/portfolio-risk/time-series/sync-market-data",
        json={"lookback_days": 90},
    ).json()

    blocked = client.post(
        "/portfolio-risk/time-series/sync-and-run",
        json={"lookback_days": 90, "sync_market_data": False, "data_snapshot_ids": [synced["snapshot_id"]]},
    )

    assert blocked.status_code == 422
    assert "promotion_stage_not_trusted" in blocked.json()["detail"]
    assert client.get("/portfolio-risk/time-series/latest").status_code == 404


def test_portfolio_time_series_risk_evidence_packet_marks_missing_latest(client: TestClient) -> None:
    evidence = client.post("/portfolio-risk/time-series/evidence-packet")

    assert evidence.status_code == 200
    packet = evidence.json()
    assert packet["status"] == "action_required"
    assert packet["latest_risk"] is None
    assert packet["missing"] == ["portfolio_time_series_risk"]
    assert packet["local_next_steps"]
    assert packet["risk_gate"]["status"] == "action_required"
    assert packet["risk_gate"]["can_review_portfolio_risk"] is False
    assert packet["risk_gate"]["can_unlock_order_approval"] is False
    assert packet["execution_available"] is False
    assert packet["production_capability"] is False
