from datetime import datetime
from datetime import timedelta
from datetime import timezone

from fastapi.testclient import TestClient

from app.db.session import get_db
from app.main import app
from app.models import Candle
from test_risk_approval import create_asset
from test_route_parity_safe_lab import create_playbook


def insert_candles(asset_id: str, closes: list[float], *, timeframe: str = "1d") -> None:
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
                    source="test_backtests",
                )
            )
        db.commit()
    finally:
        db.close()
        try:
            next(db_generator)
        except StopIteration:
            pass


def test_backtest_run_completes_deterministic_local_candle_simulation(client: TestClient) -> None:
    asset = create_asset(client)
    playbook = create_playbook(client)
    insert_candles(asset["id"], [10, 10, 10, 12, 14, 13, 11, 9])

    created = client.post(
        "/backtest-runs",
        json={
            "strategy_playbook_id": playbook["id"],
            "name": "Local MA simulation",
            "date_from": "2026-01-01",
            "date_to": "2026-01-08",
            "initial_capital": "100000",
            "parameters_json": {
                "asset_id": asset["id"],
                "timeframe": "1d",
                "short_window": 2,
                "long_window": 3,
                "position_pct": 1,
                "fee_bps": 0,
            },
        },
    )
    assert created.status_code == 201

    started = client.post(f"/backtest-runs/{created.json()['id']}/start")

    assert started.status_code == 200
    run = started.json()
    results = run["results_json"]
    assert run["status"] == "completed"
    assert results["engine_status"] == "completed"
    assert results["execution_available"] is False
    assert results["real_orders_created"] == 0
    assert results["paper_orders_created"] == 0
    assert results["simulated_trades_created"] == 2
    assert results["data_contract"]["source"] == "local_candles"
    assert results["data_contract"]["asset_id"] == asset["id"]
    assert results["data_contract"]["candle_count"] == 8
    assert results["strategy"]["short_window"] == 2
    assert results["strategy"]["long_window"] == 3
    assert [trade["side"] for trade in results["simulated_trades"]] == ["buy", "sell"]
    assert client.get("/orders/drafts").json() == []

    actions = {log["action"] for log in client.get("/audit-logs").json()}
    assert {"backtest_run.created", "backtest_run.completed"}.issubset(actions)


def test_backtest_promotion_preflight_allows_research_review_without_orders(client: TestClient) -> None:
    asset = create_asset(client)
    playbook = create_playbook(client)
    insert_candles(asset["id"], [10, 10, 10, 12, 14, 13, 11, 9])
    created = client.post(
        "/backtest-runs",
        json={
            "strategy_playbook_id": playbook["id"],
            "name": "Promotion preflight simulation",
            "date_from": "2026-01-01",
            "date_to": "2026-01-08",
            "initial_capital": "100000",
            "parameters_json": {
                "asset_id": asset["id"],
                "timeframe": "1d",
                "short_window": 2,
                "long_window": 3,
            },
        },
    )
    assert created.status_code == 201
    started = client.post(f"/backtest-runs/{created.json()['id']}/start")
    assert started.status_code == 200

    response = client.post(f"/backtest-runs/{created.json()['id']}/promotion-preflight")

    assert response.status_code == 200
    preflight = response.json()
    assert preflight["status"] in {"eligible_for_research_review", "review_required"}
    assert preflight["order_creation_allowed"] is False
    assert preflight["paper_order_creation_allowed"] is False
    assert preflight["live_order_creation_allowed"] is False
    assert preflight["execution_available"] is False
    assert preflight["blockers"] == []
    assert client.get("/orders/drafts").json() == []


