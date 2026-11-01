from fastapi.testclient import TestClient


def create_asset(client: TestClient, *, symbol: str = "NVDA") -> dict:
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
            "name": "Behavior Test Account",
            "account_type": "brokerage",
            "broker": "mock",
            "base_currency": "USD",
            "mode": "paper",
        },
    )
    assert response.status_code == 201
    return response.json()


def create_constitution(client: TestClient, *, max_single_position_pct: float = 0.2) -> dict:
    response = client.post(
        "/investment-constitutions",
        json={
            "user_id": "user-1",
            "version": "v1",
            "name": "Behavior constitution",
            "investment_style": "disciplined",
            "allowed_markets": ["US"],
            "forbidden_assets": [],
            "forbidden_actions": ["LIVE_EXECUTION"],
            "max_single_position_pct": max_single_position_pct,
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


def create_thesis(client: TestClient, asset_id: str, account_id: str) -> dict:
    response = client.post(
        "/investment-theses",
        json={
            "user_id": "user-1",
            "asset_id": asset_id,
            "account_id": account_id,
            "entry_reason": "Data center revenue growth and margin expansion remain intact.",
            "key_drivers_json": {"drivers": ["data_center_revenue_growth", "margin_expansion"]},
            "invalidation_conditions_json": {"invalidate_if": ["growth_breaks", "margin_contracts"]},
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


def create_intent(
    client: TestClient,
    asset_id: str,
    account_id: str,
    thesis_id: str,
    *,
    side: str = "buy",
    source_type: str = "manual",
) -> dict:
    response = client.post(
        "/orders/intents",
        json={
            "source_type": source_type,
            "asset_id": asset_id,
            "account_id": account_id,
            "investment_thesis_id": thesis_id,
            "side": side,
            "order_type": "market",
            "notional": 1_000,
            "rationale": "Behavior engine test intent.",
            "user_rationale": "Only act if consistent with thesis.",
        },
    )
    assert response.status_code == 201
    return response.json()


def setup_order(client: TestClient, *, side: str = "buy", max_single_position_pct: float = 0.2) -> tuple[dict, dict, dict, dict]:
    asset = create_asset(client)
    account = create_account(client)
    create_constitution(client, max_single_position_pct=max_single_position_pct)
    thesis = create_thesis(client, asset["id"], account["id"])
    intent = create_intent(client, asset["id"], account["id"], thesis["id"], side=side)
    return asset, account, thesis, intent


def test_fomo_buy_creates_hard_confirm(client: TestClient) -> None:
    _, _, thesis, intent = setup_order(client, side="buy")

    response = client.post(
        "/behavior/evaluate-order",
        json={
            "order_intent_id": intent["id"],
            "user_id": "user-1",
            "market_move": {"pct_change_1d": 0.12},
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["level"] == "HARD_CONFIRM"
    assert body["bypass_allowed"] is True
    assert body["patterns"][0]["pattern_type"] == "FOMO_BUYING"
    assert thesis["entry_reason"] in body["message"]


def test_panic_sell_creates_warning_or_hard_confirm(client: TestClient) -> None:
    _, _, thesis, intent = setup_order(client, side="sell")

    response = client.post(
        "/behavior/evaluate-order",
        json={
            "order_intent_id": intent["id"],
            "user_id": "user-1",
            "market_move": {"pct_change_1d": -0.09},
            "thesis_invalidation_triggered": False,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["level"] in {"SOFT_WARNING", "HARD_CONFIRM"}
    assert body["patterns"][0]["pattern_type"] == "PANIC_SELLING"
    assert "drawdown" in body["message"].lower()
    assert thesis["entry_reason"] in body["message"]


def test_oversized_concentration_creates_block(client: TestClient) -> None:
    _, _, _, intent = setup_order(client, side="buy", max_single_position_pct=0.2)

    response = client.post(
        "/behavior/evaluate-order",
        json={
            "order_intent_id": intent["id"],
            "user_id": "user-1",
            "projected_position_pct": 0.35,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["level"] == "BLOCK"
    assert body["bypass_allowed"] is False
    assert body["patterns"][0]["pattern_type"] == "CONCENTRATION_DRIFT"


def test_thesis_conflict_creates_violation_and_intervention(client: TestClient) -> None:
    _, _, thesis, intent = setup_order(client, side="sell")

    response = client.post(
        "/behavior/evaluate-order",
        json={
            "order_intent_id": intent["id"],
            "user_id": "user-1",
            "behavior_flags": ["THESIS_CONFLICT_TRADE"],
            "thesis_conflict": True,
            "current_action": "Sell NVDA because the price feels uncomfortable.",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["level"] == "HARD_CONFIRM"
    assert body["thesis_violation"]["thesis_id"] == thesis["id"]
    assert body["thesis_violation"]["related_order_intent_id"] == intent["id"]
    assert body["intervention"]["order_intent_id"] == intent["id"]
    assert thesis["entry_reason"] in body["message"]


def test_user_response_is_stored(client: TestClient) -> None:
    _, _, _, intent = setup_order(client, side="buy")
    evaluation = client.post(
        "/behavior/evaluate-order",
        json={
            "order_intent_id": intent["id"],
            "user_id": "user-1",
            "market_move": {"pct_change_1d": 0.12},
        },
    ).json()

    response = client.post(
        f"/behavior/interventions/{evaluation['intervention']['id']}/respond",
        json={
            "user_response": "I confirm the thesis changed because new structured facts improved.",
            "bypassed": True,
        },
    )

    assert response.status_code == 200
    intervention = response.json()
    assert intervention["user_response"] == "I confirm the thesis changed because new structured facts improved."
    assert intervention["bypassed"] is True

    interventions = client.get("/behavior/interventions").json()
    assert interventions[0]["required_user_action"]
    assert interventions[0]["bypass_allowed"] is True


def test_behavior_profile_summarizes_recurring_patterns(client: TestClient) -> None:
    _, _, _, intent = setup_order(client, side="buy")
    response = client.post(
        "/behavior/evaluate-order",
        json={
            "order_intent_id": intent["id"],
            "user_id": "user-1",
            "market_move": {"pct_change_1d": 0.12},
        },
    )
    assert response.status_code == 201

    client.post(
        f"/behavior/interventions/{response.json()['intervention']['id']}/respond",
        json={
            "user_response": "I overrode this once for testing.",
            "bypassed": True,
        },
    )

    profile_response = client.get("/behavior/profile/user-1")
    assert profile_response.status_code == 200
    profile = profile_response.json()
    assert profile["user_id"] == "user-1"
    assert profile["total_patterns"] >= 1
    assert profile["bypassed_interventions"] == 1
    assert profile["recurring_patterns"][0]["pattern_type"] == "FOMO_BUYING"
    assert "cumulative_penalty_score" in profile["current_baseline"]


def test_repeated_bypasses_escalate_to_block(client: TestClient) -> None:
    _, _, _, first_intent = setup_order(client, side="buy")
    first_response = client.post(
        "/behavior/evaluate-order",
        json={
            "order_intent_id": first_intent["id"],
            "user_id": "user-1",
            "market_move": {"pct_change_1d": 0.12},
        },
    )
    assert first_response.status_code == 201
    first_intervention = first_response.json()["intervention"]["id"]
    bypass_response = client.post(
        f"/behavior/interventions/{first_intervention}/respond",
        json={"user_response": "Bypassing once for test.", "bypassed": True},
    )
    assert bypass_response.status_code == 200

    _, _, _, second_intent = setup_order(client, side="buy")
    second_response = client.post(
        "/behavior/evaluate-order",
        json={
            "order_intent_id": second_intent["id"],
            "user_id": "user-1",
            "market_move": {"pct_change_1d": 0.12},
        },
    )
    assert second_response.status_code == 201
    assert second_response.json()["level"] == "BLOCK"
