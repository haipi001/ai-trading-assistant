from datetime import datetime
from datetime import timedelta
from datetime import timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.auth import AuthenticatedUser
from app.core.auth import ROLE_PERMISSIONS
from app.db.base import Base
from app.models import AuditLog
from app.models import OperationalEvent
from app.services.production_foundation import ProductionFoundationError
from app.services.production_foundation import ProductionFoundationService


@pytest.fixture()
def db() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)


def owner(user_id: str = "retention-owner") -> AuthenticatedUser:
    return AuthenticatedUser(
        user_id=user_id,
        role="owner",
        permissions=ROLE_PERMISSIONS["owner"],
        auth_required=True,
        token_configured=True,
    )


def event(*, user_id: str, event_type: str, status: str, age_days: int) -> OperationalEvent:
    return OperationalEvent(
        user_id=user_id,
        event_type=event_type,
        severity="info",
        source="retention-test",
        message="No customer data.",
        status=status,
        payload_json={"contains_customer_data": False},
        created_at=datetime.now(timezone.utc) - timedelta(days=age_days),
    )


def test_retention_defaults_to_disabled_preview_and_protects_business_records(db) -> None:
    actor = owner()
    db.add_all([
        event(user_id=actor.user_id, event_type="observability.slo_breached", status="resolved", age_days=120),
        event(user_id=actor.user_id, event_type="activation.weekly_return", status="closed", age_days=900),
        event(user_id=actor.user_id, event_type="restore_drill", status="closed", age_days=900),
        event(user_id="other-user", event_type="observability.slo_breached", status="resolved", age_days=120),
    ])
    db.commit()

    result = ProductionFoundationService(db).retention_status(actor=actor)

    assert result["status"] == "not_configured"
    assert result["policy"]["enabled"] is False
    assert result["preview"]["total_eligible"] == 1
    assert "investment_records" in result["protected_data"]


def test_retention_policy_rejects_unsafe_periods_and_secret_shaped_payload(db) -> None:
    service = ProductionFoundationService(db)
    actor = owner()

    with pytest.raises(ProductionFoundationError, match="between 30 and 3650"):
        service.configure_retention(actor=actor, payload={"observability_days": 7})
    with pytest.raises(ProductionFoundationError, match="between 365 and 3650"):
        service.configure_retention(actor=actor, payload={"notification_delivery_days": 30})
    with pytest.raises(ProductionFoundationError, match="must not contain secrets"):
        service.configure_retention(actor=actor, payload={"api_key": "must-never-be-stored"})


def test_apply_retention_requires_enabled_policy_and_exact_confirmation(db) -> None:
    service = ProductionFoundationService(db)
    actor = owner()
    service.configure_retention(actor=actor, payload={"enabled": False})

    with pytest.raises(ProductionFoundationError, match="exact retention confirmation"):
        service.apply_retention(actor=actor, confirmation="delete")
    with pytest.raises(ProductionFoundationError, match="configured and enabled"):
        service.apply_retention(actor=actor, confirmation=service.RETENTION_CONFIRMATION)


def test_apply_retention_deletes_only_expired_owned_telemetry_and_audits_summary(db) -> None:
    actor = owner()
    rows = [
        event(user_id=actor.user_id, event_type="observability.slo_breached", status="resolved", age_days=120),
        event(user_id=actor.user_id, event_type="observability.slo_breached", status="open", age_days=120),
        event(user_id=actor.user_id, event_type="notification.webhook_delivery", status="delivered", age_days=400),
        event(user_id=actor.user_id, event_type="activation.weekly_return", status="closed", age_days=900),
        event(user_id="other-user", event_type="notification.webhook_delivery", status="delivered", age_days=400),
    ]
    db.add_all(rows)
    db.commit()
    deleted_ids = {rows[0].id, rows[2].id}
    protected_ids = {rows[1].id, rows[3].id, rows[4].id}
    service = ProductionFoundationService(db)
    service.configure_retention(
        actor=actor,
        payload={"enabled": True, "observability_days": 90, "notification_delivery_days": 365, "audit_days": 2555},
    )

    result = service.apply_retention(actor=actor, confirmation=service.RETENTION_CONFIRMATION)

    remaining_ids = set(db.scalars(select(OperationalEvent.id)).all())
    assert deleted_ids.isdisjoint(remaining_ids)
    assert protected_ids.issubset(remaining_ids)
    assert result["deleted"] == {"observability": 1, "notification_delivery": 1}
    assert result["audit_logs_deleted"] == 0
    assert result["investment_records_deleted"] == 0
    audit = db.scalar(select(AuditLog).where(AuditLog.action == "production.retention_applied"))
    assert audit is not None
    assert audit.payload_json["protected_data_deleted"] is False


def test_retention_api_supports_preview_configuration_and_guarded_apply(client) -> None:
    headers = {"X-AI-Trading-User": "api-retention-owner", "X-AI-Trading-Role": "owner"}

    preview = client.get("/production/retention", headers=headers)
    assert preview.status_code == 200
    assert preview.json()["status"] == "not_configured"
    configured = client.put(
        "/production/retention",
        headers=headers,
        json={
            "enabled": True,
            "observability_days": 90,
            "notification_delivery_days": 365,
            "audit_days": 2555,
        },
    )
    assert configured.status_code == 200
    assert configured.json()["policy"]["enabled"] is True
    rejected = client.post("/production/retention/apply", headers=headers, json={"confirmation": "wrong"})
    assert rejected.status_code == 422
    applied = client.post(
        "/production/retention/apply",
        headers=headers,
        json={"confirmation": "DELETE_EXPIRED_OPERATIONAL_TELEMETRY"},
    )
    assert applied.status_code == 200
    assert applied.json()["protected_data_deleted"] is False
