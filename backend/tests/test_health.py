import pytest


@pytest.mark.parametrize('database',['ok','unavailable'])
@pytest.mark.parametrize('redis',['ok','unavailable'])
def test_health_endpoint_shape(client, monkeypatch, database, redis) -> None:
    # This contract test must not depend on a developer's real database/Redis.
    monkeypatch.setattr('app.api.health.check_database', lambda: database)
    monkeypatch.setattr('app.api.health.check_redis', lambda: redis)
    response = client.get('/health')
    assert response.status_code == 200
    assert response.json().keys() == {'status','service','database','redis'}
    assert response.json()['status'] == ('ok' if database == 'ok' else 'degraded')
    assert response.json()['service'] == 'ai-trading-os-backend'
    assert response.json()['database'] == database
    assert response.json()['redis'] == redis


def test_readiness_fails_closed_when_required_database_is_unavailable(client, monkeypatch) -> None:
    monkeypatch.setattr("app.api.health.check_database", lambda: "unavailable")
    monkeypatch.setattr("app.api.health.check_redis", lambda: "ok")

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    assert response.json()["components"]["database"] == {"status": "unavailable", "required": True}
    assert response.headers["cache-control"] == "no-store"


def test_public_status_page_is_redacted_and_degrades_with_dependency(client, monkeypatch) -> None:
    monkeypatch.setattr("app.api.health.check_database", lambda: "ok")
    monkeypatch.setattr("app.api.health.check_redis", lambda: "unavailable")

    response = client.get("/health/status")

    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    assert response.json()["components"]["background_services"] == "degraded"
    assert response.json()["contains_customer_data"] is False
