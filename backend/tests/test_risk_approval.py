from fastapi.testclient import TestClient


def create_asset(client: TestClient, *, tradable: bool = True, manual_enabled: bool = True, auto_enabled: bool = False) -> dict:
    response = client.post(
        "/assets",
        json={
            "symbol": "AAPL",
            "name": "Apple Inc.",
            "asset_type": "stock",
            "market": "US",
            "venue": "NASDAQ",
            "currency": "USD",
            "tradable": tradable,
            "manual_enabled": manual_enabled,
            "auto_enabled": auto_enabled,
            "risk_level": "medium",
        },
    )
    assert response.status_code == 201
    return response.json()


def create_account(client: TestClient, *, mode: str = "paper", live_trading_enabled: bool = False) -> dict:
    response = client.post(
        "/accounts",
        json={
            "name": "Risk Test Account",
            "account_type": "brokerage",
            "broker": "mock",
            "base_currency": "USD",
            "mode": mode,
            "live_trading_enabled": live_trading_enabled,
        },
    )
    assert response.status_code == 201
    return response.json()


def create_intent(
    client: TestClient,
    asset_id: str,
    account_id: str,
    *,
    side: str = "buy",
    quantity: float | None = None,
    notional: float | None = 1_000,
    limit_price: float | None = None,
    source_type: str = "manual",
    strategy_playbook_id: str | None = None,
) -> dict:
    payload = {
        "source_type": source_type,
        "asset_id": asset_id,
        "account_id": account_id,
        "side": side,
        "order_type": "market",
        "rationale": "Risk engine test intent.",
    }
    if quantity is not None:
        payload["quantity"] = quantity
    if notional is not None:
        payload["notional"] = notional
    if limit_price is not None:
        payload["limit_price"] = limit_price
    if strategy_playbook_id is not None:
        payload["strategy_playbook_id"] = strategy_playbook_id

    response = client.post(
        "/orders/intents",
        json=payload,
    )
    assert response.status_code == 201
    return response.json()


def create_quality_snapshot(client: TestClient, symbols: list[str] | None = None) -> str:
    connection_response = client.post(
        "/data-sources/connections",
        json={
            "name": "Risk Approval Quality Source",
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
            "name": "Risk approval test constitution",
            "investment_style": "disciplined",
            "allowed_markets": ["US"],
            "forbidden_assets": [],
            "forbidden_actions": ["LIVE_EXECUTION"],
            "max_single_position_pct": 0.25,
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


def risk_payload(order_intent_id: str, **overrides) -> dict:
    payload = {
        "order_intent_id": order_intent_id,
        "order_mode": "manual",
        "max_order_notional": 10_000,
        "max_position_pct": 0.25,
        "total_equity": 100_000,
        "current_position_value": 0,
        "account_daily_loss": 0,
        "max_daily_loss": 1_000,
        "current_leverage": 0,
        "max_leverage": 1,
        "liquidity_passed": True,
        "volatility": 0.2,
        "max_volatility": 1,
        "kill_switch": False,
    }
    payload.update(overrides)
    return payload


def failed_rule_names(risk_check: dict) -> set[str]:
    return {rule["rule"] for rule in risk_check["rules_json"]["rules"] if not rule["passed"]}


def test_block_oversized_order(client: TestClient) -> None:
    asset = create_asset(client)
    account = create_account(client)
    intent = create_intent(client, asset["id"], account["id"], notional=50_000)

    response = client.post("/risk/check-order", json=risk_payload(intent["id"], max_order_notional=10_000))

    assert response.status_code == 201
    risk_check = response.json()
    assert risk_check["status"] == "blocked"
    assert "max_order_notional" in failed_rule_names(risk_check)


def test_block_live_order_when_live_trading_disabled(client: TestClient) -> None:
    asset = create_asset(client)
    account = create_account(client, mode="live", live_trading_enabled=False)
    intent = create_intent(client, asset["id"], account["id"])

    response = client.post("/risk/check-order", json=risk_payload(intent["id"]))

    assert response.status_code == 201
    risk_check = response.json()
    assert risk_check["status"] == "blocked"
    assert "live_trading_enabled" in failed_rule_names(risk_check)


def test_block_auto_order_when_auto_disabled(client: TestClient) -> None:
    asset = create_asset(client, auto_enabled=False)
    account = create_account(client)
    intent = create_intent(client, asset["id"], account["id"], source_type="signal")

    response = client.post("/risk/check-order", json=risk_payload(intent["id"], order_mode="auto"))

    assert response.status_code == 201
    risk_check = response.json()
    assert risk_check["status"] == "blocked"
    assert "asset_manual_or_auto_enabled" in failed_rule_names(risk_check)


def test_allow_safe_paper_order_draft(client: TestClient) -> None:
    asset = create_asset(client)
    account = create_account(client)
    intent = create_intent(client, asset["id"], account["id"])
    pass_decision_gates(client, intent["id"], account["id"])

    response = client.post(f"/orders/intents/{intent['id']}/draft", json=risk_payload(intent["id"]))

    assert response.status_code == 201
    draft = response.json()
    assert draft["order_intent_id"] == intent["id"]
    assert draft["risk_status"] == "passed"
    assert draft["approval_status"] == "pending"
    assert draft["execution_status"] == "not_executable"


def test_order_decision_read_models_are_queryable(client: TestClient) -> None:
    asset = create_asset(client)
    account = create_account(client)
    intent = create_intent(client, asset["id"], account["id"])
    pass_decision_gates(client, intent["id"], account["id"])
    draft_response = client.post(f"/orders/intents/{intent['id']}/draft", json=risk_payload(intent["id"]))
    assert draft_response.status_code == 201
    draft = draft_response.json()
    approval_response = client.post(
        f"/orders/drafts/{draft['id']}/approve",
        json={"approver_id": "human-user", "decision_reason": "Decision detail read test."},
    )
    assert approval_response.status_code == 201

    intent_response = client.get(f"/orders/intents/{intent['id']}")
    assert intent_response.status_code == 200
    assert intent_response.json()["id"] == intent["id"]

    draft_read_response = client.get(f"/orders/drafts/{draft['id']}")
    assert draft_read_response.status_code == 200
    assert draft_read_response.json()["order_intent_id"] == intent["id"]

    risk_checks_response = client.get(f"/risk-checks?order_intent_id={intent['id']}")
    assert risk_checks_response.status_code == 200
    assert risk_checks_response.json()[0]["order_intent_id"] == intent["id"]

    approvals_response = client.get(f"/orders/drafts/{draft['id']}/approvals")
    assert approvals_response.status_code == 200
    assert approvals_response.json()[0]["decision_reason"] == "Decision detail read test."


def test_approval_writes_audit_log(client: TestClient) -> None:
    asset = create_asset(client)
    account = create_account(client)
    intent = create_intent(client, asset["id"], account["id"])
    pass_decision_gates(client, intent["id"], account["id"])
    draft_response = client.post(f"/orders/intents/{intent['id']}/draft", json=risk_payload(intent["id"]))
    assert draft_response.status_code == 201
    draft = draft_response.json()

    approval_response = client.post(
        f"/orders/drafts/{draft['id']}/approve",
        json={"approver_id": "human-user", "decision_reason": "Reviewed risk check."},
    )

    assert approval_response.status_code == 201
    approval = approval_response.json()
    assert approval["status"] == "approved"
    audit_logs = client.get("/audit-logs").json()
    assert any(log["action"] == "order_draft.approved" and log["entity_id"] == approval["id"] for log in audit_logs)