def test_backtest_run_blocks_when_local_candles_are_insufficient(client: TestClient) -> None:
    asset = create_asset(client)
    playbook = create_playbook(client)
    insert_candles(asset["id"], [10, 11, 12])

    created = client.post(
        "/backtest-runs",
        json={
            "strategy_playbook_id": playbook["id"],
            "name": "Insufficient local candles",
            "date_from": "2026-01-01",
            "date_to": "2026-01-08",
            "initial_capital": "100000",
            "parameters_json": {
                "asset_id": asset["id"],
                "timeframe": "1d",
                "short_window": 2,
                "long_window": 3,
            },
        },
    )
    assert created.status_code == 201

    started = client.post(f"/backtest-runs/{created.json()['id']}/start")

    assert started.status_code == 200
    run = started.json()
    results = run["results_json"]
    assert run["status"] == "blocked"
    assert results["execution_available"] is False
    assert results["simulated_trades_created"] == 0
    assert "insufficient_local_candles" in results["blocking_reasons"]
    assert results["data_contract"]["candle_count"] == 3


def test_backtest_run_supports_read_only_strategy_dsl_and_walk_forward(client: TestClient) -> None:
    asset = create_asset(client)
    playbook = create_playbook(client)
    insert_candles(asset["id"], [10, 10, 11, 12, 14, 13, 12, 11, 12, 13, 15, 14])

    created = client.post(
        "/backtest-runs",
        json={
            "strategy_playbook_id": playbook["id"],
            "name": "Read-only DSL walk-forward",
            "date_from": "2026-01-01",
            "date_to": "2026-01-12",
            "initial_capital": "100000",
            "parameters_json": {
                "asset_id": asset["id"],
                "timeframe": "1d",
                "position_pct": 0.5,
                "fee_bps": 5,
                "strategy_dsl": {
                    "version": "local-readonly-v1",
                    "engine": "ma_cross",
                    "entry": {"short_ma_above_long_ma": {"short_window": 2, "long_window": 3}},
                    "exit": {"short_ma_below_long_ma": {"short_window": 2, "long_window": 3}},
                },
                "walk_forward": {"enabled": True, "fold_size": 6, "step_size": 3},
            },
        },
    )
    assert created.status_code == 201

    started = client.post(f"/backtest-runs/{created.json()['id']}/start")

    assert started.status_code == 200
    run = started.json()
    results = run["results_json"]
    assert run["status"] == "completed"
    assert results["strategy"]["dsl"]["valid"] is True
    assert results["strategy"]["dsl"]["engine"] == "ma_cross"
    assert results["strategy"]["dsl"]["order_creation_allowed"] is False
    assert results["walk_forward"]["enabled"] is True
    assert results["walk_forward"]["status"] == "completed"
    assert results["walk_forward"]["summary"]["fold_count"] == 1
    assert results["walk_forward"]["summary"]["metric_scope"] == "out_of_sample_only"
    assert results["walk_forward"]["split_policy"] == "chronological_train_then_out_of_sample_test"
    assert results["walk_forward"]["folds"][0]["in_sample"]["date_to"] < results["walk_forward"]["folds"][0]["out_of_sample"]["date_from"]
    assert results["walk_forward"]["execution_available"] is False
    assert client.get("/orders/drafts").json() == []

    preflight = client.post(f"/backtest-runs/{created.json()['id']}/promotion-preflight").json()
    assert preflight["execution_available"] is False
    assert preflight["order_creation_allowed"] is False
    assert any(check["key"] == "walk_forward" for check in preflight["checks"])

    packet = client.post(f"/backtest-runs/{created.json()['id']}/research-packet").json()
    assert packet["execution_available"] is False
    assert packet["walk_forward"]["status"] == "completed"
    assert packet["strategy"]["dsl"]["engine"] == "ma_cross"


