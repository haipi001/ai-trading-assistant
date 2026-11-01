from fastapi.testclient import TestClient


def test_research_report_links_thesis_plan_and_gate_evidence(client: TestClient) -> None:
    assert client.post("/demo/seed").status_code == 201
    reports_response = client.get("/reports?limit=20")
    assert reports_response.status_code == 200
    report = reports_response.json()[0]
    theses = client.get("/investment-theses?limit=100").json()
    thesis = next(item for item in theses if item["asset_id"] == report["asset_id"])
    headers = {"X-AI-Trading-User": thesis["user_id"]}
    accounts = client.get("/accounts").json()
    account = next((item for item in accounts if item["mode"] == "paper"), accounts[0])

    review = client.post(
        f"/reports/{report['id']}/review-thesis",
        json={
            "thesis_id": thesis["id"],
            "decision": "supports",
            "human_summary": "The cited facts support the active thesis, subject to valuation risk.",
            "confidence": 0.8,
        },
        headers=headers,
    )
    assert review.status_code == 201, review.text
    review_packet = review.json()
    assert review_packet["checkpoint"]["observed_facts_json"]["research_report_id"] == report["id"]
    assert review_packet["trace"]["data_snapshot_id"] == report["data_snapshot_id"]
    assert review_packet["execution_available"] is False

    plan = client.post(
        f"/reports/{report['id']}/create-plan-and-evaluate",
        json={
            "thesis_id": thesis["id"],
            "account_id": account["id"],
            "side": "buy",
            "order_type": "market",
            "quantity": 1,
            "user_rationale": "Human-reviewed research supports a small paper-only plan.",
            "risk_context": {"data_quality_status": "acceptable", "liquidity_passed": True},
        },
        headers=headers,
    )
    assert plan.status_code == 201, plan.text
    packet = plan.json()
    assert packet["order_intent"]["source_type"] == "research_report"
    assert packet["order_intent"]["evidence_json"]["thesis_checkpoint_id"] == review_packet["checkpoint"]["id"]
    assert {item["gate_type"] for item in packet["gates"]} == {
        "RESEARCH_GATE",
        "THESIS_GATE",
        "RISK_GATE",
        "BEHAVIOR_GATE",
        "EXECUTION_GATE",
    }
    assert all(item["evidence_json"]["order_trace"]["research_report_id"] == report["id"] for item in packet["gates"])
    assert packet["execution_available"] is False

    readiness = client.get("/complete-product/readiness/items/4", headers=headers).json()
    assert "research_to_order_traceability_incomplete" not in readiness["blockers"]
    assert readiness["progress_pct"] >= 80
    default_readiness = client.get("/complete-product/readiness/items/4").json()
    assert "research_to_order_traceability_incomplete" in default_readiness["blockers"]
