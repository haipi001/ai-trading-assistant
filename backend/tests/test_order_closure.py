from fastapi.testclient import TestClient

from test_paper_execution import create_approved_draft


def find_closure_item(report: dict, order_draft_id: str) -> dict:
    return next(item for item in report["items"] if item["order_draft_id"] == order_draft_id)


def checks_by_key(item: dict) -> dict[str, dict]:
    return {check["stage_key"]: check for check in item["checks"]}


def test_order_closure_report_tracks_approval_execution_and_review(client: TestClient) -> None:
    draft = create_approved_draft(client)

    approved_report_response = client.get("/workflows/order-closure-report?user_id=human-user&limit=10")

    assert approved_report_response.status_code == 200
    approved_report = approved_report_response.json()
    approved_item = find_closure_item(approved_report, draft["id"])
    approved_checks = checks_by_key(approved_item)
    assert approved_report["execution_available"] is False
    assert approved_item["execution_available"] is False
    assert approved_item["status"] == "review_required"
    assert approved_item["execution_id"] is None
    assert approved_checks["approval"]["status"] == "ok"
    assert approved_checks["paper_execution"]["status"] == "warn"
    assert approved_checks["post_trade_review"]["status"] == "warn"

    execute_response = client.post(
        f"/paper-executions/drafts/{draft['id']}/execute",
        json={"approver_id": "human-user", "decision_reason": "Closure report test.", "fill_price": 225.12, "fee_bps": 0},
    )
    assert execute_response.status_code == 201
    execution = execute_response.json()["execution"]
    review = execute_response.json()["post_trade_review"]

    pending_review_response = client.get("/workflows/order-closure-report?user_id=human-user&limit=10")

    assert pending_review_response.status_code == 200
    pending_item = find_closure_item(pending_review_response.json(), draft["id"])
    pending_checks = checks_by_key(pending_item)
    assert pending_item["status"] == "review_required"
    assert pending_item["execution_id"] == execution["id"]
    assert pending_item["post_trade_review_id"] == review["id"]
    assert pending_checks["paper_execution"]["status"] == "ok"
    assert pending_checks["post_trade_review"]["status"] == "warn"

    update_response = client.patch(
        f"/post-trade-reviews/{review['id']}",
        json={"status": "completed", "review_json": {"lesson": "Closed-loop review completed."}},
    )
    assert update_response.status_code == 200

    closed_response = client.get("/workflows/order-closure-report?user_id=human-user&limit=10")

    assert closed_response.status_code == 200
    closed_report = closed_response.json()
    closed_item = find_closure_item(closed_report, draft["id"])
    assert closed_item["status"] == "closed"
    assert closed_report["closed_count"] == 1
    assert all(check["status"] == "ok" for check in closed_item["checks"])


def test_review_quality_report_scores_thesis_gate_order_review_loop(client: TestClient) -> None:
    draft = create_approved_draft(client)

    initial_response = client.get("/workflows/review-quality-report?user_id=human-user&limit=10")

    assert initial_response.status_code == 200
    initial = initial_response.json()
    assert initial["status"] == "review_required"
    assert initial["execution_available"] is False
    assert initial["items"][0]["order_draft_id"] == draft["id"]
    assert initial["items"][0]["warn_count"] >= 1
    assert any("paper_execution" in gap or "post_trade_review" in gap for gap in initial["explanation_gaps"])

    execute_response = client.post(
        f"/paper-executions/drafts/{draft['id']}/execute",
        json={"approver_id": "human-user", "decision_reason": "Review quality test.", "fill_price": 225.12, "fee_bps": 0},
    )
    assert execute_response.status_code == 201
    review = execute_response.json()["post_trade_review"]
    update_response = client.patch(
        f"/post-trade-reviews/{review['id']}",
        json={"status": "completed", "review_json": {"lesson": "Closed-loop quality report completed."}},
    )
    assert update_response.status_code == 200

    closed_response = client.get("/workflows/review-quality-report?user_id=human-user&limit=10")

    assert closed_response.status_code == 200
    closed = closed_response.json()
    assert closed["status"] == "closed_loop_ready"
    assert closed["average_quality_score"] == 1
    assert closed["hard_gaps"] == []
    assert closed["explanation_gaps"] == []
