from fastapi.testclient import TestClient


def create_asset(client: TestClient, symbol: str) -> dict:
    response = client.post(
        "/assets",
        json={
            "symbol": symbol,
            "name": f"{symbol} Review Asset",
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
            "name": "Monthly Review Paper Account",
            "account_type": "brokerage",
            "broker": "mock",
            "base_currency": "USD",
            "mode": "paper",
        },
    )
    assert response.status_code == 201
    return response.json()


def create_position(client: TestClient, account_id: str, asset_id: str, pnl: float) -> dict:
    response = client.post(
        "/positions/import",
        json={
            "account_id": account_id,
            "asset_id": asset_id,
            "quantity": 10,
            "average_cost": 100,
            "market_price": 100,
            "market_value": 1_000,
            "unrealized_pnl": pnl,
            "realized_pnl": 0,
            "weight": 0.1,
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
            "entry_reason": "Hold while revenue growth and margin expansion remain intact.",
            "key_drivers_json": {"drivers": ["revenue_growth", "margin_expansion"]},
            "invalidation_conditions_json": {"invalidate_if": ["revenue_growth_breaks"]},
            "expected_horizon": "swing",
            "target_condition": "Review after earnings.",
            "max_loss_tolerance_pct": 0.08,
            "position_plan_json": {"max_weight": 0.1},
            "confidence": 0.72,
            "source": "manual",
            "status": "active",
        },
    )
    assert response.status_code == 201
    return response.json()


def create_intent(client: TestClient, account_id: str, asset_id: str, thesis_id: str | None = None) -> dict:
    response = client.post(
        "/orders/intents",
        json={
            "source_type": "manual",
            "asset_id": asset_id,
            "account_id": account_id,
            "investment_thesis_id": thesis_id,
            "side": "buy",
            "order_type": "market",
            "notional": 1_000,
            "rationale": "Monthly decision review test intent.",
            "user_rationale": "Review decision attribution.",
        },
    )
    assert response.status_code == 201
    return response.json()


def create_behavior_pattern(client: TestClient, pattern_type: str, estimated_cost: float = 0) -> dict:
    response = client.post(
        "/behavior-patterns",
        json={
            "user_id": "user-1",
            "pattern_type": pattern_type,
            "description": f"{pattern_type} detected during monthly review test.",
            "evidence_json": {"source": "test"},
            "estimated_cost": estimated_cost,
            "frequency": 1,
            "severity": "high",
        },
    )
    assert response.status_code == 201
    return response.json()


def create_intervention(
    client: TestClient,
    pattern_id: str,
    order_intent_id: str,
    *,
    level: str = "HARD_CONFIRM",
    bypassed: bool = False,
) -> dict:
    response = client.post(
        "/behavior-interventions",
        json={
            "user_id": "user-1",
            "pattern_id": pattern_id,
            "order_intent_id": order_intent_id,
            "intervention_level": level,
            "message": "Review intervention message.",
            "bypassed": bypassed,
        },
    )
    assert response.status_code == 201
    return response.json()


def generate_review(client: TestClient) -> dict:
    response = client.post(
        "/reviews/monthly/generate",
        json={
            "user_id": "user-1",
            "period_start": "2026-01-01",
            "period_end": "2026-12-31",
            "provider": "mock",
        },
    )
    assert response.status_code == 201
    return response.json()


def setup_planned_and_impulsive_trades(client: TestClient) -> tuple[dict, dict, dict, dict]:
    account = create_account(client)
    planned_asset = create_asset(client, "AAPL")
    impulsive_asset = create_asset(client, "TSLA")
    planned_thesis = create_thesis(client, planned_asset["id"], account["id"])
    impulsive_thesis = create_thesis(client, impulsive_asset["id"], account["id"])
    create_position(client, account["id"], planned_asset["id"], 300)
    create_position(client, account["id"], impulsive_asset["id"], -120)
    planned_intent = create_intent(client, account["id"], planned_asset["id"], planned_thesis["id"])
    impulsive_intent = create_intent(client, account["id"], impulsive_asset["id"], impulsive_thesis["id"])
    return planned_intent, impulsive_intent, impulsive_thesis, account


def test_review_detects_impulsive_trades(client: TestClient) -> None:
    _, impulsive_intent, _, _ = setup_planned_and_impulsive_trades(client)
    pattern = create_behavior_pattern(client, "FOMO_BUYING", estimated_cost=250)
    create_intervention(client, pattern["id"], impulsive_intent["id"], bypassed=True)

    payload = generate_review(client)

    assert payload["metrics"]["impulsive_trades"] == 1
    assert payload["metrics"]["warnings_bypassed"] == 1
    assert payload["most_common_behavior_pattern"] == "FOMO_BUYING"
    assert payload["review"]["top_behavior_patterns_json"][0]["pattern_type"] == "FOMO_BUYING"


def test_review_detects_thesis_violations(client: TestClient) -> None:
    _, impulsive_intent, thesis, _ = setup_planned_and_impulsive_trades(client)
    response = client.post(
        "/thesis-violations",
        json={
            "thesis_id": thesis["id"],
            "user_id": "user-1",
            "related_order_intent_id": impulsive_intent["id"],
            "violation_type": "THESIS_CONFLICT",
            "prior_user_statement": "Hold while revenue growth remains intact.",
            "current_action": "Buy more because price moved quickly.",
            "explanation": "Action conflicts with recorded discipline.",
            "intervention_level": "HARD_CONFIRM",
            "resolved_status": "open",
        },
    )
    assert response.status_code == 201

    payload = generate_review(client)

    assert payload["metrics"]["thesis_violating_trades"] == 1
    assert payload["review"]["thesis_violating_trades"] == 1


