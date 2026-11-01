from fastapi.testclient import TestClient


def create_asset(client: TestClient, symbol: str = "AAPL") -> dict:
    response = client.post(
        "/assets",
        json={
            "symbol": symbol,
            "name": f"{symbol} Test Asset",
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
            "name": "Automation Policy Paper Account",
            "account_type": "brokerage",
            "broker": "mock",
            "base_currency": "USD",
            "mode": "paper",
        },
    )
    assert response.status_code == 201
    return response.json()


def create_constitution(client: TestClient) -> dict:
    response = client.post(
        "/investment-constitutions",
        json={
            "user_id": "user-1",
            "version": "v1",
            "name": "Automation policy constitution",
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
    assert response.status_code == 201
    return response.json()


def create_risk_budget(client: TestClient, constitution_id: str, account_id: str, max_order_notional: float = 10_000) -> dict:
    response = client.post(
        "/risk-budgets",
        json={
            "user_id": "user-1",
            "constitution_id": constitution_id,
            "account_id": account_id,
            "asset_class": "stock",
            "max_allocation_pct": 0.8,
            "max_loss_pct": 0.08,
            "max_order_notional": max_order_notional,
            "max_leverage": 1,
            "rebalance_threshold_pct": 0.05,
        },
    )
    assert response.status_code == 201
    return response.json()


def create_policy(
    client: TestClient,
    *,
    level: str,
    account_id: str | None = None,
    asset_id: str | None = None,
    allowed_actions: list[str] | None = None,
    forbidden_actions: list[str] | None = None,
    requires_approval: bool = True,
) -> dict:
    response = client.post(
        "/automation-policies",
        json={
            "user_id": "user-1",
            "account_id": account_id,
            "asset_id": asset_id,
            "automation_level": level,
            "max_notional_per_order": 1_000,
            "max_orders_per_day": 2,
            "requires_approval": requires_approval,
            "allowed_actions": allowed_actions or [],
            "forbidden_actions": forbidden_actions or ["LIVE_EXECUTION"],
            "is_active": True,
        },
    )
    assert response.status_code == 201
    return response.json()


def test_default_policy_is_read_only(client: TestClient) -> None:
    response = client.post("/automation-policy/effective", json={"user_id": "user-1"})

    assert response.status_code == 200
    policy = response.json()
    assert policy["automation_level"] == "A0_READ_ONLY"
    assert policy["source"] == "default_read_only"

    evaluate = client.post("/automation-policy/evaluate", json={"user_id": "user-1"}).json()
    assert evaluate["can_create_order_intent"] is False
    assert evaluate["can_create_order_draft"] is False
    assert evaluate["can_execute_paper"] is False
    assert evaluate["can_execute_live"] is False
    assert "default_read_only_policy" in evaluate["blocking_reasons"]


def test_a3_can_draft_but_cannot_execute(client: TestClient) -> None:
    asset = create_asset(client)
    account = create_account(client)
    create_policy(
        client,
        level="A3_ORDER_DRAFT",
        account_id=account["id"],
        asset_id=asset["id"],
        allowed_actions=["CREATE_ORDER_INTENT", "CREATE_ORDER_DRAFT"],
    )

    response = client.post(
        "/automation-policy/evaluate",
        json={
            "user_id": "user-1",
            "account_id": account["id"],
            "asset_id": asset["id"],
            "action": "CREATE_ORDER_DRAFT",
            "gates_passed": True,
            "human_approved": True,
        },
    )

    assert response.status_code == 200
    result = response.json()
    assert result["policy"]["automation_level"] == "A3_ORDER_DRAFT"
    assert result["can_create_order_intent"] is True
    assert result["can_create_order_draft"] is True
    assert result["can_execute_paper"] is False
    assert result["can_execute_live"] is False


def test_a4_requires_approval(client: TestClient) -> None:
    asset = create_asset(client)
    account = create_account(client)
    create_policy(
        client,
        level="A4_APPROVAL_EXECUTION",
        account_id=account["id"],
        asset_id=asset["id"],
        allowed_actions=["EXECUTE_PAPER"],
        requires_approval=True,
    )

    without_approval = client.post(
        "/automation-policy/evaluate",
        json={
            "user_id": "user-1",
            "account_id": account["id"],
            "asset_id": asset["id"],
            "action": "EXECUTE_PAPER",
            "gates_passed": True,
            "human_approved": False,
        },
    ).json()
    with_approval = client.post(
        "/automation-policy/evaluate",
        json={
            "user_id": "user-1",
            "account_id": account["id"],
            "asset_id": asset["id"],
            "action": "EXECUTE_PAPER",
            "gates_passed": True,
            "human_approved": True,
        },
    ).json()

    assert without_approval["requires_human_approval"] is True
    assert without_approval["can_execute_paper"] is False
    assert with_approval["can_execute_paper"] is True


def test_a5_allows_only_whitelisted_actions(client: TestClient) -> None:
    asset = create_asset(client, "SPY")
    other_asset = create_asset(client, "QQQ")
    account = create_account(client)
    constitution = create_constitution(client)
    create_risk_budget(client, constitution["id"], account["id"], max_order_notional=10_000)
    policy = create_policy(
        client,
        level="A5_CONTROLLED_AUTO",
        account_id=account["id"],
        asset_id=asset["id"],
        allowed_actions=["DCA"],
        requires_approval=False,
    )

    allowed = client.post(
        "/automation-policy/evaluate",
        json={
            "user_id": "user-1",
            "account_id": account["id"],
            "asset_id": asset["id"],
            "action": "DCA",
            "order_notional": 500,
            "gates_passed": True,
            "risk_budget_passed": True,
        },
    ).json()
    not_whitelisted_action = client.post(
        "/automation-policy/evaluate",
        json={
            "user_id": "user-1",
            "account_id": account["id"],
            "asset_id": asset["id"],
            "action": "MOMENTUM_CHASE",
            "order_notional": 500,
            "gates_passed": True,
            "risk_budget_passed": True,
        },
    ).json()
    not_whitelisted_asset = client.post(
        "/automation-policy/evaluate",
        json={
            "user_id": "user-1",
            "account_id": account["id"],
            "asset_id": other_asset["id"],
            "action": "DCA",
            "order_notional": 500,
            "gates_passed": True,
            "risk_budget_passed": True,
        },
    ).json()

    assert allowed["policy"]["id"] == policy["id"]
    assert allowed["can_execute_controlled_auto"] is True
    assert not_whitelisted_action["can_execute_controlled_auto"] is False
    assert "action_not_allowed_by_policy" in not_whitelisted_action["blocking_reasons"]
    assert not_whitelisted_asset["can_execute_controlled_auto"] is False
    assert "controlled_auto_asset_not_whitelisted" in not_whitelisted_asset["blocking_reasons"]

    audit_logs = client.get("/audit-logs").json()
    assert any(log["action"] == "automation_policy.controlled_auto_evaluated" for log in audit_logs)


def test_a6_is_rejected_as_not_implemented(client: TestClient) -> None:
    create_policy(client, level="A6_ADAPTIVE_AUTO_FUTURE")

    response = client.post("/automation-policy/effective", json={"user_id": "user-1"})

    assert response.status_code == 501
    assert "not implemented" in response.json()["detail"]


def test_live_execution_blocked_by_default(client: TestClient) -> None:
    asset = create_asset(client)
    account = create_account(client)
    create_policy(
        client,
        level="A4_APPROVAL_EXECUTION",
        account_id=account["id"],
        asset_id=asset["id"],
        allowed_actions=["EXECUTE_LIVE"],
        forbidden_actions=[],
    )

    response = client.post(
        "/automation-policy/evaluate",
        json={
            "user_id": "user-1",
            "account_id": account["id"],
            "asset_id": asset["id"],
            "action": "EXECUTE_LIVE",
            "gates_passed": True,
            "human_approved": True,
            "live_trading_enabled": False,
        },
    )

    assert response.status_code == 200
    result = response.json()
    assert result["can_execute_live"] is False
    assert "live_trading_disabled" in result["blocking_reasons"]
