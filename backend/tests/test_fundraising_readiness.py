from fastapi.testclient import TestClient


def test_fundraising_readiness_summary_returns_ordered_safe_queue(client: TestClient) -> None:
    response = client.get("/fundraising/readiness/summary")

    assert response.status_code == 200
    packet = response.json()
    assert packet["status"] == "developed_safe_slice"
    assert packet["target"] == "RMB_10M_plus_seed_style"
    assert packet["developed_items"] == 10
    assert packet["execution_available"] is False
    assert packet["real_broker_call_allowed"] is False
    assert packet["autonomous_trading_added"] is False
    assert [item["item_no"] for item in packet["items"]] == list(range(1, 11))
    assert all(item["development_status"] == "developed_safe_slice" for item in packet["items"])
    assert all(item["execution_available"] is False for item in packet["items"])


def test_fundraising_readiness_items_match_requested_ten_gaps(client: TestClient) -> None:
    response = client.get("/fundraising/readiness/items")

    assert response.status_code == 200
    items = response.json()
    assert [item["key"] for item in items] == [
        "icp_killer_workflow",
        "real_authenticated_readonly_data",
        "production_auth_rbac_secrets_ops",
        "external_compliance_boundary",
        "ai_provider_eval_citation_antihallucination",
        "beta_users_retention_paid_intent_loi",
        "seven_minute_investor_demo_path",
        "business_model_pricing_gtm",
        "deck_onepager_demo_video_data_room",
        "controlled_live_sandbox_proof",
    ]
    assert items[1]["real_broker_call_allowed"] is False
    assert items[9]["live_execution_enabled"] is False
    assert "real_sandbox_adapter_missing" in items[9]["blockers"]


def test_fundraising_readiness_single_item_and_missing_item(client: TestClient) -> None:
    response = client.get("/fundraising/readiness/items/7")

    assert response.status_code == 200
    packet = response.json()
    assert packet["key"] == "seven_minute_investor_demo_path"
    assert packet["item_no"] == 7
    assert packet["wallet_signing_available"] is False

    missing = client.get("/fundraising/readiness/items/99")
    assert missing.status_code == 404
