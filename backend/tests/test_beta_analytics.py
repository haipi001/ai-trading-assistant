from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.auth import AuthenticatedUser
from app.core.auth import ROLE_PERMISSIONS
from app.core.config import Settings
from app.db.base import Base
from app.models import ExportArtifact
from app.models import LocalUserConfig
from app.models import OperationalEvent
from app.models import UserAccount
from app.services.beta_analytics import BetaAnalyticsError
from app.services.beta_analytics import BetaAnalyticsService
from app.services.privacy_center import PrivacyCenterService


@pytest.fixture()
def db() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)


def actor(user_id: str = "founder", role: str = "owner") -> AuthenticatedUser:
    return AuthenticatedUser(user_id=user_id, role=role, permissions=ROLE_PERMISSIONS[role], auth_required=True, token_configured=True)


def qualified_payload() -> dict:
    return {
        "holds_us_equity_or_etf": True,
        "holds_crypto": True,
        "thesis_driven": True,
        "self_directed": True,
        "private_beta_consent": True,
        "risk_disclosure_acknowledged": True,
        "consent_action": BetaAnalyticsService.CONSENT_ACTION,
        "beta_terms_version": BetaAnalyticsService.TERMS_VERSION,
        "privacy_policy_version": PrivacyCenterService.POLICY_VERSION,
    }


def test_icp_profile_requires_all_criteria_and_never_counts_as_usage(db) -> None:
    service = BetaAnalyticsService(db)
    user = actor("profile-user", "viewer")
    incomplete = service.save_profile(actor=user, payload={**qualified_payload(), "holds_crypto": False})
    assert incomplete["qualified"] is False
    assert incomplete["usage_metrics_counted"] is False
    complete = service.save_profile(actor=user, payload=qualified_payload())
    assert complete["qualified"] is True
    assert complete["profile"]["evidence_kind"] == "user_self_attestation_not_usage_evidence"
    assert complete["consent_current"] is True
    assert complete["profile"]["consent_accepted_at"]


def test_beta_consent_requires_current_versions_and_can_be_withdrawn(db) -> None:
    service = BetaAnalyticsService(db)
    user = actor("consent-user", "viewer")
    with pytest.raises(BetaAnalyticsError, match="versioned"):
        service.save_profile(actor=user, payload={**qualified_payload(), "privacy_policy_version": "old-policy"})
    accepted = service.save_profile(actor=user, payload=qualified_payload())
    assert accepted["qualified"] is True
    withdrawn = service.save_profile(actor=user, payload={
        **qualified_payload(),
        "private_beta_consent": False,
        "risk_disclosure_acknowledged": False,
        "consent_action": None,
    })
    assert withdrawn["qualified"] is False
    assert withdrawn["consent_current"] is False
    assert withdrawn["profile"]["consent_withdrawn_at"]


def test_local_environment_and_manual_activation_events_never_verify_beta(db) -> None:
    service = BetaAnalyticsService(db, Settings(environment="local"))
    user = actor("real-looking-user", "viewer")
    service.save_profile(actor=user, payload=qualified_payload())
    db.add(UserAccount(user_id=user.user_id, display_name="User", role="viewer", status="active", permissions_json=ROLE_PERMISSIONS["viewer"], onboarding_state_json={"identity_provider": "https://id.example.com"}))
    db.add(OperationalEvent(user_id=user.user_id, event_type="activation.weekly_return", severity="info", source="manual", message="manual", status="closed", payload_json={}))
    db.commit()

    report = service.metrics(actor=actor())

    assert report["status"] == "insufficient_real_beta_evidence"
    assert report["counts"]["identity_verified_profiles"] == 0
    assert report["manual_activation_events_counted"] is False
    assert report["registered_users_counted_without_behavior"] is False
    assert "real_staging_or_production_oidc_environment_missing" in report["blockers"]


