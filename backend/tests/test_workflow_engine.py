from fastapi.testclient import TestClient


VALID_PATH = [
    "DATA_COLLECTED",
    "RESEARCH_GENERATED",
    "THESIS_CREATED_OR_MATCHED",
    "SIGNAL_DETECTED",
    "ORDER_INTENT_CREATED",
    "RESEARCH_GATE_PASSED",
    "THESIS_GATE_PASSED",
    "RISK_GATE_PASSED",
    "BEHAVIOR_GATE_PASSED",
    "EXECUTION_GATE_PASSED",
    "ORDER_DRAFT_CREATED",
    "USER_APPROVAL_REQUIRED",
    "APPROVED",
    "PAPER_EXECUTED",
    "EXECUTION_CONFIRMED",
    "JOURNAL_WRITTEN",
    "REVIEW_SCHEDULED",
    "POST_TRADE_REVIEWED",
    "PLAYBOOK_UPDATED",
]


def create_workflow(client: TestClient, entity_type: str = "trade_idea", entity_id: str = "idea-1") -> dict:
    response = client.post(
        "/workflows",
        json={"entity_type": entity_type, "entity_id": entity_id, "metadata": {"source": "test"}},
    )
    assert response.status_code == 201
    workflow = response.json()
    assert workflow["current_state"] == "IDEA_CREATED"
    return workflow


def transition(client: TestClient, workflow_id: str, next_state: str, **metadata) -> dict:
    response = client.post(
        f"/workflows/{workflow_id}/transition",
        json={
            "next_state": next_state,
            "reason": f"move to {next_state}",
            "metadata": metadata,
        },
    )
    assert response.status_code == 201
    return response.json()


def advance_to(client: TestClient, workflow: dict, target_state: str, **metadata) -> dict:
    current = workflow
    for next_state in VALID_PATH:
        current = transition(client, current["id"], next_state, **metadata)
        if next_state == target_state:
            return current
    raise AssertionError(f"target state {target_state} is not in valid path")


def test_valid_transition_path(client: TestClient) -> None:
    workflow = create_workflow(client)
    current = workflow

    for next_state in VALID_PATH:
        current = transition(client, current["id"], next_state)

    assert current["current_state"] == "PLAYBOOK_UPDATED"
    timeline_response = client.get("/workflows/entity/trade_idea/idea-1")
    assert timeline_response.status_code == 200
    timeline = timeline_response.json()
    assert [item["current_state"] for item in timeline] == ["IDEA_CREATED", *VALID_PATH]


def test_invalid_skipped_gate_is_blocked(client: TestClient) -> None:
    workflow = create_workflow(client, entity_id="idea-skip-gate")
    order_intent = advance_to(client, workflow, "ORDER_INTENT_CREATED")

    response = client.post(
        f"/workflows/{order_intent['id']}/transition",
        json={
            "next_state": "ORDER_DRAFT_CREATED",
            "reason": "attempt to skip gates",
            "metadata": {},
        },
    )

    assert response.status_code == 422
    assert "before all required gates pass" in response.json()["detail"]
    timeline = client.get("/workflows/entity/trade_idea/idea-skip-gate").json()
    assert timeline[-1]["current_state"] == "BLOCKED"
    assert timeline[-1]["metadata_json"]["attempted_state"] == "ORDER_DRAFT_CREATED"


def test_blocked_workflow(client: TestClient) -> None:
    workflow = create_workflow(client, entity_id="idea-blocked")

    response = client.post(
        f"/workflows/{workflow['id']}/block",
        json={"reason": "missing data quality report", "metadata": {"data_quality": "unavailable"}},
    )

    assert response.status_code == 201
    blocked = response.json()
    assert blocked["current_state"] == "BLOCKED"
    assert blocked["metadata_json"]["blocking_reason"] == "missing data quality report"


def test_audit_log_on_transition(client: TestClient) -> None:
    workflow = create_workflow(client, entity_id="idea-audit")
    transitioned = transition(client, workflow["id"], "DATA_COLLECTED")

    audit_logs = client.get("/audit-logs").json()
    assert any(
        log["action"] == "workflow.transitioned"
        and log["entity_id"] == transitioned["id"]
        and log["payload_json"]["next_state"] == "DATA_COLLECTED"
        for log in audit_logs
    )


def test_cannot_execute_without_approval(client: TestClient) -> None:
    workflow = create_workflow(client, entity_id="idea-no-approval")
    draft = advance_to(client, workflow, "ORDER_DRAFT_CREATED")

    response = client.post(
        f"/workflows/{draft['id']}/transition",
        json={
            "next_state": "PAPER_EXECUTED",
            "reason": "attempt paper execution before approval",
            "metadata": {},
        },
    )

    assert response.status_code == 422
    assert "cannot execute before approval" in response.json()["detail"]


def test_cannot_live_execute_by_default(client: TestClient) -> None:
    workflow = create_workflow(client, entity_id="idea-live-default")
    approved = advance_to(client, workflow, "APPROVED")

    response = client.post(
        f"/workflows/{approved['id']}/transition",
        json={
            "next_state": "LIVE_EXECUTED",
            "reason": "attempt live state transition",
            "metadata": {"live_trading_enabled": False},
        },
    )

    assert response.status_code == 422
    assert "live_trading_enabled is true" in response.json()["detail"]
