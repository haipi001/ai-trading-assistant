from fastapi.testclient import TestClient

from test_decision_narratives import create_thesis
from test_paper_execution import create_strategy_playbook
from test_risk_approval import create_account
from test_risk_approval import create_asset
from test_risk_approval import create_intent
from test_risk_approval import pass_decision_gates
from test_risk_approval import risk_payload


def checks_by_stage(item: dict) -> dict[int, dict]:
    return {check["stage_number"]: check for check in item["checks"]}


def find_stage_item(queue: dict, order_intent_id: str) -> dict:
    return next(item for item in queue["items"] if item["order_intent_id"] == order_intent_id)


def test_stage_5_11_readiness_blocks_unprepared_order_intent(client: TestClient) -> None:
    asset = create_asset(client)
    account = create_account(client)
    intent = create_intent(client, asset["id"], account["id"], notional=1_000)

    response = client.get("/workflows/stage-5-11-readiness?user_id=default-user&limit=10")

    assert response.status_code == 200
    queue = response.json()
    item = find_stage_item(queue, intent["id"])
    stage_checks = checks_by_stage(item)

    assert queue["execution_available"] is False
    assert item["execution_available"] is False
    assert item["subject_type"] == "order_intent"
    assert item["readiness"] == "blocked"
    assert set(stage_checks) == {5, 6, 7, 8, 9, 10, 11}
    assert stage_checks[5]["status"] == "block"
    assert stage_checks[7]["status"] == "block"
    assert stage_checks[8]["status"] == "block"
    assert stage_checks[9]["status"] == "block"
    assert "Missing StrategyPlaybook link before order workflow." in item["blockers"]
    assert "Missing latest RiskCheck." in item["blockers"]


def test_stage_5_11_readiness_surfaces_ready_order_draft_without_execution(client: TestClient) -> None:
    asset = create_asset(client)
    account = create_account(client)
    playbook = create_strategy_playbook(client, user_id="human-user")
    thesis = create_thesis(client, asset["id"], playbook["id"])
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
            "notional": 1_000,
            "rationale": "Stage 5-11 readiness test intent.",
            "user_rationale": "This order follows the linked thesis and current playbook.",
        },
    )
    assert intent_response.status_code == 201
    intent = intent_response.json()

    checkpoint_response = client.post(
        "/thesis-checkpoints",
        json={
            "thesis_id": thesis["id"],
            "checkpoint_type": "manual_freshness",
            "observed_facts_json": {"trend": "confirmed", "risk": "within plan"},
            "supports_thesis": True,
            "weakens_thesis": False,
            "invalidates_thesis": False,
            "confidence": 0.82,
        },
    )
    assert checkpoint_response.status_code == 201
    pass_decision_gates(client, intent["id"], account["id"])
    draft_response = client.post(f"/orders/intents/{intent['id']}/draft", json=risk_payload(intent["id"]))
    assert draft_response.status_code == 201
    draft = draft_response.json()
    behavior_response = client.post(
        "/behavior/evaluate-order",
        json={"order_intent_id": intent["id"], "user_id": "human-user"},
    )
    assert behavior_response.status_code == 201
    workflow_response = client.post(
        "/workflow-states",
        json={
            "workflow_type": "OrderDraft",
            "entity_id": draft["id"],
            "current_state": "USER_APPROVAL_REQUIRED",
            "previous_state": "ORDER_DRAFT_CREATED",
            "transition_reason": "Stage 5-11 readiness test.",
            "metadata_json": {"source": "test_stage_5_11_readiness"},
        },
    )
    assert workflow_response.status_code == 201

    response = client.get("/workflows/stage-5-11-readiness?user_id=human-user&limit=10")

    assert response.status_code == 200
    queue = response.json()
    item = find_stage_item(queue, intent["id"])

    assert queue["ready_count"] >= 1
    assert queue["execution_available"] is False
    assert item["subject_type"] == "order_draft"
    assert item["order_draft_id"] == draft["id"]
    assert item["readiness"] == "ready_for_human_review"
    assert item["current_workflow_state"] == "USER_APPROVAL_REQUIRED"
    assert item["execution_available"] is False
    assert [check["status"] for check in item["checks"]] == ["ok", "ok", "ok", "ok", "ok", "ok", "ok"]
