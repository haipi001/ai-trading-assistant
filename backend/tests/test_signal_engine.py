from datetime import datetime
from datetime import timedelta
from datetime import timezone

from app.db.session import get_db
from app.main import app
from app.models import Candle


def create_asset(client) -> str:
    response = client.post(
        "/assets",
        json={
            "symbol": "AAPL",
            "name": "Apple Inc.",
            "asset_type": "stock",
            "market": "US",
            "venue": "NASDAQ",
            "currency": "USD",
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def create_account(client) -> str:
    response = client.post(
        "/accounts",
        json={
            "name": "stock_paper_account",
            "account_type": "brokerage",
            "broker": "mock_stock",
            "base_currency": "USD",
            "mode": "paper",
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def insert_candles(client, asset_id: str, *, timeframe: str, closes: list[float]) -> None:
    db_generator = app.dependency_overrides[get_db]()
    db = next(db_generator)
    try:
        base_timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
        step = timedelta(hours=1) if timeframe == "1h" else timedelta(days=1)
        for index, close in enumerate(closes):
            db.add(
                Candle(
                    asset_id=asset_id,
                    timeframe=timeframe,
                    timestamp=base_timestamp + step * index,
                    open=close,
                    high=close * 1.01,
                    low=close * 0.99,
                    close=close,
                    volume=1000 + index * 100,
                    source="test_fixture",
                )
            )
        db.commit()
    finally:
        db.close()
        try:
            next(db_generator)
        except StopIteration:
            pass


def test_rsi_signal_generation(client):
    asset_id = create_asset(client)
    candles = [{"close": close} for close in [100, 98, 96, 94, 92, 90, 88, 86]]

    response = client.post(
        "/signals/generate",
        json={"asset_id": asset_id, "signal_types": ["rsi"], "candles": candles, "horizon": "swing"},
    )

    assert response.status_code == 201
    signal = response.json()[0]
    assert signal["asset_id"] == asset_id
    assert signal["signal_type"] == "rsi"
    assert signal["direction"] == "bullish"
    assert 0 <= signal["strength"] <= 100
    assert signal["suggested_action"] == "watch"
    assert "rsi" in signal["evidence"]


def test_ma_cross_signal_generation(client):
    asset_id = create_asset(client)
    candles = [{"close": close} for close in [10, 10, 10, 8, 8, 20]]

    response = client.post(
        "/signals/generate",
        json={"asset_id": asset_id, "signal_types": ["ma_cross"], "candles": candles, "horizon": "swing"},
    )

    assert response.status_code == 201
    signal = response.json()[0]
    assert signal["signal_type"] == "ma_cross"
    assert signal["direction"] == "bullish"
    assert signal["suggested_action"] == "draft_buy"
    assert signal["evidence"]["short_window"] == 3
    assert signal["evidence"]["long_window"] == 5


def test_signal_does_not_create_order_by_default(client):
    asset_id = create_asset(client)
    response = client.post(
        "/signals/generate",
        json={"asset_id": asset_id, "signal_types": ["ma_cross"], "candles": [{"close": close} for close in [10, 10, 10, 8, 8, 20]]},
    )
    assert response.status_code == 201
    signal_id = response.json()[0]["id"]

    blocked_response = client.post(
        f"/signals/{signal_id}/create-order-intent",
        json={"account_id": "account-1"},
    )

    assert blocked_response.status_code == 403
    audit_logs = client.get("/audit-logs").json()
    assert any(log["action"] == "signal.order_intent_blocked" for log in audit_logs)
    assert not any(log["action"] == "signal.order_intent_created" for log in audit_logs)


def test_signal_creates_order_intent_only_when_allowed(client):
    asset_id = create_asset(client)
    account_id = create_account(client)
    response = client.post(
        "/signals/generate",
        json={"asset_id": asset_id, "signal_types": ["ma_cross"], "candles": [{"close": close} for close in [10, 10, 10, 8, 8, 20]]},
    )
    assert response.status_code == 201
    signal_id = response.json()[0]["id"]

    order_response = client.post(
        f"/signals/{signal_id}/create-order-intent",
        json={
            "account_id": account_id,
            "automation_level": "A3_ORDER_DRAFT",
            "signal_order_intents_enabled": True,
            "notional": 1000,
        },
    )

    assert order_response.status_code == 201
    order_intent = order_response.json()
    assert order_intent["source_type"] == "signal"
    assert order_intent["source_id"] == signal_id
    assert order_intent["asset_id"] == asset_id
    assert order_intent["account_id"] == account_id
    assert order_intent["side"] == "buy"
    assert order_intent["status"] == "created"
    assert client.get("/orders/drafts").json() == []
    assert any(log["action"] == "signal.order_intent_created" for log in client.get("/audit-logs").json())


def test_signal_uses_stored_daily_candles_when_request_omits_them(client):
    asset_id = create_asset(client)
    insert_candles(client, asset_id, timeframe="1d", closes=[100, 98, 96, 94, 92, 90, 88, 86])

    response = client.post(
        "/signals/generate",
        json={"asset_id": asset_id, "signal_types": ["rsi"], "horizon": "swing"},
    )

    assert response.status_code == 201
    signal = response.json()[0]
    assert signal["direction"] == "bullish"
    assert signal["evidence"]["input"]["source"] == "stored_candles"
    assert signal["evidence"]["input"]["timeframe"] == "1d"
    assert signal["evidence"]["input"]["candle_count"] == 8
    assert "rsi" in signal["evidence"]


def test_intraday_signal_prefers_stored_hourly_candles(client):
    asset_id = create_asset(client)
    insert_candles(client, asset_id, timeframe="1d", closes=[20, 20, 20, 20, 20, 20])
    insert_candles(client, asset_id, timeframe="1h", closes=[10, 10, 10, 8, 8, 20])

    response = client.post(
        "/signals/generate",
        json={"asset_id": asset_id, "signal_types": ["ma_cross"], "horizon": "intraday"},
    )

    assert response.status_code == 201
    signal = response.json()[0]
    assert signal["direction"] == "bullish"
    assert signal["suggested_action"] == "draft_buy"
    assert signal["evidence"]["input"]["source"] == "stored_candles"
    assert signal["evidence"]["input"]["timeframe"] == "1h"
    assert signal["evidence"]["input"]["candle_count"] == 6


def test_signal_review_queue_marks_missing_thesis_for_actionable_signal(client):
    asset_id = create_asset(client)
    response = client.post(
        "/signals/generate",
        json={"asset_id": asset_id, "signal_types": ["ma_cross"], "candles": [{"close": close} for close in [10, 10, 10, 8, 8, 20]], "horizon": "swing"},
    )
    assert response.status_code == 201

    queue_response = client.get("/signals/review-queue")
    assert queue_response.status_code == 200
    queue = queue_response.json()
    assert len(queue) == 1
    item = queue[0]
    assert item["asset_symbol"] == "AAPL"
    assert item["review_status"] == "needs_thesis_review"
    assert item["has_active_thesis"] is False
    assert item["suggested_action"] == "draft_buy"


def test_signal_review_queue_marks_ready_when_active_thesis_exists(client):
    asset_id = create_asset(client)
    account_id = create_account(client)
    thesis_response = client.post(
        "/investment-theses",
        json={
            "user_id": "default-user",
            "asset_id": asset_id,
            "entry_reason": "Test thesis",
            "key_drivers_json": {"driver": "earnings growth"},
            "invalidation_conditions_json": {"invalid": "growth breaks"},
            "expected_horizon": "swing",
            "target_condition": "momentum confirms",
            "max_loss_tolerance_pct": 0.1,
            "position_plan_json": {"sizing": "starter"},
            "confidence": 0.7,
            "source": "manual",
            "status": "active",
        },
    )
    assert thesis_response.status_code == 201

    response = client.post(
        "/signals/generate",
        json={"asset_id": asset_id, "signal_types": ["ma_cross"], "candles": [{"close": close} for close in [10, 10, 10, 8, 8, 20]], "horizon": "swing"},
    )
    assert response.status_code == 201

    queue_response = client.get("/signals/review-queue")
    assert queue_response.status_code == 200
    queue = queue_response.json()
    assert len(queue) == 1
    item = queue[0]
    assert item["review_status"] == "ready_for_draft_review"
    assert item["has_active_thesis"] is True
    assert item["latest_thesis_id"] == thesis_response.json()["id"]

    intent_response = client.post(
        f"/signals/{item['signal_id']}/create-order-intent",
        json={
            "account_id": account_id,
            "automation_level": "A3_ORDER_DRAFT",
            "signal_order_intents_enabled": True,
            "notional": 1000,
        },
    )
    assert intent_response.status_code == 201
    intent = intent_response.json()
    assert intent["investment_thesis_id"] == thesis_response.json()["id"]
    assert intent["source_signal_id"] == item["signal_id"]


def insert_signal(client, asset_id: str, *, direction: str, created_at: datetime) -> None:
    from app.models import Signal

    db_generator = app.dependency_overrides[get_db]()
    db = next(db_generator)
    try:
        db.add(
            Signal(
                asset_id=asset_id,
                signal_type="ma_cross",
                direction=direction,
                strength=0.8,
                source="test_fixture",
                observation_json={"horizon": "swing"},
                created_at=created_at,
            )
        )
        db.commit()
    finally:
        db_generator.close()


def test_signal_quality_report_computes_hit_rate_from_forward_returns(client) -> None:
    asset_id = create_asset(client)
    signal_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    # 6 daily candles rising from the signal timestamp: bullish hits, bearish misses.
    insert_candles(client, asset_id, timeframe="1d", closes=[100, 101, 102, 103, 104, 110])
    insert_signal(client, asset_id, direction="bullish", created_at=signal_time)
    insert_signal(client, asset_id, direction="bearish", created_at=signal_time)

    response = client.get("/signals/quality-report?horizon_candles=5")

    assert response.status_code == 200
    report = response.json()
    assert report["status"] == "evaluated"
    assert report["signals_evaluated"] == 2
    assert report["hit_rate"] == 0.5
    assert report["by_signal_type"]["ma_cross"]["evaluated"] == 2
    outcomes = {item["direction"]: item for item in report["outcomes"]}
    assert outcomes["bullish"]["hit"] is True
    assert outcomes["bearish"]["hit"] is False
    assert outcomes["bullish"]["forward_return_pct"] == 10.0
    assert report["execution_available"] is False


def test_signal_quality_report_skips_signals_without_forward_history(client) -> None:
    asset_id = create_asset(client)
    insert_candles(client, asset_id, timeframe="1d", closes=[100, 101])
    insert_signal(client, asset_id, direction="bullish", created_at=datetime(2026, 1, 1, tzinfo=timezone.utc))

    response = client.get("/signals/quality-report?horizon_candles=5")

    assert response.status_code == 200
    report = response.json()
    assert report["signals_evaluated"] == 0
    assert report["signals_skipped_insufficient_data"] == 1
    assert report["status"] == "insufficient_forward_data"
    assert report["hit_rate"] is None


def create_second_asset(client, symbol: str = "NVDA") -> str:
    response = client.post(
        "/assets",
        json={"symbol": symbol, "name": f"{symbol} Inc.", "asset_type": "stock", "market": "US", "venue": "NASDAQ", "currency": "USD"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_signal_baseline_shows_positive_edge_when_directions_match_moves(client) -> None:
    # Asset A rises → a bullish signal on it is correct.
    # Asset B falls → a bearish signal on it is correct.
    # Both signals hit (hit_rate=1.0). But the sample is 50% up / 50% down moves,
    # so a zero-skill same-direction-mix bet would only score ~0.5 → positive edge.
    signal_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    asset_up = create_asset(client)  # AAPL
    asset_down = create_second_asset(client)  # NVDA
    insert_candles(client, asset_up, timeframe="1d", closes=[100, 101, 102, 103, 104, 110])
    insert_candles(client, asset_down, timeframe="1d", closes=[100, 99, 98, 97, 96, 90])
    insert_signal(client, asset_up, direction="bullish", created_at=signal_time)
    insert_signal(client, asset_down, direction="bearish", created_at=signal_time)

    report = client.get("/signals/quality-report?horizon_candles=5").json()

    assert report["signals_evaluated"] == 2
    assert report["hit_rate"] == 1.0
    baseline = report["baseline"]
    assert baseline["up_move_rate"] == 0.5
    assert baseline["down_move_rate"] == 0.5
    assert baseline["baseline_hit_rate"] == 0.5
    assert baseline["edge_vs_baseline"] == 0.5
    assert baseline["has_positive_edge"] is True
    assert report["evaluation_scope"] == "point_in_time_out_of_sample"
    assert report["statistical_evidence"]["sample_sufficient"] is False
    assert report["statistical_evidence"]["quality_claim_allowed"] is False
    assert report["statistical_evidence"]["status"] == "insufficient_sample"


def test_signal_quality_requires_minimum_sample_and_wilson_lower_bound_above_baseline(client) -> None:
    signal_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    asset_up = create_asset(client)
    asset_down = create_second_asset(client)
    insert_candles(client, asset_up, timeframe="1d", closes=[100, 101, 102, 103, 104, 110])
    insert_candles(client, asset_down, timeframe="1d", closes=[100, 99, 98, 97, 96, 90])
    for _ in range(15):
        insert_signal(client, asset_up, direction="bullish", created_at=signal_time)
        insert_signal(client, asset_down, direction="bearish", created_at=signal_time)

    report = client.get("/signals/quality-report?horizon_candles=5&minimum_sample_size=30").json()

    assert report["signals_evaluated"] == 30
    assert report["hit_rate"] == 1.0
    assert report["baseline"]["baseline_hit_rate"] == 0.5
    assert report["statistical_evidence"]["hit_rate_confidence_interval_95"]["lower"] > 0.5
    assert report["statistical_evidence"]["statistically_supported_edge"] is True
    assert report["statistical_evidence"]["quality_claim_allowed"] is True
    assert report["statistical_evidence"]["status"] == "supported_edge"
    assert report["avg_directional_return_pct"] == 10.0


def test_signal_quality_uses_same_timeframe_and_point_in_time_base(client) -> None:
    asset_id = create_asset(client)
    insert_candles(client, asset_id, timeframe="1d", closes=[100, 101, 102, 103, 104, 110])
    insert_candles(client, asset_id, timeframe="1h", closes=[100, 50, 40, 30, 20, 10])
    insert_signal(client, asset_id, direction="bullish", created_at=datetime(2026, 1, 1, tzinfo=timezone.utc))

    report = client.get("/signals/quality-report?horizon_candles=5").json()

    assert report["outcomes"][0]["timeframe"] == "1d"
    assert report["outcomes"][0]["base_candle_at"].startswith("2026-01-01")
    assert report["outcomes"][0]["forward_return_pct"] == 10.0


def test_signal_baseline_shows_no_edge_in_a_uniform_up_market(client) -> None:
    # A single bullish signal in a market that only goes up: it hits, but so
    # would blindly betting bullish → zero edge. This is the case the baseline
    # exists to expose.
    signal_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    asset_id = create_asset(client)
    insert_candles(client, asset_id, timeframe="1d", closes=[100, 101, 102, 103, 104, 110])
    insert_signal(client, asset_id, direction="bullish", created_at=signal_time)

    report = client.get("/signals/quality-report?horizon_candles=5").json()

    assert report["hit_rate"] == 1.0
    baseline = report["baseline"]
    assert baseline["up_move_rate"] == 1.0
    assert baseline["baseline_hit_rate"] == 1.0
    assert baseline["edge_vs_baseline"] == 0.0
    assert baseline["has_positive_edge"] is False