def test_backtest_run_blocks_unsupported_strategy_dsl(client: TestClient) -> None:
    asset = create_asset(client)
    playbook = create_playbook(client)
    insert_candles(asset["id"], [10, 10, 11, 12, 14, 13, 12, 11])

    created = client.post(
        "/backtest-runs",
        json={
            "strategy_playbook_id": playbook["id"],
            "name": "Unsupported DSL",
            "date_from": "2026-01-01",
            "date_to": "2026-01-08",
            "initial_capital": "100000",
            "parameters_json": {
                "asset_id": asset["id"],
                "timeframe": "1d",
                "strategy_dsl": {"version": "local-readonly-v1", "engine": "llm_direct_execution"},
            },
        },
    )
    assert created.status_code == 201

    started = client.post(f"/backtest-runs/{created.json()['id']}/start")

    assert started.status_code == 200
    results = started.json()["results_json"]
    assert started.json()["status"] == "blocked"
    assert "unsupported_strategy_engine" in results["blocking_reasons"]
    assert results["execution_available"] is False
    assert results["real_orders_created"] == 0


def test_backtest_slippage_model_worsens_fill_prices(client: TestClient) -> None:
    asset = create_asset(client)
    playbook = create_playbook(client)
    insert_candles(asset["id"], [10, 10, 11, 12, 14, 13, 12, 11, 12, 13, 15, 14])

    def run_with(slippage_bps: float) -> dict:
        created = client.post(
            "/backtest-runs",
            json={
                "strategy_playbook_id": playbook["id"],
                "name": f"Slippage {slippage_bps}bps",
                "date_from": "2026-01-01",
                "date_to": "2026-01-12",
                "initial_capital": "100000",
                "parameters_json": {
                    "asset_id": asset["id"],
                    "timeframe": "1d",
                    "short_window": 2,
                    "long_window": 3,
                    "position_pct": 1.0,
                    "fee_bps": 0,
                    "slippage_bps": slippage_bps,
                },
            },
        )
        assert created.status_code == 201
        started = client.post(f"/backtest-runs/{created.json()['id']}/start")
        assert started.status_code == 200
        return started.json()["results_json"]

    frictionless = run_with(0)
    slipped = run_with(50)

    buys = [trade for trade in slipped["simulated_trades"] if trade["side"] == "buy"]
    sells = [trade for trade in slipped["simulated_trades"] if trade["side"] == "sell"]
    assert buys and sells
    for trade in buys:
        assert trade["fill_price"] > trade["price"]
        assert trade["slippage_cost"] > 0
    for trade in sells:
        assert trade["fill_price"] < trade["price"]
        assert trade["slippage_cost"] > 0
    assert slipped["final_capital"] < frictionless["final_capital"]


def test_backtest_reports_buy_and_hold_benchmark(client: TestClient) -> None:
    asset = create_asset(client)
    playbook = create_playbook(client)
    # A steady uptrend: buy-and-hold captures the full move; an MA-cross that
    # trades in and out will generally not beat simply holding.
    insert_candles(asset["id"], [10, 10, 11, 12, 14, 13, 12, 11, 12, 13, 15, 20])

    created = client.post(
        "/backtest-runs",
        json={
            "strategy_playbook_id": playbook["id"],
            "name": "Benchmark comparison",
            "date_from": "2026-01-01",
            "date_to": "2026-01-12",
            "initial_capital": "100000",
            "parameters_json": {
                "asset_id": asset["id"],
                "timeframe": "1d",
                "short_window": 2,
                "long_window": 3,
                "position_pct": 1.0,
                "fee_bps": 0,
                "slippage_bps": 0,
            },
        },
    )
    assert created.status_code == 201
    started = client.post(f"/backtest-runs/{created.json()['id']}/start")
    assert started.status_code == 200
    results = started.json()["results_json"]

    benchmark = results["benchmark"]
    assert benchmark is not None
    assert benchmark["type"] == "buy_and_hold"
    assert benchmark["entry_price"] == 10.0
    assert benchmark["exit_price"] == 20.0
    # Buy-and-hold doubles: 100000 → ~200000.
    assert abs(benchmark["total_return_pct"] - 100.0) < 0.01
    # excess = strategy return - benchmark return, and the flag is consistent.
    strat_return = results["metrics"]["total_return_pct"]
    assert abs(benchmark["strategy_excess_return_pct"] - (strat_return - benchmark["total_return_pct"])) < 0.01
    assert benchmark["strategy_beats_benchmark"] == (results["final_capital"] > benchmark["final_capital"])


