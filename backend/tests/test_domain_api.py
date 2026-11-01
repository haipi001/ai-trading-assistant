from fastapi.testclient import TestClient


def create_asset(client: TestClient) -> dict:
    response = client.post(
        "/assets",
        json={
            "symbol": "AAPL",
            "name": "Apple Inc.",
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


def create_account(client: TestClient) -> dict:
    response = client.post(
        "/accounts",
        json={
            "name": "Read Only Test Account",
            "account_type": "brokerage",
            "broker": "manual",
            "base_currency": "USD",
            "mode": "read_only",
        },
    )

    assert response.status_code == 201
    return response.json()


def create_quality_snapshot(client: TestClient, symbols: list[str] | None = None) -> str:
    connection_response = client.post(
        "/data-sources/connections",
        json={
            "name": "Domain API Quality Source",
            "provider": "mock_market_data",
            "source_type": "market_data",
            "mode": "read_only",
        },
    )
    assert connection_response.status_code == 201
    connection = connection_response.json()
    import_response = client.post(
        f"/data-sources/connections/{connection['id']}/import-quotes",
        json={"symbols": symbols or ["AAPL"], "asset_type": "stock", "market": "US", "currency": "USD"},
    )
    assert import_response.status_code == 201
    entry_id = import_response.json()["catalog_entry"]["id"]
    assert client.post(f"/data-catalog/entries/{entry_id}/promote").json()["current_stage"] == "reviewed"
    assert client.post(f"/data-catalog/entries/{entry_id}/promote").json()["current_stage"] == "trusted"
    return import_response.json()["snapshot"]["id"]


def pass_decision_gates(client: TestClient, order_intent_id: str, account_id: str) -> None:
    constitution_response = client.post(
        "/investment-constitutions",
        json={
            "user_id": "user-1",
            "version": "v1",
            "name": "Phase 1 test constitution",
            "investment_style": "disciplined",
            "allowed_markets": ["US"],
            "forbidden_assets": [],
            "forbidden_actions": ["LIVE_EXECUTION"],
            "max_single_position_pct": 0.2,
            "max_asset_class_pct": 0.8,
            "max_crypto_pct": 0.2,
            "max_single_exchange_pct": 0.5,
            "max_daily_loss_pct": 0.02,
            "max_monthly_drawdown_pct": 0.08,
            "leverage_allowed": False,
            "derivatives_allowed": False,
            "auto_execution_allowed": False,
            "human_approval_required": True,
            "cooldown_rules_json": {},
            "is_active": True,
        },
    )
    assert constitution_response.status_code == 201
    constitution = constitution_response.json()

    risk_budget_response = client.post(
        "/risk-budgets",
        json={
            "user_id": "user-1",
            "constitution_id": constitution["id"],
            "account_id": account_id,
            "asset_class": "stock",
            "max_allocation_pct": 0.8,
            "max_loss_pct": 0.08,
            "max_order_notional": 10_000,
            "max_leverage": 1,
            "rebalance_threshold_pct": 0.05,
        },
    )
    assert risk_budget_response.status_code == 201
    snapshot_id = create_quality_snapshot(client)
    report_response = client.post(
        "/reports/generate",
        json={
            "report_type": "single_asset_research",
            "data_snapshot_id": snapshot_id,
            "input_facts": {"revenue_growth": "positive", "risks": ["valuation"]},
            "provider": "mock",
        },
    )
    assert report_response.status_code == 201
    client.post("/mock/update-quotes")
    gate_response = client.post(
        "/decision-gates/evaluate",
        json={
            "order_intent_id": order_intent_id,
            "user_id": "user-1",
            "data_snapshot_id": snapshot_id,
            "current_position_pct": 0,
            "order_position_pct": 0.01,
            "asset_class_pct": 0.1,
            "exchange_pct": 0.1,
        },
    )
    assert gate_response.status_code == 201
    assert gate_response.json()["all_passed"] is True


def test_create_asset(client: TestClient) -> None:
    asset = create_asset(client)

    assert asset["symbol"] == "AAPL"
    assert asset["asset_type"] == "stock"
    assert asset["auto_enabled"] is False

    list_response = client.get("/assets")
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1


def test_create_account_defaults_live_trading_false(client: TestClient) -> None:
    account = create_account(client)

    assert account["mode"] == "read_only"
    assert account["live_trading_enabled"] is False

    list_response = client.get("/accounts")
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1


def test_import_position(client: TestClient) -> None:
    asset = create_asset(client)
    account = create_account(client)

    response = client.post(
        "/positions/import",
        json={
            "account_id": account["id"],
            "asset_id": asset["id"],
            "quantity": 10,
            "average_cost": 100,
            "market_price": 125,
            "market_value": 1250,
            "unrealized_pnl": 250,
            "realized_pnl": 0,
            "weight": 0.25,
        },
    )

    assert response.status_code == 201
    assert response.json()["account_id"] == account["id"]
    assert response.json()["asset_id"] == asset["id"]


def test_create_order_intent_and_draft_with_audit_log(client: TestClient) -> None:
    asset = create_asset(client)
    account_response = client.post(
        "/accounts",
        json={
            "name": "Paper Test Account",
            "account_type": "brokerage",
            "broker": "manual",
            "base_currency": "USD",
            "mode": "paper",
        },
    )
    assert account_response.status_code == 201
    account = account_response.json()

    intent_response = client.post(
        "/orders/intents",
        json={
            "source_type": "manual",
            "asset_id": asset["id"],
            "account_id": account["id"],
            "side": "buy",
            "order_type": "market",
            "notional": 120,
            "rationale": "Phase 1 data model test only.",
        },
    )

    assert intent_response.status_code == 201
    intent = intent_response.json()
    assert intent["status"] == "created"

    pass_decision_gates(client, intent["id"], account["id"])
    draft_response = client.post(f"/orders/intents/{intent['id']}/draft", json={"order_intent_id": intent["id"]})

    assert draft_response.status_code == 201
    draft = draft_response.json()
    assert draft["order_intent_id"] == intent["id"]
    assert draft["execution_status"] == "not_executable"

    audit_response = client.get("/audit-logs")
    assert audit_response.status_code == 200
    actions = {audit_log["action"] for audit_log in audit_response.json()}
    assert {"asset.created", "account.created", "order_intent.created", "order_draft.created_after_risk"}.issubset(actions)
