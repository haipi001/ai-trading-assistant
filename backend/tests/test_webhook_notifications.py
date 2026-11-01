import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.core.config import Settings
from app.core.observability import RedisRequestMetrics
from app.core.secrets import SecretResolution
from app.db.session import get_db
from app.main import app
from app.models import LocalUserConfig, OperationalEvent, SecretReference
from app.services.notifications import NotificationDeliveryError, WebhookNotificationService


class StaticResolver:
    def __init__(self, value: str):
        self.value = value

    def resolve(self, reference: str) -> SecretResolution:
        return SecretResolution(reference=reference, backend="env", value=self.value)


def configured_service(client, *, transport, max_attempts: int = 3):
    session_gen = app.dependency_overrides[get_db]()
    db = next(session_gen)
    reference = "env://TEST_ALERT_WEBHOOK"
    db.add(LocalUserConfig(
        user_id="default-user",
        config_key="notification_preferences",
        value_json={
            "external_channels": {"webhook": reference},
            "external_delivery_consent": {"webhook": True},
        },
        description="test",
    ))
    db.add(SecretReference(
        user_id="default-user",
        reference_key=reference,
        provider="env",
        scope="notification_send",
        storage_backend="env",
        status="active",
        metadata_json={"contains_secret": False},
        last_verified_at=datetime.now(timezone.utc),
    ))
    alert = OperationalEvent(
        user_id="default-user",
        event_type="observability.slo_breached",
        severity="critical",
        source="redis-http-request-metrics",
        message="safe alert",
        status="open",
        payload_json={"requests": 100, "errors": 5, "availability": 0.95},
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    settings = Settings(
        external_notification_delivery_enabled=True,
        NOTIFICATION_WEBHOOK_ALLOWED_HOSTS="alerts.example",
        notification_delivery_retry_seconds=0,
        notification_delivery_max_attempts=max_attempts,
    )
    resolver = StaticResolver(json.dumps({"url": "https://alerts.example/hooks/atos?key=hidden", "authorization": "Bearer hidden-token"}))
    return session_gen, db, alert, WebhookNotificationService(db, settings, resolver=resolver, transport=transport)


def test_webhook_delivery_is_opt_in_allowlisted_and_credential_free_in_audit(client) -> None:
    captured = {}

    def transport(endpoint: str, headers: dict[str, str], body: bytes, timeout: int) -> int:
        captured.update(endpoint=endpoint, headers=headers, body=json.loads(body), timeout=timeout)
        return 202

    session_gen, db, alert, service = configured_service(client, transport=transport)
    try:
        result = service.deliver_alert(user_id="default-user", alert=alert)
        assert result["status"] == "delivered"
        assert result["delivered"] is True
        assert captured["endpoint"].endswith("key=hidden")
        assert captured["headers"]["Authorization"] == "Bearer hidden-token"
        assert captured["body"]["contains_customer_data"] is False
        assert captured["body"]["metrics"] == {
            "window_hours": None,
            "requests": 100,
            "errors": 5,
            "availability": 0.95,
            "error_rate": None,
            "average_latency_ms": None,
        }
        delivery = db.scalar(select(OperationalEvent).where(OperationalEvent.event_type == "notification.webhook_delivery"))
        serialized = json.dumps(delivery.payload_json)
        assert "hidden-token" not in serialized
        assert "key=hidden" not in serialized
        assert delivery.status == "delivered"
        assert delivery.payload_json["external_notification_delivered"] is True
    finally:
        session_gen.close()


def test_webhook_failure_retries_to_limit_then_fails_closed(client) -> None:
    calls = []

    def transport(endpoint: str, headers: dict[str, str], body: bytes, timeout: int) -> int:
        calls.append(endpoint)
        return 503

    session_gen, db, alert, service = configured_service(client, transport=transport, max_attempts=2)
    try:
        first = service.deliver_alert(user_id="default-user", alert=alert)
        second = service.deliver_alert(user_id="default-user", alert=alert)
        third = service.deliver_alert(user_id="default-user", alert=alert)
        assert first["status"] == "failed"
        assert second["status"] == "failed"
        assert third["status"] == "attempts_exhausted"
        assert third["attempted"] is False
        assert len(calls) == 2
        failures = list(db.scalars(select(OperationalEvent).where(OperationalEvent.event_type == "notification.webhook_delivery")).all())
        assert len(failures) == 2
        assert all(item.status == "failed" for item in failures)
    finally:
        session_gen.close()


def test_later_success_resolves_prior_failed_delivery_event(client) -> None:
    statuses = iter([503, 204])

    def transport(endpoint: str, headers: dict[str, str], body: bytes, timeout: int) -> int:
        return next(statuses)

    session_gen, db, alert, service = configured_service(client, transport=transport, max_attempts=3)
    try:
        assert service.deliver_alert(user_id="default-user", alert=alert)["status"] == "failed"
        assert service.deliver_alert(user_id="default-user", alert=alert)["status"] == "delivered"
        attempts = list(db.scalars(select(OperationalEvent).where(
            OperationalEvent.event_type == "notification.webhook_delivery"
        ).order_by(OperationalEvent.created_at)).all())
        assert [item.status for item in attempts] == ["resolved", "delivered"]
        assert attempts[0].payload_json["resolution_reason"] == "later_webhook_delivery_succeeded"
        assert service.delivery_summary(user_id="default-user") == {
            "delivered": 1,
            "failed": 0,
            "real_delivery_evidence": True,
        }
    finally:
        session_gen.close()


def test_webhook_rejects_redirect_prone_or_private_targets_before_transport(client) -> None:
    session_gen, _db, _alert, service = configured_service(client, transport=lambda *_: 200)
    try:
        with pytest.raises(NotificationDeliveryError):
            service._parse_secret("http://alerts.example/hook")
        with pytest.raises(NotificationDeliveryError):
            service._parse_secret("https://127.0.0.1/hook")
        with pytest.raises(NotificationDeliveryError):
            service._parse_secret("https://other.example/hook")
        with pytest.raises(NotificationDeliveryError):
            service._parse_secret(json.dumps({"url": "https://alerts.example/hook", "authorization": "Bearer ok\r\nX-Evil: yes"}))
    finally:
        session_gen.close()


def test_webhook_readiness_requires_verified_reference_and_explicit_consent(client) -> None:
    session_gen = app.dependency_overrides[get_db]()
    db = next(session_gen)
    try:
        settings = Settings(
            external_notification_delivery_enabled=True,
            NOTIFICATION_WEBHOOK_ALLOWED_HOSTS="alerts.example",
        )
        readiness = WebhookNotificationService(db, settings).readiness(user_id="default-user")
        assert readiness["status"] == "blocked"
        assert "webhook_secret_reference_missing" in readiness["blockers"]
        assert "webhook_delivery_consent_missing" in readiness["blockers"]
    finally:
        session_gen.close()


def test_slo_breach_records_real_delivery_result_on_alert(client, monkeypatch) -> None:
    monkeypatch.setattr(RedisRequestMetrics, "snapshot", lambda self, window_hours=24: {
        "status": "breached",
        "window_hours": 24,
        "requests": 100,
        "errors": 5,
        "availability": 0.95,
        "error_rate": 0.05,
        "average_latency_ms": 1200,
        "targets": {"availability": 0.995},
        "sample_sufficient": True,
        "real_request_metrics": True,
    })
    monkeypatch.setattr(WebhookNotificationService, "deliver_alert", lambda self, user_id, alert, test=False: {
        "status": "delivered",
        "delivered": True,
        "attempted": True,
        "delivery_event_id": "delivery-proof-id",
        "external_message_sent": True,
    })
    response = client.post("/ops/observability/evaluate")
    assert response.status_code == 201
    payload = response.json()
    assert payload["notification"]["external_notification_delivered"] is True
    assert payload["notification"]["external_delivery"]["delivery_event_id"] == "delivery-proof-id"

    session_gen = app.dependency_overrides[get_db]()
    db = next(session_gen)
    try:
        alert = db.scalar(select(OperationalEvent).where(OperationalEvent.event_type == "observability.slo_breached"))
        assert alert.payload_json["external_notification_delivered"] is True
        assert alert.payload_json["external_notification_delivery_event_id"] == "delivery-proof-id"
    finally:
        session_gen.close()