def test_backtest_benchmark_applies_entry_fee_and_slippage(client: TestClient) -> None:
    asset = create_asset(client)
    playbook = create_playbook(client)
    insert_candles(asset["id"], [100, 100, 101, 102, 104, 103, 102, 101, 102, 103, 105, 110])

    created = client.post(
        "/backtest-runs",
        json={
            "strategy_playbook_id": playbook["id"],
            "name": "Benchmark with friction",
            "date_from": "2026-01-01",
            "date_to": "2026-01-12",
            "initial_capital": "100000",
            "parameters_json": {
                "asset_id": asset["id"],
                "timeframe": "1d",
                "short_window": 2,
                "long_window": 3,
                "position_pct": 1.0,
                "fee_bps": 10,
                "slippage_bps": 25,
            },
        },
    )
    assert created.status_code == 201
    started = client.post(f"/backtest-runs/{created.json()['id']}/start")
    assert started.status_code == 200
    benchmark = started.json()["results_json"]["benchmark"]
    # With entry friction, buying at 100 and selling at 110 yields slightly
    # under the frictionless 10% because of the fee + entry slippage drag.
    assert benchmark["entry_price"] == 100.0
    assert benchmark["exit_price"] == 110.0
    assert benchmark["total_return_pct"] < 10.0
    assert benchmark["total_return_pct"] > 9.5