def test_metrics_derive_five_user_four_week_retention_from_daily_records(db) -> None:
    settings = Settings(environment="staging", managed_auth_required=True, oidc_issuer="https://id.example.com", oidc_userinfo_url="https://id.example.com/userinfo", oidc_client_id="atos")
    service = BetaAnalyticsService(db, settings)
    now = service._now()
    for index in range(5):
        user_id = f"beta-user-{index}"
        user = actor(user_id, "viewer")
        service.save_profile(actor=user, payload=qualified_payload())
        profile = db.scalar(select(LocalUserConfig).where(LocalUserConfig.user_id == user_id, LocalUserConfig.config_key == service.PROFILE_KEY))
        recorded = now - timedelta(days=29)
        profile.value_json = {**profile.value_json, "recorded_at": recorded.isoformat(), "qualified_at": recorded.isoformat()}
        db.add(UserAccount(user_id=user_id, display_name=f"Beta {index}", role="viewer", status="active", permissions_json=ROLE_PERMISSIONS["viewer"], onboarding_state_json={"identity_provider": "https://id.example.com"}))
        for day in (0, 7, 14, 21, 28):
            timestamp = recorded + timedelta(days=day, hours=1)
            db.add(ExportArtifact(user_id=user_id, export_type="daily_open_record", format="json", status="open", payload_json={}, summary_json={}, file_path=None, created_at=timestamp))
            db.add(ExportArtifact(user_id=user_id, export_type="daily_close_record", format="json", status="closed", payload_json={}, summary_json={}, file_path=None, created_at=timestamp + timedelta(hours=1)))
    db.commit()

    report = service.metrics(actor=actor("ops", "operator"))

    assert report["status"] == "verified"
    assert report["counts"]["four_week_retained_users"] == 5
    assert report["metrics"]["activation_rate"] == 1.0
    assert report["metrics"]["first_day_loop_rate"] == 1.0
    assert report["metrics"]["d7_retention_rate"] == 1.0
    assert report["metrics"]["four_week_retention_rate"] == 1.0
    assert report["metrics"]["daily_review_completion_rate"] == 1.0
    assert all(row["raw_user_id_returned"] is False for row in report["users"])
    assert all("beta-user" not in row["user_ref"] for row in report["users"])


def test_ineligible_or_test_identities_are_excluded_from_verified_denominators(db) -> None:
    settings = Settings(environment="staging", managed_auth_required=True, oidc_issuer="https://id.example.com", oidc_userinfo_url="https://id.example.com/userinfo", oidc_client_id="atos")
    service = BetaAnalyticsService(db, settings)
    for user_id, payload in (("default-user", qualified_payload()), ("eligible-user", {**qualified_payload(), "thesis_driven": False})):
        service.save_profile(actor=actor(user_id, "viewer"), payload=payload)
        db.add(UserAccount(user_id=user_id, display_name=user_id, role="viewer", status="active", permissions_json=ROLE_PERMISSIONS["viewer"], onboarding_state_json={"identity_provider": "https://id.example.com"}))
    db.commit()
    report = service.metrics(actor=actor("ops", "operator"))
    assert report["counts"]["qualified_profiles"] == 1
    assert report["counts"]["identity_verified_profiles"] == 0


def test_viewer_cannot_read_cross_user_beta_analytics(db) -> None:
    with pytest.raises(BetaAnalyticsError, match="operator permission"):
        BetaAnalyticsService(db).metrics(actor=actor("viewer-user", "viewer"))


def test_beta_profile_and_analytics_api_permissions(client) -> None:
    viewer_headers = {"X-AI-Trading-User": "profile-api-user", "X-AI-Trading-Role": "viewer"}
    operator_headers = {"X-AI-Trading-User": "profile-api-operator", "X-AI-Trading-Role": "operator"}
    saved = client.put("/production/beta-profile", headers=viewer_headers, json=qualified_payload())
    assert saved.status_code == 200
    assert saved.json()["qualified"] is True
    assert client.get("/production/beta-analytics", headers=viewer_headers).status_code == 403
    report = client.get("/production/beta-analytics", headers=operator_headers)
    assert report.status_code == 200
    assert report.json()["status"] == "insufficient_real_beta_evidence"
