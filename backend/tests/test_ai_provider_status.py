from fastapi.testclient import TestClient


def test_ai_provider_status_is_safe_by_default(client: TestClient) -> None:
    response = client.get("/ai/provider-status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["default_provider"] == "mock"
    assert payload["external_calls_enabled"] is False
    assert payload["openai_configured"] is False
    assert payload["safe_mode"] == "mock_only"
    assert any("cannot execute orders" in limitation for limitation in payload["limitations"])
