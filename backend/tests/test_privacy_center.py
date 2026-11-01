from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.auth import AuthenticatedUser
from app.core.auth import ROLE_PERMISSIONS
from app.db.base import Base
from app.models import AuditLog
from app.models import LocalUserConfig
from app.models import Reminder
from app.models import SecretReference
from app.models import UserAccount
from app.services.privacy_center import PrivacyCenterError
from app.services.privacy_center import PrivacyCenterService


@pytest.fixture()
def db() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)


def viewer(user_id: str = "privacy-user") -> AuthenticatedUser:
    return AuthenticatedUser(
        user_id=user_id,
        role="viewer",
        permissions=ROLE_PERMISSIONS["viewer"],
        auth_required=True,
        token_configured=True,
    )


def seed_user(db: Session, user_id: str = "privacy-user") -> None:
    db.add_all([
        UserAccount(user_id=user_id, display_name="Private User", role="viewer", status="active", permissions_json=ROLE_PERMISSIONS["viewer"], onboarding_state_json={}),
        Reminder(user_id=user_id, title="Review thesis", reminder_type="manual", priority="normal", status="pending", payload_json={"note": "personal"}),
        LocalUserConfig(user_id=user_id, config_key="notification_preferences", value_json={"webhook_secret_ref": "aws-sm://private/hook", "theme": "dark"}),
        LocalUserConfig(user_id=user_id, config_key="auth_session:test-jti", value_json={"status": "active", "token": "must-not-export"}),
        SecretReference(user_id=user_id, reference_key="aws-sm://private/api-key", provider="aws-sm", scope="read_only", storage_backend="aws-sm", status="active", metadata_json={"version": "1"}),
        Reminder(user_id="other-user", title="Other user", reminder_type="manual", priority="normal", status="pending", payload_json={}),
    ])
    db.commit()


def test_privacy_status_has_real_inventory_and_non_advice_disclosure(db) -> None:
    seed_user(db)

    result = PrivacyCenterService(db).status(actor=viewer())

    assert result["data_inventory"]["records"] >= 5
    assert result["deletion"]["status"] == "not_requested"
    assert "not individualized investment advice" in result["policy"]["risk_disclosure"]
    assert result["policy"]["legal_review_status"] == "requires_qualified_counsel_before_public_launch"


def test_portability_export_covers_tenant_tables_but_redacts_security_material(db) -> None:
    seed_user(db)

    packet = PrivacyCenterService(db).export(actor=viewer())

    assert packet["packet_type"] == "user_data_portability_export"
    assert packet["record_counts"]["reminders"] == 1
    assert packet["omitted_security_records"]["local_user_configs"] == 1
    assert packet["redaction"]["secret_values_included"] is False
    secret_row = packet["tables"]["secret_references"][0]
    assert secret_row["reference_key"]["redacted"] is True
    config_row = packet["tables"]["local_user_configs"][0]
    assert config_row["value_json"]["webhook_secret_ref"]["redacted"] is True
    serialized = str(packet)
    assert "must-not-export" not in serialized
    assert "aws-sm://private/api-key" not in serialized
    assert "Other user" not in serialized


def test_deletion_request_requires_exact_phrase_returns_nonce_once_and_can_cancel(db) -> None:
    seed_user(db)
    service = PrivacyCenterService(db)
    actor = viewer()

    with pytest.raises(PrivacyCenterError, match="exact deletion request"):
        service.request_deletion(actor=actor, confirmation="delete")
    requested = service.request_deletion(actor=actor, confirmation=service.REQUEST_CONFIRMATION)
    assert requested["nonce_shown_once"] is True
    assert requested["verification_nonce"]
    status = service.status(actor=actor)
    assert status["deletion"]["status"] == "pending"
    assert status["deletion"]["nonce_returned"] is False
    cancelled = service.cancel_deletion(actor=actor)
    assert cancelled == {"status": "cancelled", "nonce_invalidated": True}
    with pytest.raises(PrivacyCenterError, match="no pending"):
        service.execute_deletion(actor=actor, confirmation=service.EXECUTE_CONFIRMATION, nonce=requested["verification_nonce"])


def test_deletion_fails_closed_during_grace_or_with_wrong_nonce(db) -> None:
    seed_user(db)
    service = PrivacyCenterService(db)
    actor = viewer()
    requested = service.request_deletion(actor=actor, confirmation=service.REQUEST_CONFIRMATION)

    with pytest.raises(PrivacyCenterError, match="nonce is invalid"):
        service.execute_deletion(actor=actor, confirmation=service.EXECUTE_CONFIRMATION, nonce="wrong")
    with pytest.raises(PrivacyCenterError, match="grace period has not elapsed"):
        service.execute_deletion(actor=actor, confirmation=service.EXECUTE_CONFIRMATION, nonce=requested["verification_nonce"])


def test_deletion_removes_only_requesting_tenant_and_pseudonymizes_audit(db) -> None:
    seed_user(db)
    service = PrivacyCenterService(db)
    actor = viewer()
    requested = service.request_deletion(actor=actor, confirmation=service.REQUEST_CONFIRMATION)
    record = db.scalar(select(LocalUserConfig).where(LocalUserConfig.user_id == actor.user_id, LocalUserConfig.config_key == service.REQUEST_KEY))
    assert record is not None
    record.value_json = {**record.value_json, "scheduled_for": (service._now() - timedelta(seconds=1)).isoformat()}
    db.commit()

    result = service.execute_deletion(actor=actor, confirmation=service.EXECUTE_CONFIRMATION, nonce=requested["verification_nonce"])

    assert result["status"] == "completed"
    assert result["deleted_record_count"] >= 5
    assert db.scalar(select(Reminder).where(Reminder.user_id == actor.user_id)) is None
    assert db.scalar(select(UserAccount).where(UserAccount.user_id == actor.user_id)) is None
    assert db.scalar(select(Reminder).where(Reminder.user_id == "other-user")) is not None
    receipts = list(db.scalars(select(AuditLog).where(AuditLog.action == "privacy.data_deletion_completed")).all())
    assert len(receipts) == 1
    assert receipts[0].user_id.startswith("deleted-")
    assert actor.user_id not in str(receipts[0].payload_json)


def test_privacy_api_is_available_to_authenticated_viewer(client) -> None:
    headers = {"X-AI-Trading-User": "privacy-api-user", "X-AI-Trading-Role": "viewer"}
    status = client.get("/production/privacy", headers=headers)
    assert status.status_code == 200
    exported = client.post("/production/privacy/export", headers=headers)
    assert exported.status_code == 201
    assert exported.json()["redaction"]["secret_values_included"] is False
    rejected = client.post("/production/privacy/deletion-request", headers=headers, json={"confirmation": "wrong"})
    assert rejected.status_code == 422