def create_second_asset(client: TestClient) -> dict:
    response = client.post(
        "/assets",
        json={
            "symbol": "MSFT",
            "name": "Microsoft Corp.",
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


def test_backtest_portfolio_run_combines_legs_without_orders(client: TestClient) -> None:
    asset_a = create_asset(client)
    asset_b = create_second_asset(client)
    playbook = create_playbook(client)
    # Asset A trends up (MA-cross buys), asset B trends down (stays in cash).
    insert_candles(asset_a["id"], [10, 11, 12, 13, 14, 16, 18, 20, 24, 30])
    insert_candles(asset_b["id"], [30, 28, 26, 24, 22, 20, 18, 16, 13, 10])

    created = client.post(
        "/backtest-runs",
        json={
            "strategy_playbook_id": playbook["id"],
            "name": "Two-asset portfolio",
            "date_from": "2026-01-01",
            "date_to": "2026-01-31",
            "initial_capital": "100000",
            "parameters_json": {
                "timeframe": "1d",
                "short_window": 2,
                "long_window": 4,
                "fee_bps": 10,
                "slippage_bps": 5,
                "assets": [
                    {"asset_id": asset_a["id"], "weight": 0.6},
                    {"asset_id": asset_b["id"], "weight": 0.4},
                ],
            },
        },
    )
    assert created.status_code == 201

    started = client.post(f"/backtest-runs/{created.json()['id']}/start")
    assert started.status_code == 200
    run = started.json()
    results = run["results_json"]

    assert run["status"] == "completed"
    assert results["mode"] == "portfolio"
    assert results["engine_status"] == "completed"
    # Safety invariants must hold in portfolio mode too.
    assert results["execution_available"] is False
    assert results["real_orders_created"] == 0
    assert results["paper_orders_created"] == 0
    assert len(results["legs"]) == 2
    # Weights are normalized and each leg's capital sums to the portfolio total.
    allocated = sum(leg["allocated_capital"] for leg in results["legs"])
    assert abs(allocated - 100000.0) < 1e-3
    # Portfolio final equals the sum of per-leg finals.
    leg_final_sum = sum(leg["final_capital"] for leg in results["legs"])
    assert abs(results["final_capital"] - leg_final_sum) < 1e-2
    # Benchmark is the weighted buy-and-hold of the same legs.
    assert results["benchmark"]["type"] == "buy_and_hold_portfolio"
    assert isinstance(results["benchmark"]["strategy_beats_benchmark"], bool)
    assert results["data_contract"]["source"] == "local_candles"
    assert client.get("/orders/drafts").json() == []


def test_backtest_portfolio_walk_forward_reports_only_out_of_sample_metrics(client: TestClient) -> None:
    asset_a = create_asset(client)
    asset_b = create_second_asset(client)
    playbook = create_playbook(client)
    insert_candles(asset_a["id"], [10, 11, 12, 13, 14, 16, 18, 17, 19, 21, 23, 25])
    insert_candles(asset_b["id"], [30, 29, 28, 27, 26, 25, 24, 25, 26, 27, 28, 29])
    created = client.post(
        "/backtest-runs",
        json={
            "strategy_playbook_id": playbook["id"], "name": "Portfolio OOS", "date_from": "2026-01-01", "date_to": "2026-01-31", "initial_capital": "100000",
            "parameters_json": {"timeframe": "1d", "short_window": 2, "long_window": 3, "fee_bps": 5, "slippage_bps": 5, "max_volume_participation_pct": 10, "assets": [{"asset_id": asset_a["id"], "weight": 0.6}, {"asset_id": asset_b["id"], "weight": 0.4}], "walk_forward": {"enabled": True, "train_candles": 6, "test_candles": 6, "step_size": 6}},
        },
    )
    started = client.post(f"/backtest-runs/{created.json()['id']}/start")
    assert started.status_code == 200
    walk_forward = started.json()["results_json"]["walk_forward"]
    assert walk_forward["status"] == "completed"
    assert walk_forward["mode"] == "portfolio_static_weight_sleeves"
    assert walk_forward["summary"]["metric_scope"] == "out_of_sample_only"
    assert walk_forward["folds"][0]["in_sample"]["date_to"] < walk_forward["folds"][0]["out_of_sample"]["date_from"]
    assert len(walk_forward["folds"][0]["legs"]) == 2
    assert walk_forward["execution_available"] is False


def test_backtest_volume_participation_caps_strategy_and_benchmark_fills(client: TestClient) -> None:
    asset = create_asset(client)
    playbook = create_playbook(client)
    insert_candles(asset["id"], [10, 10, 11, 12, 14, 13, 12, 11, 12, 14])
    created = client.post(
        "/backtest-runs",
        json={
            "strategy_playbook_id": playbook["id"],
            "name": "Liquidity constrained simulation",
            "date_from": "2026-01-01",
            "date_to": "2026-01-10",
            "initial_capital": "100000",
            "parameters_json": {"asset_id": asset["id"], "timeframe": "1d", "short_window": 2, "long_window": 3, "position_pct": 1, "max_volume_participation_pct": 1},
        },
    )
    started = client.post(f"/backtest-runs/{created.json()['id']}/start")
    assert started.status_code == 200
    results = started.json()["results_json"]
    assert results["strategy"]["max_volume_participation_pct"] == 1
    assert results["metrics"]["liquidity_constrained_fills"] > 0
    assert any(trade["liquidity_constrained"] for trade in results["simulated_trades"])
    assert results["benchmark"]["liquidity_constrained"] is True
    assert results["execution_available"] is False


def test_backtest_portfolio_run_blocks_on_bad_weight(client: TestClient) -> None:
    asset_a = create_asset(client)
    asset_b = create_second_asset(client)
    playbook = create_playbook(client)
    insert_candles(asset_a["id"], [10, 11, 12, 13, 14, 16, 18, 20, 24, 30])
    insert_candles(asset_b["id"], [30, 28, 26, 24, 22, 20, 18, 16, 13, 10])

    created = client.post(
        "/backtest-runs",
        json={
            "strategy_playbook_id": playbook["id"],
            "name": "Bad-weight portfolio",
            "date_from": "2026-01-01",
            "date_to": "2026-01-31",
            "initial_capital": "100000",
            "parameters_json": {
                "timeframe": "1d",
                "short_window": 2,
                "long_window": 4,
                "assets": [
                    {"asset_id": asset_a["id"], "weight": 0},
                    {"asset_id": asset_b["id"], "weight": 1},
                ],
            },
        },
    )
    assert created.status_code == 201

    started = client.post(f"/backtest-runs/{created.json()['id']}/start")
    assert started.status_code == 200
    results = started.json()["results_json"]
    assert started.json()["status"] == "blocked"
    assert results["engine_status"] == "blocked"
    assert "non_positive_portfolio_weight" in results["blocking_reasons"]
    assert results["execution_available"] is False
    assert client.get("/orders/drafts").json() == []


def test_backtest_portfolio_rebalancing_runs_and_reports_events(client: TestClient) -> None:
    asset_a = create_asset(client)
    asset_b = create_second_asset(client)
    playbook = create_playbook(client)
    insert_candles(asset_a["id"], [10, 11, 12, 13, 15, 18, 22, 20, 17, 14, 12, 11])
    insert_candles(asset_b["id"], [30, 28, 26, 24, 22, 20, 18, 20, 23, 26, 29, 32])

    created = client.post(
        "/backtest-runs",
        json={
            "strategy_playbook_id": playbook["id"],
            "name": "Rebalanced portfolio",
            "date_from": "2026-01-01",
            "date_to": "2026-01-31",
            "initial_capital": "100000",
            "parameters_json": {
                "timeframe": "1d",
                "short_window": 2,
                "long_window": 4,
                "fee_bps": 10,
                "slippage_bps": 5,
                "rebalance_every": 4,
                "assets": [
                    {"asset_id": asset_a["id"], "weight": 0.5},
                    {"asset_id": asset_b["id"], "weight": 0.5},
                ],
            },
        },
    )
    assert created.status_code == 201

    started = client.post(f"/backtest-runs/{created.json()['id']}/start")
    assert started.status_code == 200
    results = started.json()["results_json"]

    assert started.json()["status"] == "completed"
    assert results["mode"] == "portfolio"
    assert results["execution_available"] is False
    assert results["real_orders_created"] == 0
    # Rebalancing metadata is present and internally consistent.
    assert results["rebalance"]["enabled"] is True
    assert results["rebalance"]["rebalance_every_candles"] == 4
    assert results["rebalance"]["rebalance_events"] >= 1
    assert results["metrics"]["rebalance_events"] == results["rebalance"]["rebalance_events"]
    assert results["benchmark"]["type"] == "buy_and_hold_portfolio"
    # Equity curve ends at the reported final capital.
    assert abs(results["equity_curve"][-1]["equity"] - results["final_capital"]) < 1e-2
    assert client.get("/orders/drafts").json() == []


def test_backtest_portfolio_rejects_negative_rebalance(client: TestClient) -> None:
    asset_a = create_asset(client)
    asset_b = create_second_asset(client)
    playbook = create_playbook(client)
    insert_candles(asset_a["id"], [10, 11, 12, 13, 15, 18])
    insert_candles(asset_b["id"], [30, 28, 26, 24, 22, 20])

    created = client.post(
        "/backtest-runs",
        json={
            "strategy_playbook_id": playbook["id"],
            "name": "Bad rebalance",
            "date_from": "2026-01-01",
            "date_to": "2026-01-31",
            "initial_capital": "100000",
            "parameters_json": {
                "timeframe": "1d", "short_window": 2, "long_window": 4, "rebalance_every": -3,
                "assets": [
                    {"asset_id": asset_a["id"], "weight": 0.5},
                    {"asset_id": asset_b["id"], "weight": 0.5},
                ],
            },
        },
    )
    assert created.status_code == 201
    started = client.post(f"/backtest-runs/{created.json()['id']}/start")
    # Negative rebalance_every fails closed as a blocked run, not a crash.
    assert started.status_code == 200
    results = started.json()["results_json"]
    assert started.json()["status"] == "blocked"
    assert "invalid_rebalance_every" in results["blocking_reasons"]
    assert results["execution_available"] is False
