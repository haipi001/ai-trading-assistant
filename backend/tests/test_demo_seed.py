from fastapi.testclient import TestClient


def test_demo_seed_creates_happy_path_and_blocker_samples(client: TestClient) -> None:
    response = client.post("/demo/seed")

    assert response.status_code == 201
    payload = response.json()["status"]
    assert payload["seeded"] is True
    assert payload["automation_level"] == "A3_ORDER_DRAFT"
    assert payload["counts"]["holdings"] >= 3
    assert payload["counts"]["theses"] >= 1
    assert payload["counts"]["drafts"] >= 3
    assert payload["counts"]["blocked_gate_intents"] >= 1
    assert payload["counts"]["rejected_drafts"] >= 1
    assert payload["counts"]["low_quality_reports"] >= 1
    assert payload["global_risk_status"] == "healthy"
    assert payload["current_workflow_stage"] == "draft_waiting_approval"

    step_by_key = {step["key"]: step for step in payload["steps"]}
    assert step_by_key["import_data"]["status"] == "complete"
    assert step_by_key["holdings"]["status"] == "complete"
    assert step_by_key["gates"]["status"] == "complete"
    assert step_by_key["gates"]["action_label"] == "Inspect gate chain"
    assert step_by_key["gates"]["blockers"]
    assert step_by_key["approve"]["status"] == "ready"
    assert step_by_key["approve"]["action_label"] == "Approve draft"
    assert step_by_key["paper_execute"]["status"] == "pending"
    assert "approval_required" in step_by_key["paper_execute"]["blockers"]

    drafts = client.get("/orders/drafts").json()
    assert any(draft["approval_status"] == "pending" for draft in drafts)
    assert any(draft["approval_status"] == "rejected" for draft in drafts)
    assert any(draft["execution_status"] == "paper_filled" for draft in drafts)

    reviews = client.get("/post-trade-reviews").json()
    assert any(review["status"] == "completed" for review in reviews)

    monthly_reviews = client.get("/reviews/monthly?user_id=demo-user").json()
    assert len(monthly_reviews) == 1

    playbooks_response = client.get("/strategy-playbooks")
    assert playbooks_response.status_code == 200
    assert any(playbook["automation_level"] == "A3_ORDER_DRAFT" for playbook in playbooks_response.json())

    policies_response = client.get("/automation-policies")
    assert policies_response.status_code == 200
    assert any(policy["automation_level"] == "A3_ORDER_DRAFT" for policy in policies_response.json())

    budgets_response = client.get("/risk-budgets?limit=100")
    assert budgets_response.status_code == 200
    demo_asset_classes = {item["asset_class"] for item in budgets_response.json() if item["user_id"] == "demo-user"}
    assert {"stock", "etf"} <= demo_asset_classes


def test_demo_status_is_empty_before_seed(client: TestClient) -> None:
    response = client.get("/demo/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["seeded"] is False
    assert payload["current_workflow_stage"] == "data_import_pending"
