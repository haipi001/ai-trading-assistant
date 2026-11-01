from fastapi.testclient import TestClient


def create_asset(client: TestClient) -> dict:
    response = client.post(
        "/assets",
        json={
            "symbol": "NVDA",
            "name": "NVIDIA Corporation",
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
            "name": "Self Logic Paper Account",
            "account_type": "brokerage",
            "broker": "manual",
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
            "name": "Long-term disciplined investing",
            "investment_style": "quality_growth",
            "allowed_markets": ["US_STOCKS", "CRYPTO_SPOT"],
            "forbidden_assets": ["HIGH_LEVERAGE_ETN"],
            "forbidden_actions": ["UNAPPROVED_LIVE_EXECUTION"],
            "max_single_position_pct": 0.2,
            "max_asset_class_pct": 0.7,
            "max_crypto_pct": 0.25,
            "max_single_exchange_pct": 0.2,
            "max_daily_loss_pct": 0.02,
            "max_monthly_drawdown_pct": 0.08,
            "leverage_allowed": False,
            "derivatives_allowed": False,
            "auto_execution_allowed": False,
            "human_approval_required": True,
            "cooldown_rules_json": {"after_loss_minutes": 60},
            "is_active": True,
        },
    )
    assert response.status_code == 201
    return response.json()


def create_playbook(client: TestClient) -> dict:
    response = client.post(
        "/strategy-playbooks",
        json={
            "user_id": "user-1",
            "name": "Earnings quality swing",
            "strategy_type": "swing",
            "applicable_markets": ["US_STOCKS"],
            "applicable_assets": ["NVDA"],
            "entry_conditions_json": {"requires_breakout": True},
            "exit_conditions_json": {"invalidate_on_revenue_miss": True},
            "risk_rules_json": {"max_position_pct": 0.1},
            "automation_level": "A3_ORDER_DRAFT",
            "requires_human_approval": True,
            "is_active": True,
        },
    )
    assert response.status_code == 201
    return response.json()


def create_thesis(client: TestClient, asset_id: str, account_id: str | None = None, playbook_id: str | None = None) -> dict:
    response = client.post(
        "/investment-theses",
        json={
            "user_id": "user-1",
            "asset_id": asset_id,
            "account_id": account_id,
            "strategy_playbook_id": playbook_id,
            "entry_reason": "GPU demand and earnings quality remain strong.",
            "key_drivers_json": {"drivers": ["datacenter_growth", "margin_strength"]},
            "invalidation_conditions_json": {"invalidate_if": ["datacenter_growth_slows"]},
            "expected_horizon": "swing",
            "target_condition": "Reassess after next earnings report.",
            "max_loss_tolerance_pct": 0.08,
            "position_plan_json": {"initial_weight": 0.05, "max_weight": 0.1},
            "confidence": 0.72,
            "source": "manual",
            "status": "active",
        },
    )
    assert response.status_code == 201
    return response.json()


def test_create_investment_constitution(client: TestClient) -> None:
    constitution = create_constitution(client)

    assert constitution["user_id"] == "user-1"
    assert constitution["auto_execution_allowed"] is False

    list_response = client.get("/investment-constitutions")
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1


def test_create_strategy_playbook(client: TestClient) -> None:
    playbook = create_playbook(client)

    assert playbook["automation_level"] == "A3_ORDER_DRAFT"
    assert playbook["requires_human_approval"] is True


def test_create_investment_thesis(client: TestClient) -> None:
    asset = create_asset(client)
    account = create_account(client)
    playbook = create_playbook(client)

    thesis = create_thesis(client, asset["id"], account["id"], playbook["id"])

    assert thesis["asset_id"] == asset["id"]
    assert thesis["account_id"] == account["id"]
    assert thesis["strategy_playbook_id"] == playbook["id"]


