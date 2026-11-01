from fastapi.testclient import TestClient

from test_paper_execution import create_strategy_playbook
from test_risk_approval import create_account
from test_risk_approval import create_asset
from test_risk_approval import pass_decision_gates
from test_risk_approval import risk_payload


def create_thesis(client: TestClient, asset_id: str, strategy_playbook_id: str) -> dict:
    response = client.post(
        "/investment-theses",
        json={
            "user_id": "human-user",
            "asset_id": asset_id,
            "strategy_playbook_id": strategy_playbook_id,
            "entry_reason": "Buy only when momentum confirms the existing thesis.",
            "key_drivers_json": {"driver": "earnings growth", "setup": "momentum confirmation"},
            "invalidation_conditions_json": {"invalid": "momentum fails or drawdown exceeds limit"},
            "expected_horizon": "swing",
            "target_condition": "trend continuation after confirmation",
            "max_loss_tolerance_pct": 0.08,
            "position_plan_json": {"sizing": "starter only"},
            "confidence": 0.72,
            "source": "manual",
            "status": "active",
        },
    )
    assert response.status_code == 201
    return response.json()


def create_signal_linked_draft(client: TestClient) -> tuple[dict, dict, dict, dict]:
    asset = create_asset(client)
    account = create_account(client)
    playbook = create_strategy_playbook(client)
    thesis = create_thesis(client, asset["id"], playbook["id"])

    signal_response = client.post(
        "/signals/generate",
        json={
            "asset_id": asset["id"],
            "signal_types": ["ma_cross"],
            "candles": [{"close": close} for close in [10, 10, 10, 8, 8, 20]],
            "horizon": "swing",
        },
    )
    assert signal_response.status_code == 201
    signal = signal_response.json()[0]

    intent_response = client.post(
        f"/signals/{signal['id']}/create-order-intent",
        json={
            "account_id": account["id"],
            "automation_level": "A3_ORDER_DRAFT",
            "signal_order_intents_enabled": True,
            "notional": 225.12,
        },
    )
    assert intent_response.status_code == 201
    intent = intent_response.json()
    assert intent["investment_thesis_id"] == thesis["id"]
    assert intent["strategy_playbook_id"] == playbook["id"]

    pass_decision_gates(client, intent["id"], account["id"])
    draft_response = client.post(f"/orders/intents/{intent['id']}/draft", json=risk_payload(intent["id"]))
    assert draft_response.status_code == 201
    draft = draft_response.json()
    approval_response = client.post(
        f"/orders/drafts/{draft['id']}/approve",
        json={"approver_id": "human-user", "decision_reason": "Narrative test paper approval."},
    )
    assert approval_response.status_code == 201
    return draft, signal, thesis, playbook


def test_order_draft_decision_narrative_links_signal_thesis_review_and_playbook(client: TestClient) -> None:
    draft, signal, thesis, playbook = create_signal_linked_draft(client)
    execute_response = client.post(
        f"/paper-executions/drafts/{draft['id']}/execute",
        json={"approver_id": "human-user", "fill_price": 225.12, "fee_bps": 0},
    )
    assert execute_response.status_code == 201
    review = execute_response.json()["post_trade_review"]
    update_response = client.patch(
        f"/post-trade-reviews/{review['id']}",
        json={"status": "completed", "review_json": {"lesson": "Wait for thesis confirmation before adding size."}},
    )
    assert update_response.status_code == 200
    proposal_response = client.post(f"/playbook-update-proposals/from-post-trade-review/{review['id']}")
    assert proposal_response.status_code == 201
    proposal = proposal_response.json()

    response = client.get(f"/orders/drafts/{draft['id']}/decision-narrative")

    assert response.status_code == 200
    narrative = response.json()
    assert narrative["draft_id"] == draft["id"]
    assert narrative["signal_id"] == signal["id"]
    assert narrative["thesis_id"] == thesis["id"]
    assert narrative["thesis_link_kind"] == "explicit"
    assert narrative["strategy_playbook_id"] == playbook["id"]
    assert narrative["current_stage"] == "post_trade_reviewed"

    sections = {section["key"]: section for section in narrative["sections"]}
    assert sections["source_signal"]["evidence"]["signal_id"] == signal["id"]
    assert sections["source_signal"]["status"] == "needs_review"
    assert sections["thesis_alignment"]["status"] == "ok"
    assert sections["gate_summary"]["status"] == "ok"
    assert sections["post_trade_learning"]["summary"] == "Wait for thesis confirmation before adding size."
    assert sections["playbook_next"]["evidence"]["proposal_id"] == proposal["id"]
    assert sections["playbook_next"]["evidence"]["auto_applied"] is False

    assert narrative["safety_flags"]["live_execution_available"] is False
    assert narrative["safety_flags"]["broker_execution_called"] is False
    assert narrative["safety_flags"]["wallet_write_called"] is False
    assert narrative["safety_flags"]["all_latest_gates_passed"] is True
    assert any("pending playbook proposal" in action for action in narrative["next_actions"])
    assert {event["label"] for event in narrative["timeline"]} >= {
        "OrderIntent",
        "OrderDraft",
        "RiskCheck",
        "Approval",
        "PaperExecution",
        "PostTradeReview",
        "PlaybookProposal",
    }


def test_order_draft_decision_narrative_404_for_missing_draft(client: TestClient) -> None:
    response = client.get("/orders/drafts/missing-draft/decision-narrative")

    assert response.status_code == 404
    assert response.json()["detail"] == "order draft not found"
