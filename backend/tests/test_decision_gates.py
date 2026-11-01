from fastapi.testclient import TestClient


def create_asset(client: TestClient, *, symbol: str = "AAPL", asset_type: str = "stock") -> dict:
    response = client.post(
        "/assets",
        json={
            "symbol": symbol,
            "name": f"{symbol} Test Asset",
            "asset_type": asset_type,
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
            "name": "Decision Gate Paper Account",
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
            "name": "Gate test constitution",
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


def create_risk_budget(client: TestClient, constitution_id: str, account_id: str, *, max_order_notional: float = 10_000) -> dict:
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


def create_thesis(client: TestClient, asset_id: str, account_id: str) -> dict:
    response = client.post(
        "/investment-theses",
        json={
            "user_id": "user-1",
            "asset_id": asset_id,
            "account_id": account_id,
            "entry_reason": "Revenue growth thesis remains active.",
            "key_drivers_json": {"drivers": ["revenue_growth"]},
            "invalidation_conditions_json": {"invalidate_if": ["growth_breaks"]},
            "expected_horizon": "swing",
            "target_condition": "Review at next earnings.",
            "max_loss_tolerance_pct": 0.08,
            "position_plan_json": {"max_weight": 0.1},
            "confidence": 0.7,
            "source": "manual",
            "status": "active",
        },
    )
    assert response.status_code == 201
    return response.json()


def create_report(client: TestClient, data_snapshot_id: str = "snapshot-gates") -> dict:
    response = client.post(
        "/reports/generate",
        json={
            "report_type": "single_asset_research",
            "data_snapshot_id": data_snapshot_id,
            "input_facts": {"revenue_growth": "positive", "risks": ["valuation"]},
            "provider": "mock",
        },
    )
    assert response.status_code == 201
    return response.json()


def create_quality_snapshot(client: TestClient, symbols: list[str] | None = None) -> str:
    connection_response = client.post(
        "/data-sources/connections",
        json={
            "name": "Decision Gate Quality Source",
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


def create_intent(client: TestClient, asset_id: str, account_id: str, thesis_id: str, *, notional: float = 1_000) -> dict:
    response = client.post(
        "/orders/intents",
        json={
            "source_type": "manual",
            "asset_id": asset_id,
            "account_id": account_id,
            "investment_thesis_id": thesis_id,
            "side": "buy",
            "order_type": "market",
            "notional": notional,
            "rationale": "Decision gate test intent.",
            "user_rationale": "Fits active thesis.",
        },
    )
    assert response.status_code == 201
    return response.json()


def setup_gate_ready_order(client: TestClient, *, notional: float = 1_000, max_order_notional: float = 10_000) -> tuple[dict, dict, dict, str]:
    asset = create_asset(client)
    account = create_account(client)
    constitution = create_constitution(client)
    create_risk_budget(client, constitution["id"], account["id"], max_order_notional=max_order_notional)
    thesis = create_thesis(client, asset["id"], account["id"])
    intent = create_intent(client, asset["id"], account["id"], thesis["id"], notional=notional)
    snapshot_id = create_quality_snapshot(client, [asset["symbol"]])
    create_report(client, snapshot_id)
    client.post("/mock/update-quotes")
    return asset, account, intent, snapshot_id


def passing_gate_payload(order_intent_id: str, data_snapshot_id: str, **overrides) -> dict:
    payload = {
        "order_intent_id": order_intent_id,
        "user_id": "user-1",
        "data_snapshot_id": data_snapshot_id,
        "data_quality_status": "acceptable",
        "quality_report_required": True,
        "min_data_quality_score": 0.75,
        "research_report_required": True,
        "min_research_confidence": 0.5,
        "current_position_pct": 0.02,
        "order_position_pct": 0.03,
        "asset_class_pct": 0.3,
        "crypto_pct": 0,
        "exchange_pct": 0.1,
        "daily_loss_pct": 0,
        "monthly_drawdown_pct": 0,
        "current_leverage": 0,
        "behavior_flags": [],
        "latest_quote_required": True,
        "max_quote_age_seconds": 900,
        "source_timestamp_valid": True,
        "broker_status": "healthy",
        "exchange_status": "healthy",
        "expected_slippage_pct": 0.001,
        "max_slippage_pct": 0.01,
        "order_size_executable": True,
        "execution_mode": "paper",
        "action": "CREATE_ORDER_DRAFT",
    }
    payload.update(overrides)
    return payload


def gate_by_type(gates: list[dict], gate_type: str) -> dict:
    return next(gate for gate in gates if gate["gate_type"] == gate_type)


def test_research_gate_blocks_missing_data(client: TestClient) -> None:
    _, _, intent, snapshot_id = setup_gate_ready_order(client)

    response = client.post(
        "/decision-gates/evaluate",
        json=passing_gate_payload(intent["id"], snapshot_id) | {"data_snapshot_id": None},
    )

    assert response.status_code == 201
    research_gate = gate_by_type(response.json()["gates"], "RESEARCH_GATE")
    assert research_gate["status"] == "BLOCKED"
    assert "data_snapshot_missing" in research_gate["blocking_reasons_json"]


def test_thesis_gate_creates_thesis_violation(client: TestClient) -> None:
    _, _, intent, snapshot_id = setup_gate_ready_order(client)

    response = client.post(
        "/decision-gates/evaluate",
        json=passing_gate_payload(
            intent["id"],
            snapshot_id,
            thesis_conflict=True,
            prior_user_statement="Only add if revenue growth stays strong.",
            current_action="Buy despite invalidation.",
        ),
    )

    assert response.status_code == 201
    thesis_gate = gate_by_type(response.json()["gates"], "THESIS_GATE")
    assert thesis_gate["status"] == "BLOCKED"
    violations = client.get("/thesis-violations").json()
    assert len(violations) == 1
    assert violations[0]["related_order_intent_id"] == intent["id"]


def test_risk_gate_blocks_oversized_order(client: TestClient) -> None:
    _, _, intent, snapshot_id = setup_gate_ready_order(client, notional=50_000, max_order_notional=10_000)

    response = client.post("/decision-gates/evaluate", json=passing_gate_payload(intent["id"], snapshot_id))

    assert response.status_code == 201
    risk_gate = gate_by_type(response.json()["gates"], "RISK_GATE")
    assert risk_gate["status"] == "BLOCKED"
    assert "risk_budget_max_order_notional_exceeded" in risk_gate["blocking_reasons_json"]


def test_behavior_gate_creates_hard_confirm_on_fomo(client: TestClient) -> None:
    _, _, intent, snapshot_id = setup_gate_ready_order(client)

    response = client.post(
        "/decision-gates/evaluate",
        json=passing_gate_payload(intent["id"], snapshot_id, behavior_flags=["FOMO_BUYING"]),
    )

    assert response.status_code == 201
    behavior_gate = gate_by_type(response.json()["gates"], "BEHAVIOR_GATE")
    assert behavior_gate["status"] == "HARD_CONFIRM_REQUIRED"
    assert behavior_gate["recommended_intervention_level"] == "HARD_CONFIRM"
    interventions = client.get("/behavior-interventions").json()
    assert len(interventions) == 1
    assert interventions[0]["order_intent_id"] == intent["id"]


def test_execution_gate_blocks_stale_quote(client: TestClient) -> None:
    _, _, intent, snapshot_id = setup_gate_ready_order(client)

    response = client.post(
        "/decision-gates/evaluate",
        json=passing_gate_payload(intent["id"], snapshot_id, max_quote_age_seconds=-1),
    )

    assert response.status_code == 201
    execution_gate = gate_by_type(response.json()["gates"], "EXECUTION_GATE")
    assert execution_gate["status"] == "BLOCKED"
    assert "latest_quote_stale" in execution_gate["blocking_reasons_json"]


def test_research_gate_blocks_low_quality_report(client: TestClient) -> None:
    asset = create_asset(client)
    account = create_account(client)
    constitution = create_constitution(client)
    create_risk_budget(client, constitution["id"], account["id"])
    thesis = create_thesis(client, asset["id"], account["id"])
    intent = create_intent(client, asset["id"], account["id"], thesis["id"])

    connection_response = client.post(
        "/data-sources/connections",
        json={
            "name": "Low Quality Source",
            "provider": "mock_market_data",
            "source_type": "market_data",
            "mode": "read_only",
        },
    )
    assert connection_response.status_code == 201
    connection = connection_response.json()
    low_quality_import = client.post(
        f"/data-sources/connections/{connection['id']}/import-quotes",
        json={"symbols": [asset["symbol"], "UNKNOWN"], "asset_type": "stock", "market": "US", "currency": "USD"},
    )
    assert low_quality_import.status_code == 201

    from_snapshot_id = low_quality_import.json()["snapshot"]["id"]
    report_response = client.post(
        "/reports/generate",
        json={
            "report_type": "single_asset_research",
            "data_snapshot_id": from_snapshot_id,
            "input_facts": {"revenue_growth": "positive", "risks": ["valuation"]},
            "provider": "mock",
        },
    )
    assert report_response.status_code == 409
    detail = report_response.json()["detail"]
    assert detail["code"] == "data_trust_gate_blocked"
    assert "quality_not_valid" in detail["blockers"]
    assert "promotion_stage_not_trusted" in detail["blockers"]


def test_all_gates_must_pass_before_order_draft(client: TestClient) -> None:
    _, _, intent, snapshot_id = setup_gate_ready_order(client)

    missing_gates_response = client.post(f"/orders/intents/{intent['id']}/draft", json={"order_intent_id": intent["id"]})
    assert missing_gates_response.status_code == 422
    assert "decision gates" in missing_gates_response.json()["detail"]

    gate_response = client.post("/decision-gates/evaluate", json=passing_gate_payload(intent["id"], snapshot_id))
    assert gate_response.status_code == 201
    assert gate_response.json()["all_passed"] is True

    draft_response = client.post(f"/orders/intents/{intent['id']}/draft", json={"order_intent_id": intent["id"]})
    assert draft_response.status_code == 201
    draft = draft_response.json()
    assert draft["order_intent_id"] == intent["id"]
    assert draft["decision_gate_results"]["RESEARCH_GATE"]["status"] == "PASSED"
    assert draft["behavior_status"] == "passed"


def test_decision_gate_replay_builds_review_only_evidence_packet(client: TestClient) -> None:
    _, _, intent, snapshot_id = setup_gate_ready_order(client)
    gate_response = client.post("/decision-gates/evaluate", json=passing_gate_payload(intent["id"], snapshot_id))
    assert gate_response.status_code == 201

    replay_response = client.post(f"/decision-gates/order-intent/{intent['id']}/replay")

    assert replay_response.status_code == 200
    replay = replay_response.json()
    assert replay["order_intent_id"] == intent["id"]
    assert replay["replay_status"] == "completed"
    assert replay["policy_version"] == "decision-gate-local-v1"
    assert replay["order_creation_allowed"] is False
    assert replay["execution_available"] is False
    assert replay["live_execution_available"] is False
    assert len(replay["items"]) == 5
    assert {item["gate_type"] for item in replay["items"]} == {
        "RESEARCH_GATE",
        "THESIS_GATE",
        "RISK_GATE",
        "BEHAVIOR_GATE",
        "EXECUTION_GATE",
    }
    assert all(item["replayed_status"] == "matched" for item in replay["items"])
    assert all(item["evidence_hash"] for item in replay["items"])
    assert replay["replay_hash"]

    audit_logs = client.get("/audit-logs").json()
    assert any(log["action"] == "decision_gate.replayed" and log["entity_id"] == intent["id"] for log in audit_logs)


def test_decision_gate_replay_blocks_when_gate_history_missing(client: TestClient) -> None:
    _, _, intent, _ = setup_gate_ready_order(client)

    replay_response = client.post(f"/decision-gates/order-intent/{intent['id']}/replay")

    assert replay_response.status_code == 200
    replay = replay_response.json()
    assert replay["replay_status"] == "blocked"
    assert replay["missing_gate_types"] == [
        "RESEARCH_GATE",
        "THESIS_GATE",
        "RISK_GATE",
        "BEHAVIOR_GATE",
        "EXECUTION_GATE",
    ]
    assert replay["order_creation_allowed"] is False
    assert replay["execution_available"] is False
    assert replay["items"][0]["replayed_status"] == "missing"


def create_playbook_with_rule(client: TestClient, *, rule_type: str, conditions: dict, action: str = "block") -> str:
    playbook_response = client.post(
        "/strategy-playbooks",
        json={
            "user_id": "user-1",
            "name": "Gate rule playbook",
            "strategy_type": "swing",
        },
    )
    assert playbook_response.status_code == 201
    playbook_id = playbook_response.json()["id"]
    rule_response = client.post(
        "/strategy-rules",
        json={
            "strategy_playbook_id": playbook_id,
            "rule_type": rule_type,
            "priority": 1,
            "description": f"Test rule {rule_type}",
            "conditions_json": conditions,
            "actions_json": {"action": action},
            "is_active": True,
        },
    )
    assert rule_response.status_code == 201
    return playbook_id


def create_thesis_with_playbook(client: TestClient, asset_id: str, account_id: str, playbook_id: str) -> dict:
    response = client.post(
        "/investment-theses",
        json={
            "user_id": "user-1",
            "asset_id": asset_id,
            "account_id": account_id,
            "strategy_playbook_id": playbook_id,
            "entry_reason": "Playbook-linked thesis for rule gating.",
            "key_drivers_json": {"drivers": ["revenue_growth"]},
            "invalidation_conditions_json": {"invalidate_if": ["growth_breaks"]},
            "expected_horizon": "swing",
            "target_condition": "Review at next earnings.",
            "max_loss_tolerance_pct": 0.08,
            "position_plan_json": {"max_weight": 0.1},
            "confidence": 0.7,
            "source": "manual",
            "status": "active",
        },
    )
    assert response.status_code == 201
    return response.json()


def setup_rule_gated_order(client: TestClient, *, rule_type: str, conditions: dict, action: str = "block", notional: float = 5_000) -> tuple[dict, str]:
    asset, account, _base_intent, snapshot_id = setup_gate_ready_order(client, notional=notional)
    playbook_id = create_playbook_with_rule(client, rule_type=rule_type, conditions=conditions, action=action)
    thesis = create_thesis_with_playbook(client, asset["id"], account["id"], playbook_id)
    intent = create_intent(client, asset["id"], account["id"], thesis["id"], notional=notional)
    return intent, snapshot_id


def test_strategy_rule_blocks_order_through_risk_gate(client: TestClient) -> None:
    intent, snapshot_id = setup_rule_gated_order(
        client, rule_type="max_order_notional", conditions={"max_notional": 1_000}, notional=5_000
    )

    response = client.post("/decision-gates/evaluate", json=passing_gate_payload(intent["id"], snapshot_id))
    assert response.status_code == 201
    risk_gate = gate_by_type(response.json()["gates"], "RISK_GATE")
    assert risk_gate["status"] == "BLOCKED"
    assert any(reason.startswith("strategy_rule:max_order_notional:") for reason in risk_gate["blocking_reasons_json"])


def test_strategy_rule_warn_action_warns_without_blocking(client: TestClient) -> None:
    intent, snapshot_id = setup_rule_gated_order(
        client, rule_type="allowed_sides", conditions={"sides": ["sell"]}, action="warn", notional=5_000
    )

    response = client.post("/decision-gates/evaluate", json=passing_gate_payload(intent["id"], snapshot_id))
    assert response.status_code == 201
    risk_gate = gate_by_type(response.json()["gates"], "RISK_GATE")
    assert risk_gate["status"] == "WARNING"
    assert any(reason.startswith("strategy_rule:allowed_sides:") for reason in risk_gate["warnings_json"])


def test_strategy_rules_pass_when_conditions_met(client: TestClient) -> None:
    intent, snapshot_id = setup_rule_gated_order(
        client, rule_type="max_order_notional", conditions={"max_notional": 1_000}, notional=500
    )

    response = client.post("/decision-gates/evaluate", json=passing_gate_payload(intent["id"], snapshot_id))
    assert response.status_code == 201
    risk_gate = gate_by_type(response.json()["gates"], "RISK_GATE")
    assert risk_gate["status"] == "PASSED"


def test_research_gate_blocks_snapshot_catalog_marked_not_usable(client: TestClient) -> None:
    from app.db.session import get_db
    from app.main import app as fastapi_app
    from app.models import DataCatalogEntry

    asset, account, intent, snapshot_id = setup_gate_ready_order(client)

    db_generator = fastapi_app.dependency_overrides[get_db]()
    db = next(db_generator)
    try:
        db.add(
            DataCatalogEntry(
                dataset_type="quotes",
                source="test_fixture",
                data_snapshot_id=snapshot_id,
                quality_status="REVIEW_ONLY",
                usable_for_trading=False,
            )
        )
        db.commit()
    finally:
        db_generator.close()

    response = client.post("/decision-gates/evaluate", json=passing_gate_payload(intent["id"], snapshot_id))
    assert response.status_code == 201
    research_gate = gate_by_type(response.json()["gates"], "RESEARCH_GATE")
    assert research_gate["status"] == "BLOCKED"
    assert "data_catalog_not_usable_for_trading" in research_gate["blocking_reasons_json"]