def test_review_calculates_planned_vs_impulsive_pnl(client: TestClient) -> None:
    _, impulsive_intent, _, _ = setup_planned_and_impulsive_trades(client)
    pattern = create_behavior_pattern(client, "FOMO_BUYING")
    create_intervention(client, pattern["id"], impulsive_intent["id"])

    payload = generate_review(client)

    assert payload["metrics"]["planned_trade_pnl"] == 300
    assert payload["metrics"]["impulsive_trade_pnl"] == -120
    assert payload["review"]["planned_trade_pnl"] == 300
    assert payload["review"]["impulsive_trade_pnl"] == -120


def test_review_suggests_playbook_update(client: TestClient) -> None:
    _, impulsive_intent, _, _ = setup_planned_and_impulsive_trades(client)
    pattern = create_behavior_pattern(client, "OVERTRADING", estimated_cost=75)
    create_intervention(client, pattern["id"], impulsive_intent["id"])

    payload = generate_review(client)

    assert payload["metrics"]["overtrading_cost"] == 75
    assert payload["recommended_playbook_updates"]
    assert payload["recommended_playbook_updates"][0]["target"] == "StrategyPlaybook"
    assert payload["recommended_playbook_updates"][0]["requires_user_approval"] is True


def test_review_never_applies_rule_updates_automatically(client: TestClient) -> None:
    _, impulsive_intent, _, _ = setup_planned_and_impulsive_trades(client)
    pattern = create_behavior_pattern(client, "FOMO_BUYING")
    create_intervention(client, pattern["id"], impulsive_intent["id"], level="BLOCK")

    payload = generate_review(client)

    assert payload["automatic_rule_updates_applied"] is False
    assert payload["metrics"]["biggest_prevented_loss"] == 0
    for update in payload["review"]["recommended_rule_updates_json"]:
        assert update["requires_user_approval"] is True
        assert update["automatic_update_applied"] is False
    assert any(log["action"] == "monthly_decision_review.generated" for log in client.get("/audit-logs").json())


def test_monthly_review_list_and_get_endpoints(client: TestClient) -> None:
    setup_planned_and_impulsive_trades(client)
    created = generate_review(client)

    list_response = client.get("/reviews/monthly?user_id=user-1")
    assert list_response.status_code == 200
    assert list_response.json()[0]["id"] == created["review"]["id"]

    get_response = client.get(f"/reviews/monthly/{created['review']['id']}")
    assert get_response.status_code == 200
    assert get_response.json()["id"] == created["review"]["id"]


def create_monthly_review_record(
    client: TestClient,
    *,
    period_start: str,
    period_end: str,
    impulsive_trades: int,
    thesis_violating_trades: int,
    blocked_trades: int,
    planned_trade_pnl: float,
    pattern_type: str = "FOMO_BUYING",
) -> dict:
    response = client.post(
        "/monthly-decision-reviews",
        json={
            "user_id": "user-1",
            "period_start": period_start,
            "period_end": period_end,
            "total_trades": 5,
            "thesis_aligned_trades": 4 - thesis_violating_trades,
            "thesis_violating_trades": thesis_violating_trades,
            "impulsive_trades": impulsive_trades,
            "blocked_trades": blocked_trades,
            "bypassed_warnings": 1 if impulsive_trades else 0,
            "planned_trade_pnl": planned_trade_pnl,
            "impulsive_trade_pnl": -50 * impulsive_trades,
            "overtrading_cost": 25 * impulsive_trades,
            "top_behavior_patterns_json": [{"pattern_type": pattern_type, "count": impulsive_trades or 1}],
            "recommended_rule_updates_json": [
                {
                    "target": "StrategyPlaybook",
                    "update_type": "add_pre_trade_cooldown_checklist",
                    "requires_user_approval": True,
                    "automatic_update_applied": False,
                }
            ],
            "ai_summary": "Monthly review fixture.",
        },
    )
    assert response.status_code == 201
    return response.json()


def test_quarterly_trend_summarizes_recent_monthly_reviews(client: TestClient) -> None:
    create_monthly_review_record(
        client,
        period_start="2026-01-01",
        period_end="2026-01-31",
        impulsive_trades=3,
        thesis_violating_trades=2,
        blocked_trades=1,
        planned_trade_pnl=100,
    )
    create_monthly_review_record(
        client,
        period_start="2026-02-01",
        period_end="2026-02-28",
        impulsive_trades=2,
        thesis_violating_trades=1,
        blocked_trades=1,
        planned_trade_pnl=150,
    )
    create_monthly_review_record(
        client,
        period_start="2026-03-01",
        period_end="2026-03-31",
        impulsive_trades=1,
        thesis_violating_trades=0,
        blocked_trades=2,
        planned_trade_pnl=250,
    )

    response = client.get("/reviews/monthly/quarterly-trend?user_id=user-1&months=3")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["review_count"] == 3
    assert payload["totals"]["total_trades"] == 15
    assert payload["totals"]["impulsive_trades"] == 6
    assert payload["totals"]["thesis_violating_trades"] == 3
    assert payload["trend"]["impulsive_trades"] == "improving"
    assert payload["trend"]["planned_pnl"] == "improving"
    assert payload["top_behavior_patterns"][0]["pattern_type"] == "FOMO_BUYING"
    assert payload["execution_available"] is False
    assert payload["automatic_rule_updates_applied"] is False


def test_quarterly_trend_blocks_without_monthly_reviews(client: TestClient) -> None:
    response = client.get("/reviews/monthly/quarterly-trend?user_id=user-1&months=3")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "blocked"
    assert payload["blockers"] == ["monthly_reviews_missing"]
    assert payload["execution_available"] is False
