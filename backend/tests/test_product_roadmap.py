def test_product_roadmap_summary_exposes_nine_safe_phases(client):
    response = client.get("/product-roadmap/summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["phases_total"] == 9
    assert payload["capability_kind"] == "product_development_roadmap"
    assert payload["production_capability"] is False
    assert payload["execution_available"] is False
    assert payload["current_phase"]["key"] == "founder_daily_use_alpha"
    assert payload["next_phase"]["key"] == "real_readonly_data_proof"
    assert payload["phases"][-1]["key"] == "controlled_pilot"
    assert all(phase["production_capability"] is False for phase in payload["phases"])
    assert all(phase["execution_available"] is False for phase in payload["phases"])


def test_product_roadmap_phase_lookup_and_missing_phase(client):
    response = client.get("/product-roadmap/phases/2")
    assert response.status_code == 200
    payload = response.json()
    assert payload["title"] == "Real Read-Only Data Proof"
    assert "authenticated read-only adapter" in payload["scope"]
    assert payload["real_broker_call_allowed"] is False

    missing_response = client.get("/product-roadmap/phases/99")
    assert missing_response.status_code == 404