def test_create_thesis_violation(client: TestClient) -> None:
    asset = create_asset(client)
    thesis = create_thesis(client, asset["id"])

    response = client.post(
        "/thesis-violations",
        json={
            "thesis_id": thesis["id"],
            "user_id": "user-1",
            "violation_type": "THESIS_CONFLICT",
            "prior_user_statement": "I will sell only if datacenter growth slows.",
            "current_action": "User attempted to sell after a small intraday dip.",
            "explanation": "The action conflicts with the prior invalidation rule.",
            "intervention_level": "SOFT_WARNING",
            "resolved_status": "open",
        },
    )

    assert response.status_code == 201
    violation = response.json()
    assert violation["thesis_id"] == thesis["id"]
    assert violation["intervention_level"] == "SOFT_WARNING"


def test_create_automation_policy(client: TestClient) -> None:
    asset = create_asset(client)
    account = create_account(client)
    playbook = create_playbook(client)

    response = client.post(
        "/automation-policies",
        json={
            "user_id": "user-1",
            "account_id": account["id"],
            "asset_id": asset["id"],
            "strategy_playbook_id": playbook["id"],
            "automation_level": "A3_ORDER_DRAFT",
            "max_notional_per_order": 500,
            "max_orders_per_day": 2,
            "requires_approval": True,
            "allowed_actions": ["CREATE_ORDER_DRAFT"],
            "forbidden_actions": ["LIVE_EXECUTION"],
            "is_active": True,
        },
    )

    assert response.status_code == 201
    policy = response.json()
    assert policy["automation_level"] == "A3_ORDER_DRAFT"
    assert policy["requires_approval"] is True


def test_create_workflow_state(client: TestClient) -> None:
    response = client.post(
        "/workflow-states",
        json={
            "workflow_type": "trade_idea",
            "entity_id": "idea-1",
            "current_state": "IDEA_CREATED",
            "previous_state": None,
            "transition_reason": "User captured a new research idea.",
            "metadata_json": {"source": "manual"},
        },
    )

    assert response.status_code == 201
    workflow_state = response.json()
    assert workflow_state["current_state"] == "IDEA_CREATED"


def test_create_monthly_decision_review(client: TestClient) -> None:
    response = client.post(
        "/monthly-decision-reviews",
        json={
            "user_id": "user-1",
            "period_start": "2026-05-01",
            "period_end": "2026-05-31",
            "total_trades": 4,
            "thesis_aligned_trades": 3,
            "thesis_violating_trades": 1,
            "impulsive_trades": 1,
            "blocked_trades": 2,
            "bypassed_warnings": 0,
            "planned_trade_pnl": 1200,
            "impulsive_trade_pnl": -150,
            "overtrading_cost": 50,
            "top_behavior_patterns_json": [{"pattern_type": "FOMO_BUYING"}],
            "recommended_rule_updates_json": [{"rule": "cooldown_after_signal"}],
            "ai_summary": "Review is data-only in this phase; no AI call was made.",
        },
    )

    assert response.status_code == 201
    review = response.json()
    assert review["total_trades"] == 4
    assert review["thesis_violating_trades"] == 1


def test_order_intent_can_link_to_thesis_and_playbook(client: TestClient) -> None:
    asset = create_asset(client)
    account = create_account(client)
    playbook = create_playbook(client)
    thesis = create_thesis(client, asset["id"], account["id"], playbook["id"])

    response = client.post(
        "/orders/intents",
        json={
            "source_type": "manual",
            "asset_id": asset["id"],
            "account_id": account["id"],
            "investment_thesis_id": thesis["id"],
            "strategy_playbook_id": playbook["id"],
            "side": "buy",
            "order_type": "market",
            "notional": 250,
            "rationale": "Data model link test only.",
            "user_rationale": "Add only if thesis remains valid.",
        },
    )

    assert response.status_code == 201
    intent = response.json()
    assert intent["investment_thesis_id"] == thesis["id"]
    assert intent["strategy_playbook_id"] == playbook["id"]
    assert intent["user_rationale"] == "Add only if thesis remains valid."
