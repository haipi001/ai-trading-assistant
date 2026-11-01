from fastapi.testclient import TestClient
import pytest

from app.services.theses import ThesisCaptureService
from test_risk_approval import pass_decision_gates
from test_risk_approval import risk_payload


TRUSTED_THESIS_SNAPSHOT_ID = "thesis-trusted-snapshot"


@pytest.fixture(autouse=True)
def trusted_thesis_snapshot(trusted_snapshot_factory):
    trusted_snapshot_factory(TRUSTED_THESIS_SNAPSHOT_ID)


def create_asset(client: TestClient, symbol: str = "NVDA") -> dict:
    response = client.post(
        "/assets",
        json={
            "symbol": symbol,
            "name": "NVIDIA Corporation" if symbol == "NVDA" else symbol,
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


def capture_thesis(client: TestClient, asset_id: str) -> dict:
    response = client.post(
        "/theses/capture",
        json={
            "user_id": "user-1",
            "asset_id": asset_id,
            "data_snapshot_id": TRUSTED_THESIS_SNAPSHOT_ID,
            "user_rationale": "I want to own NVDA while datacenter demand and margin strength remain intact.",
            "intended_action": "buy",
            "current_position": {"quantity": 0, "market_value": 0},
            "market_context": {
                "key_drivers": ["datacenter_demand", "margin_strength"],
                "invalidation_conditions": ["datacenter_growth_slows", "gross_margin_breaks_down"],
                "expected_horizon": "swing",
                "target_condition": "Review after next earnings report.",
                "max_loss_tolerance_pct": 0.08,
                "confidence": 0.74,
            },
        },
    )
    assert response.status_code == 201
    return response.json()


def test_capture_thesis_from_mock_user_input(client: TestClient) -> None:
    asset = create_asset(client)

    thesis = capture_thesis(client, asset["id"])

    assert thesis["asset_id"] == asset["id"]
    assert thesis["entry_reason"].startswith("I want to own NVDA")
    assert thesis["key_drivers_json"]["items"] == ["datacenter_demand", "margin_strength"]
    assert thesis["source"] == "mock_ai_thesis_capture"
    assert thesis["data_snapshot_id"] == TRUSTED_THESIS_SNAPSHOT_ID

    drafts_response = client.get("/orders/drafts")
    assert drafts_response.status_code == 200
    assert drafts_response.json() == []


def test_capture_thesis_blocks_untrusted_snapshot_before_ai_generation(client: TestClient) -> None:
    asset = create_asset(client)
    response = client.post(
        "/theses/capture",
        json={
            "user_id": "user-1",
            "asset_id": asset["id"],
            "data_snapshot_id": "unknown-thesis-snapshot",
            "user_rationale": "Only capture this thesis when its market facts are trusted.",
            "intended_action": "review",
            "current_position": {},
            "market_context": {},
        },
    )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "data_trust_gate_blocked"
    assert detail["decision_scope"] == "thesis_capture"
    assert client.get("/investment-theses").json() == []


def test_capture_thesis_accepts_asset_symbol_for_holding_workflow(client: TestClient) -> None:
    asset = create_asset(client, symbol="SELFTHESIS")

    thesis = capture_thesis(client, "SELFTHESIS")

    assert thesis["asset_id"] == asset["id"]


def test_monitor_thesis_with_supporting_facts(client: TestClient) -> None:
    asset = create_asset(client)
    thesis = capture_thesis(client, asset["id"])

    response = client.post(
        f"/theses/{thesis['id']}/monitor",
        json={
            "data_snapshot_id": TRUSTED_THESIS_SNAPSHOT_ID,
            "new_facts": {"supports_thesis": True, "datacenter_growth": "accelerating"},
            "earnings_data": {"supports_key_driver": True},
            "technical_signals": [{"signal_type": "ma_cross", "direction": "bullish"}],
        },
    )

    assert response.status_code == 201
    checkpoint = response.json()
    assert checkpoint["checkpoint_type"] == "SUPPORTS_THESIS"
    assert checkpoint["supports_thesis"] is True
    assert checkpoint["invalidates_thesis"] is False
    assert checkpoint["data_snapshot_id"] == TRUSTED_THESIS_SNAPSHOT_ID


def test_monitor_thesis_blocks_untrusted_snapshot_without_checkpoint(client: TestClient) -> None:
    asset = create_asset(client)
    thesis = capture_thesis(client, asset["id"])

    response = client.post(
        f"/theses/{thesis['id']}/monitor",
        json={"data_snapshot_id": "unknown-monitor-snapshot", "new_facts": {"supports_thesis": True}},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["decision_scope"] == "thesis_monitor"
    assert client.get(f"/theses/{thesis['id']}/checkpoints").json() == []


def test_monitor_thesis_with_invalidating_facts(client: TestClient) -> None:
    asset = create_asset(client)
    thesis = capture_thesis(client, asset["id"])

    response = client.post(
        f"/theses/{thesis['id']}/monitor",
        json={
            "data_snapshot_id": TRUSTED_THESIS_SNAPSHOT_ID,
            "new_facts": {"invalidation_triggered": True},
            "price_movement": {"drawdown_pct": 0.09},
        },
    )

    assert response.status_code == 201
    checkpoint = response.json()
    assert checkpoint["checkpoint_type"] == "INVALIDATES_THESIS"
    assert checkpoint["invalidates_thesis"] is True

    list_response = client.get(f"/theses/{thesis['id']}/checkpoints")
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1


def test_monitor_thesis_with_insufficient_data(client: TestClient) -> None:
    asset = create_asset(client)
    thesis = capture_thesis(client, asset["id"])

    response = client.post(f"/theses/{thesis['id']}/monitor", json={"data_snapshot_id": TRUSTED_THESIS_SNAPSHOT_ID})

    assert response.status_code == 201
    checkpoint = response.json()
    assert checkpoint["checkpoint_type"] == "DATA_INSUFFICIENT"
    assert checkpoint["supports_thesis"] is False
    assert checkpoint["weakens_thesis"] is False
    assert checkpoint["invalidates_thesis"] is False


def test_create_thesis_violation_message(client: TestClient) -> None:
    asset = create_asset(client)
    thesis = capture_thesis(client, asset["id"])

    response = client.post(
        f"/theses/{thesis['id']}/violation-message",
        json={
            "user_id": "user-1",
            "current_action": "Sell because of a small intraday dip despite intact datacenter thesis.",
            "intervention_level": "HARD_CONFIRM",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["intervention_level"] == "HARD_CONFIRM"
    assert body["violation"]["thesis_id"] == thesis["id"]
    assert body["violation"]["violation_type"] == "THESIS_CONFLICT"

    violations_response = client.get("/thesis-violations")
    assert violations_response.status_code == 200
    assert len(violations_response.json()) == 1


def test_thesis_events_and_context_are_exposed(client: TestClient) -> None:
    asset = create_asset(client)
    thesis = capture_thesis(client, asset["id"])
    monitor_response = client.post(
        f"/theses/{thesis['id']}/monitor",
        json={"data_snapshot_id": TRUSTED_THESIS_SNAPSHOT_ID, "new_facts": {"supports_thesis": True, "new_customer_signal": "positive"}},
    )
    assert monitor_response.status_code == 201

    event_response = client.post(
        "/theses/thesis-events",
        json={
            "thesis_id": thesis["id"],
            "event_type": "EVIDENCE_NOTE",
            "title": "Channel check supports thesis",
            "description": "Demand remains firm.",
            "impact_json": {"supports": True},
        },
    )
    assert event_response.status_code == 201

    list_response = client.get(f"/theses/thesis-events?thesis_id={thesis['id']}")
    assert list_response.status_code == 200
    assert any(event["event_type"] == "EVIDENCE_NOTE" for event in list_response.json())

    all_events_response = client.get("/theses/thesis-events")
    assert all_events_response.status_code == 200
    assert any(event["thesis_id"] == thesis["id"] for event in all_events_response.json())

    context_response = client.get(f"/theses/{thesis['id']}/context")
    assert context_response.status_code == 200
    context = context_response.json()
    assert context["thesis_id"] == thesis["id"]
    assert context["health_status"] in {"healthy", "needs_review"}
    assert context["recent_events"]
    assert "summary" in context


def test_thesis_context_includes_playbook_proposals(client: TestClient) -> None:
    asset = create_asset(client, "AAPL")
    account_response = client.post(
        "/accounts",
        json={
            "name": "Thesis Context Account",
            "account_type": "brokerage",
            "broker": "mock",
            "base_currency": "USD",
            "mode": "paper",
        },
    )
    assert account_response.status_code == 201
    account = account_response.json()

    playbook_response = client.post(
        "/strategy-playbooks",
        json={
            "user_id": "default-user",
            "name": "Momentum Playbook",
            "strategy_type": "swing",
            "applicable_markets": ["US"],
            "applicable_assets": ["stock"],
            "entry_conditions_json": {"items": ["trend"]},
            "exit_conditions_json": {"items": ["breakdown"]},
            "risk_rules_json": {},
            "automation_level": "A1_RESEARCH",
            "requires_human_approval": True,
            "is_active": True,
        },
    )
    assert playbook_response.status_code == 201
    playbook = playbook_response.json()

    thesis_response = client.post(
        "/investment-theses",
        json={
            "user_id": "default-user",
            "asset_id": asset["id"],
            "data_snapshot_id": TRUSTED_THESIS_SNAPSHOT_ID,
            "account_id": account["id"],
            "strategy_playbook_id": playbook["id"],
            "entry_reason": "Trend and earnings revisions remain supportive.",
            "key_drivers_json": {"drivers": ["trend", "revisions"]},
            "invalidation_conditions_json": {"invalidate_if": ["trend_breaks"]},
            "expected_horizon": "swing",
            "target_condition": "Hold while setup remains intact.",
            "max_loss_tolerance_pct": 0.08,
            "position_plan_json": {"max_weight": 0.1},
            "confidence": 0.7,
            "source": "manual",
            "status": "active",
        },
    )
    assert thesis_response.status_code == 201
    thesis = thesis_response.json()

    intent_response = client.post(
        "/orders/intents",
        json={
            "source_type": "manual",
            "asset_id": asset["id"],
            "account_id": account["id"],
            "investment_thesis_id": thesis["id"],
            "strategy_playbook_id": playbook["id"],
            "side": "buy",
            "order_type": "market",
            "notional": 1000,
            "rationale": "Context test intent",
        },
    )
    assert intent_response.status_code == 201
    intent = intent_response.json()

    pass_decision_gates(client, intent["id"], account["id"])
    draft_response = client.post(f"/orders/intents/{intent['id']}/draft", json=risk_payload(intent["id"]))
    assert draft_response.status_code == 201
    draft = draft_response.json()
    approve_response = client.post(
        f"/orders/drafts/{draft['id']}/approve",
        json={"approver_id": "tester", "decision_reason": "Approve for context linkage test."},
    )
    assert approve_response.status_code == 201

    execution_response = client.post(
        f"/paper-executions/drafts/{draft['id']}/execute",
        json={"approver_id": "tester", "fill_price": 200},
    )
    assert execution_response.status_code == 201
    review = execution_response.json()["post_trade_review"]

    proposal_response = client.post(f"/playbook-update-proposals/from-post-trade-review/{review['id']}")
    assert proposal_response.status_code == 201

    context_response = client.get(f"/theses/{thesis['id']}/context")
    assert context_response.status_code == 200
    context = context_response.json()
    assert len(context["linked_playbook_proposals"]) == 1
    assert context["linked_playbook_proposals"][0]["strategy_playbook_id"] == playbook["id"]


def test_reject_unsupported_ai_output(client: TestClient, monkeypatch) -> None:
    asset = create_asset(client)

    def invalid_capture_output(self, provider_name, input_facts, prompt_template):
        return {"entry_reason": "", "key_drivers": []}

    monkeypatch.setattr(ThesisCaptureService, "_generate_capture_output", invalid_capture_output)

    response = client.post(
        "/theses/capture",
        json={
            "user_id": "user-1",
            "asset_id": asset["id"],
            "data_snapshot_id": TRUSTED_THESIS_SNAPSHOT_ID,
            "user_rationale": "Buy only if the thesis is structurally sound.",
            "intended_action": "buy",
            "current_position": {},
            "market_context": {},
        },
    )

    assert response.status_code == 422

    theses_response = client.get("/investment-theses")
    assert theses_response.status_code == 200
    assert theses_response.json() == []

    audit_response = client.get("/audit-logs")
    assert audit_response.status_code == 200
    assert any(log["action"] == "investment_thesis.invalid_output_rejected" for log in audit_response.json())
