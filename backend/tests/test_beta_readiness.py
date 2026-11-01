from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import OperationalEvent


OWNER_HEADERS = {
    "X-AI-Trading-User": "beta-owner",
    "X-AI-Trading-Role": "owner",
}


def test_beta_whoami_uses_header_identity_and_creates_user(client: TestClient) -> None:
    response = client.get(
        "/beta/whoami",
        headers={"X-AI-Trading-User": "beta-operator", "X-AI-Trading-Role": "operator"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == "beta-operator"
    assert body["role"] == "operator"
    assert body["auth_required"] is False
    assert body["execution_available"] is False
    assert "events:write" in body["permissions"]

    users_response = client.get("/beta/users", headers=OWNER_HEADERS)
    assert users_response.status_code == 200
    assert any(user["user_id"] == "beta-operator" for user in users_response.json())


def test_viewer_cannot_write_users(client: TestClient) -> None:
    response = client.post(
        "/beta/users",
        json={
            "user_id": "blocked-viewer-write",
            "display_name": "Blocked Viewer Write",
            "role": "viewer",
        },
        headers={"X-AI-Trading-User": "readonly-user", "X-AI-Trading-Role": "viewer"},
    )

    assert response.status_code == 403


def test_secret_reference_rejects_inline_secret_metadata(client: TestClient) -> None:
    response = client.post(
        "/beta/secrets/references",
        json={
            "user_id": "beta-owner",
            "reference_key": "IBKR_READONLY",
            "provider": "ibkr",
            "metadata_json": {"api_key": "do-not-store"},
        },
        headers=OWNER_HEADERS,
    )

    assert response.status_code == 422


def test_beta_readiness_blocks_when_auth_is_not_required_locally(client: TestClient) -> None:
    response = client.get("/beta/readiness", headers=OWNER_HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert body["beta_ready"] is False
    assert body["execution_available"] is False
    checks = {item["key"]: item for item in body["checklist"]}
    assert checks["auth"]["status"] == "block"
    assert checks["safety"]["status"] == "ok"
    assert any("BETA_AUTH_REQUIRED" in action for action in checks["auth"]["next_actions"])


def test_external_beta_launch_report_aggregates_readiness_ops_data_and_ledger(client: TestClient) -> None:
    response = client.get("/beta/external-launch-report", headers=OWNER_HEADERS)

    assert response.status_code == 200
    body = response.json()
    checks = {item["key"]: item for item in body["checks"]}
    assert body["launch_status"] == "blocked"
    assert body["execution_available"] is False
    assert body["live_execution_available"] is False
    assert body["release_controls"]["auth_required"] is False
    assert body["release_controls"]["live_trading_enabled"] is False
    assert body["release_controls"]["live_execution_enabled"] is False
    assert checks["beta_readiness"]["status"] == "block"
    assert checks["release_controls"]["status"] == "block"
    assert checks["data_trust"]["status"] in {"warn", "block"}
    assert checks["ledger_preflight"]["status"] in {"warn", "block"}
    assert any("BETA_AUTH_REQUIRED" in action for action in body["next_actions"])


def test_release_control_report_blocks_external_invites_until_production_controls_pass(client: TestClient) -> None:
    response = client.get("/beta/release-control-report", headers=OWNER_HEADERS)

    assert response.status_code == 200
    body = response.json()
    checks = {item["key"]: item for item in body["checks"]}
    assert body["release_status"] == "blocked"
    assert body["can_invite_external_users"] is False
    assert body["execution_available"] is False
    assert body["live_execution_available"] is False
    assert checks["auth"]["status"] == "block"
    assert checks["safety_locks"]["status"] == "block"
    assert "beta_auth_not_fully_configured" in body["blockers"]


def test_beta_backup_manifest_creates_read_only_export_for_current_user(client: TestClient) -> None:
    response = client.post("/beta/backup-manifest", headers=OWNER_HEADERS)

    assert response.status_code == 201
    body = response.json()
    assert body["user_id"] == "beta-owner"
    assert body["export_type"] == "local_backup_manifest"
    assert body["status"] == "ready"
    assert body["summary_json"]["execution_available"] is False
    assert body["payload_json"]["safe_mode"] == "read_only_local_export"

    events_response = client.get("/beta/events", headers=OWNER_HEADERS)
    assert events_response.status_code == 200
    assert any(event["event_type"] == "backup_manifest.created" for event in events_response.json())


def test_beta_events_allow_closed_operational_events(client: TestClient) -> None:
    create_response = client.post(
        "/beta/events",
        headers=OWNER_HEADERS,
        json={
            "event_type": "local_start.initialized",
            "severity": "info",
            "source": "settings",
            "message": "Local start center recorded a completed setup event.",
            "status": "closed",
            "payload_json": {"execution_available": False},
        },
    )

    assert create_response.status_code == 201
    assert create_response.json()["status"] == "closed"

    events_response = client.get("/beta/events?status=closed", headers=OWNER_HEADERS)
    assert events_response.status_code == 200
    assert any(event["event_type"] == "local_start.initialized" for event in events_response.json())


def test_beta_events_normalizes_legacy_admin_events() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    with TestingSessionLocal() as db:
        db.add(
            OperationalEvent(
                user_id="legacy-user",
                event_type="legacy.admin_event",
                severity="block",
                source="legacy_admin_console",
                message="Legacy admin event uses old enum values.",
                status="blocked",
                payload_json={"note": "old status shape"},
            )
        )
        db.commit()

    def override_get_db():
        db: Session = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            response = test_client.get("/beta/events?limit=10", headers=OWNER_HEADERS)
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)

    assert response.status_code == 200
    event = next(item for item in response.json() if item["event_type"] == "legacy.admin_event")
    assert event["severity"] == "warning"
    assert event["status"] == "open"
    assert event["payload_json"]["original_severity"] == "block"
    assert event["payload_json"]["original_status"] == "blocked"
