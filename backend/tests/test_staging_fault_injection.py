from app.api import ops
from app.core.config import Settings


def test_fault_injection_is_hidden_by_default(client):
    response = client.post("/ops/observability/fault-injection")
    assert response.status_code == 404


def test_fault_injection_requires_managed_staging_and_explicit_switch(client, monkeypatch):
    for settings in (
        Settings(environment="staging", deployment_target="managed-staging", staging_fault_injection_enabled=False),
        Settings(environment="production", deployment_target="managed-production", staging_fault_injection_enabled=True),
        Settings(environment="local", deployment_target="managed-staging", staging_fault_injection_enabled=True),
    ):
        monkeypatch.setattr(ops, "get_settings", lambda settings=settings: settings)
        assert client.post("/ops/observability/fault-injection").status_code == 404


def test_fault_injection_returns_only_safe_503_in_explicit_staging(client, monkeypatch):
    monkeypatch.setattr(
        ops,
        "get_settings",
        lambda: Settings(environment="staging", deployment_target="managed-staging", staging_fault_injection_enabled=True),
    )
    response = client.post("/ops/observability/fault-injection")
    assert response.status_code == 503
    assert response.json() == {
        "status": "injected_staging_failure",
        "contains_customer_data": False,
        "execution_available": False,
    }
    assert response.headers["cache-control"] == "no-store"


def test_viewer_cannot_inject_staging_failure(client, monkeypatch):
    monkeypatch.setattr(
        ops,
        "get_settings",
        lambda: Settings(environment="staging", deployment_target="managed-staging", staging_fault_injection_enabled=True),
    )
    response = client.post("/ops/observability/fault-injection", headers={"X-AI-Trading-Role": "viewer"})
    assert response.status_code == 403
