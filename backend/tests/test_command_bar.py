from fastapi.testclient import TestClient


def create_asset(client: TestClient, symbol: str = "NVDA", asset_type: str = "stock") -> dict:
    response = client.post(
        "/assets",
        json={
            "symbol": symbol,
            "name": f"{symbol} Test Asset",
            "asset_type": asset_type,
            "market": "US" if asset_type == "stock" else "crypto",
            "venue": "NASDAQ" if asset_type == "stock" else "mock_cex",
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
            "name": "Command Bar Paper Account",
            "account_type": "brokerage",
            "broker": "mock",
            "base_currency": "USD",
            "mode": "paper",
        },
    )
    assert response.status_code == 201
    return response.json()


def import_position(client: TestClient, account_id: str, asset_id: str, market_value: float = 10_000) -> dict:
    response = client.post(
        "/positions/import",
        json={
            "account_id": account_id,
            "asset_id": asset_id,
            "quantity": 10,
            "average_cost": 900,
            "market_price": 1000,
            "market_value": market_value,
            "unrealized_pnl": 1000,
            "realized_pnl": 0,
            "weight": 1,
        },
    )
    assert response.status_code == 201
    return response.json()


def create_thesis(client: TestClient, asset_id: str, account_id: str) -> dict:
    response = client.post(
        "/investment-theses",
        json={
            "user_id": "user-1",
            "asset_id": asset_id,
            "account_id": account_id,
            "entry_reason": "Own NVDA for data center revenue growth and margin expansion.",
            "key_drivers_json": {"items": ["data center growth", "margin expansion"]},
            "invalidation_conditions_json": {"items": ["data center growth decelerates"]},
            "expected_horizon": "long_term",
            "target_condition": "Hold while thesis remains valid.",
            "max_loss_tolerance_pct": 0.2,
            "position_plan_json": {"sizing": "core"},
            "confidence": 0.75,
            "source": "manual",
            "status": "active",
        },
    )
    assert response.status_code == 201
    return response.json()


def create_policy(client: TestClient, account_id: str, asset_id: str) -> dict:
    response = client.post(
        "/automation-policies",
        json={
            "user_id": "user-1",
            "account_id": account_id,
            "asset_id": asset_id,
            "automation_level": "A3_ORDER_DRAFT",
            "max_notional_per_order": 1000,
            "max_orders_per_day": 2,
            "requires_approval": True,
            "allowed_actions": ["CREATE_ORDER_INTENT", "CREATE_ORDER_DRAFT"],
            "forbidden_actions": ["LIVE_EXECUTION"],
            "is_active": True,
        },
    )
    assert response.status_code == 201
    return response.json()


def test_portfolio_query_routes_to_portfolio_tool(client: TestClient) -> None:
    response = client.post(
        "/command-bar/query",
        json={"user_id": "user-1", "raw_query": "portfolio summary", "data_snapshot_id": "snapshot-portfolio-1"},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["query"]["detected_intent"] == "portfolio_summary"
    assert payload["query"]["required_tools"] == ["portfolio_summary_tool"]
    assert payload["tool_calls"][0]["tool_name"] == "portfolio_summary_tool"
    assert payload["result"]["data_sources_json"]["data_snapshot_id"] == "snapshot-portfolio-1"


def test_thesis_query_routes_to_thesis_tool(client: TestClient) -> None:
    asset = create_asset(client)
    account = create_account(client)
    create_thesis(client, asset["id"], account["id"])

    response = client.post(
        "/command-bar/query",
        json={"user_id": "user-1", "asset_id": asset["id"], "raw_query": "为 NVDA 生成 thesis review"},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["query"]["detected_intent"] == "thesis_review"
    assert payload["tool_calls"][0]["tool_name"] == "thesis_review_tool"
    assert payload["tool_calls"][0]["output_json"]["theses"][0]["asset_id"] == asset["id"]
    assert "data_quality" in payload["tool_calls"][0]["output_json"]
    assert payload["result"]["structured_result_json"]["next_steps"]
    assert payload["result"]["structured_result_json"]["next_steps"][0]["module"] == "investment_logic"


def test_risk_query_routes_to_risk_tool(client: TestClient) -> None:
    asset = create_asset(client, "BTC", "crypto")
    account = create_account(client)
    import_position(client, account["id"], asset["id"], market_value=50_000)

    response = client.post(
        "/command-bar/query",
        json={"user_id": "user-1", "raw_query": "总结我今天的组合风险", "data_snapshot_id": "risk-snapshot-1"},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["query"]["detected_intent"] == "risk_exposure"
    assert payload["tool_calls"][0]["tool_name"] == "risk_exposure_tool"
    assert payload["result"]["data_sources_json"]["data_snapshot_id"] == "risk-snapshot-1"


def test_execution_request_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/command-bar/query",
        json={"user_id": "user-1", "raw_query": "execute live market buy NVDA now"},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["query"]["status"] == "rejected"
    assert payload["query"]["detected_intent"] == "rejected_execution_request"
    assert payload["tool_calls"] == []
    assert payload["result"]["structured_result_json"]["reason"] == "command_bar_cannot_execute_trades"
    assert any(log["action"] == "command_bar.execution_request_rejected" for log in client.get("/audit-logs").json())


def test_order_intent_creation_requires_policy(client: TestClient) -> None:
    asset = create_asset(client)
    account = create_account(client)

    response = client.post(
        "/command-bar/query",
        json={
            "user_id": "user-1",
            "raw_query": "create order intent to buy NVDA",
            "allow_order_intent": True,
            "account_id": account["id"],
            "asset_id": asset["id"],
            "side": "buy",
            "notional": 500,
        },
    )

    assert response.status_code == 403
    assert "A3_ORDER_DRAFT" in response.json()["detail"]
    audit_logs = client.get("/audit-logs").json()
    assert any(log["action"] == "command_bar.order_intent_blocked" for log in audit_logs)
    assert not any(log["action"] == "command_bar.order_intent_created" for log in audit_logs)


def test_order_intent_creation_allowed_with_a3_policy(client: TestClient) -> None:
    asset = create_asset(client)
    account = create_account(client)
    policy = create_policy(client, account["id"], asset["id"])

    response = client.post(
        "/command-bar/query",
        json={
            "user_id": "user-1",
            "raw_query": "create order intent to buy NVDA",
            "allow_order_intent": True,
            "account_id": account["id"],
            "asset_id": asset["id"],
            "side": "buy",
            "notional": 500,
            "user_rationale": "Testing a passive command-bar order intent.",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["order_intent"]["source_type"] == "command_bar"
    assert payload["order_intent"]["automation_policy_id"] == policy["id"]
    assert payload["order_intent"]["status"] == "created"
    assert payload["order_intent"]["rationale"].startswith("Passive OrderIntent created by command bar")
    assert any(log["action"] == "command_bar.order_intent_created" for log in client.get("/audit-logs").json())


def test_command_bar_writes_audit_log(client: TestClient) -> None:
    response = client.post(
        "/command-bar/query",
        json={"user_id": "user-1", "raw_query": "signal lookup"},
    )
    assert response.status_code == 201
    audit_actions = [log["action"] for log in client.get("/audit-logs").json()]
    assert "command_bar.query_logged" in audit_actions
    assert "command_bar.query_completed" in audit_actions
