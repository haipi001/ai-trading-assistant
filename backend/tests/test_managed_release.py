from importlib.util import module_from_spec, spec_from_file_location
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "managed_release.py"
SPEC = spec_from_file_location("managed_release", SCRIPT)
assert SPEC and SPEC.loader
managed_release = module_from_spec(SPEC)
SPEC.loader.exec_module(managed_release)


def valid_values() -> dict[str, str]:
    return {
        "COMPOSE_PROJECT_NAME": "atos-production",
        "BACKEND_IMAGE": "registry.example/atos-backend:git-abc123",
        "FRONTEND_IMAGE": "registry.example/atos-frontend@sha256:" + "a" * 64,
        "SERVICE_NAME": "atos-production",
        "RELEASE_ID": "git-abc123",
        "DATABASE_URL": "postgresql+psycopg://user:secret@db.example/atos?sslmode=require",
        "REDIS_URL": "rediss://redis.example/0",
        "BACKEND_CORS_ORIGINS": "https://app.example",
        "OIDC_ISSUER": "https://identity.example/",
        "OIDC_USERINFO_URL": "https://identity.example/userinfo",
        "OIDC_CLIENT_ID": "atos",
        "AUTH_SESSION_SECRET_REF": "aws-sm://atos/session-signing",
        "LEGACY_TENANT_USER_ID": "oidc-owner-sub",
        "ERROR_REPORTING_ENABLED": "true",
        "NOTIFICATION_WEBHOOK_ALLOWED_HOSTS": "alerts.example",
    }


def restore_evidence(*, completed_at: datetime | None = None, **overrides) -> dict:
    values = valid_values()
    payload = {
        "status": "passed",
        "environment": "production",
        "source_database_fingerprint": managed_release.database_fingerprint(values["DATABASE_URL"]),
        "contains_credentials": False,
        "source_database_modified": False,
        "isolated_restore_database": True,
        "temporary_dump_destroyed": True,
        "restore_database_destroyed": True,
        "restore_performed": True,
        "schema_match": True,
        "row_counts_match": True,
        "completed_at": (completed_at or datetime.now(timezone.utc)).isoformat(),
    }
    payload.update(overrides)
    return payload


def write_restore_evidence(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    path.chmod(0o600)
    return path


def backup_snapshot_evidence(*, created_at: datetime | None = None, **overrides) -> dict:
    values = valid_values()
    payload = {
        "status": "passed",
        "provider": "aws_rds",
        "environment": "production",
        "release_id": values["RELEASE_ID"],
        "source_database_fingerprint": managed_release.database_fingerprint(values["DATABASE_URL"]),
        "contains_credentials": False,
        "provider_snapshot_created": True,
        "provider_api_verified": True,
        "real_provider_calls_performed": True,
        "snapshot_retained": True,
        "provider_snapshot_available": True,
        "provider_snapshot_encrypted": True,
        "kms_key_verified": True,
        "manual_snapshot_verified": True,
        "source_instance_verified": True,
        "source_instance_encrypted": True,
        "source_instance_kms_verified": True,
        "snapshot_reference_fingerprint": "snapshot-ref-hash",
        "snapshot_created_at": (created_at or datetime.now(timezone.utc)).isoformat(),
    }
    payload.update(overrides)
    return payload


def test_production_release_environment_accepts_managed_tls_targets() -> None:
    assert managed_release.validate_release_environment(valid_values(), "production") == []


def test_production_release_environment_rejects_local_mutable_and_plaintext_targets() -> None:
    values = valid_values()
    values.update(
        BACKEND_IMAGE="atos-backend:latest",
        DATABASE_URL="sqlite:///local.db",
        REDIS_URL="redis://localhost:6379/0",
        OIDC_ISSUER="http://localhost:9000",
        AUTH_SESSION_SECRET_REF="env://SESSION_SECRET",
        LEGACY_TENANT_USER_ID="default-user",
        BACKEND_CORS_ORIGINS="http://localhost:3000",
        ERROR_REPORTING_ENABLED="false",
    )
    errors = managed_release.validate_release_environment(values, "production")
    assert any("immutable" in error for error in errors)
    assert any("PostgreSQL" in error for error in errors)
    assert any("rediss" in error for error in errors)
    assert any("HTTPS" in error for error in errors)
    assert any("cloud/Vault" in error for error in errors)
    assert any("exact existing owner" in error for error in errors)
    assert any("CORS" in error for error in errors)
    assert any("ERROR_REPORTING_ENABLED" in error for error in errors)


def test_production_release_environment_rejects_staging_fault_injection() -> None:
    values = valid_values()
    values["STAGING_FAULT_INJECTION_ENABLED"] = "true"
    assert "production STAGING_FAULT_INJECTION_ENABLED must be false" in managed_release.validate_release_environment(values, "production")


def test_redacted_release_evidence_excludes_urls_and_credentials() -> None:
    evidence = managed_release.redact(valid_values())
    serialized = str(evidence)
    assert "user:secret" not in serialized
    assert "user:" not in serialized
    assert evidence["contains_credentials"] is False
    assert evidence["database_scheme"] == "postgresql"
    assert evidence["redis_tls"] is True


def test_recent_matching_real_restore_drill_evidence_is_accepted(tmp_path) -> None:
    now = datetime(2026, 7, 17, 12, tzinfo=timezone.utc)
    path = write_restore_evidence(tmp_path / "restore.json", restore_evidence(completed_at=now - timedelta(hours=6)))

    result = managed_release.validate_restore_drill_evidence(
        path,
        environment="production",
        database_url=valid_values()["DATABASE_URL"],
        maximum_age_hours=24,
        now=now,
    )

    assert result["status"] == "verified"
    assert result["age_hours"] == 6
    assert result["real_restore_performed"] is True
    assert len(result["evidence_sha256"]) == 64
    assert "secret" not in str(result)


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"status": "dry_run_valid", "restore_performed": False}, "status must be passed"),
        ({"environment": "staging"}, "environment does not match"),
        ({"source_database_fingerprint": "other-database"}, "fingerprint does not match"),
        ({"schema_match": False}, "schema_match=true"),
    ],
)
def test_restore_drill_gate_rejects_dry_run_cross_environment_or_weak_evidence(tmp_path, override, message) -> None:
    path = write_restore_evidence(tmp_path / "restore.json", restore_evidence(**override))

    with pytest.raises(managed_release.ReleaseError, match=message):
        managed_release.validate_restore_drill_evidence(
            path,
            environment="production",
            database_url=valid_values()["DATABASE_URL"],
            maximum_age_hours=720,
        )


def test_restore_drill_gate_rejects_stale_or_insecure_file(tmp_path) -> None:
    now = datetime(2026, 7, 17, 12, tzinfo=timezone.utc)
    path = write_restore_evidence(tmp_path / "restore.json", restore_evidence(completed_at=now - timedelta(hours=25)))
    with pytest.raises(managed_release.ReleaseError, match="too old"):
        managed_release.validate_restore_drill_evidence(
            path,
            environment="production",
            database_url=valid_values()["DATABASE_URL"],
            maximum_age_hours=24,
            now=now,
        )

    path.chmod(0o644)
    with pytest.raises(managed_release.ReleaseError, match="group/world"):
        managed_release.validate_restore_drill_evidence(
            path,
            environment="production",
            database_url=valid_values()["DATABASE_URL"],
            maximum_age_hours=720,
            now=now,
        )


def test_executed_deploy_requires_restore_drill_evidence_before_compose(monkeypatch, tmp_path) -> None:
    env_file = tmp_path / "production.env"
    env_file.write_text("\n".join(f"{key}={value}" for key, value in valid_values().items()), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", [
        "managed_release.py",
        "--environment", "production",
        "--env-file", str(env_file),
        "--execute",
        "--allow-first-deploy-without-rollback",
    ])

    with pytest.raises(managed_release.ReleaseError, match="requires --restore-drill-evidence"):
        managed_release.main()


def test_recent_matching_real_backup_snapshot_evidence_is_accepted(tmp_path) -> None:
    now = datetime(2026, 7, 17, 12, tzinfo=timezone.utc)
    path = write_restore_evidence(tmp_path / "snapshot.json", backup_snapshot_evidence(created_at=now - timedelta(hours=2)))

    result = managed_release.validate_backup_snapshot_evidence(
        path,
        environment="production",
        database_url=valid_values()["DATABASE_URL"],
        release_id=valid_values()["RELEASE_ID"],
        maximum_age_hours=4,
        now=now,
    )

    assert result["status"] == "verified"
    assert result["provider"] == "aws_rds"
    assert result["age_hours"] == 2
    assert result["snapshot_retained"] is True
    assert len(result["evidence_sha256"]) == 64
    assert "user:secret" not in str(result)


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"status": "dry_run_valid", "real_provider_calls_performed": False}, "status must be passed"),
        ({"release_id": "other-release"}, "release id does not match"),
        ({"source_database_fingerprint": "other-db"}, "fingerprint does not match"),
        ({"provider_snapshot_encrypted": False}, "provider_snapshot_encrypted=true"),
        ({"snapshot_retained": False}, "snapshot_retained=true"),
    ],
)
def test_backup_snapshot_gate_rejects_dry_run_wrong_release_or_weak_snapshot(tmp_path, override, message) -> None:
    path = write_restore_evidence(tmp_path / "snapshot.json", backup_snapshot_evidence(**override))
    with pytest.raises(managed_release.ReleaseError, match=message):
        managed_release.validate_backup_snapshot_evidence(
            path,
            environment="production",
            database_url=valid_values()["DATABASE_URL"],
            release_id=valid_values()["RELEASE_ID"],
            maximum_age_hours=4,
        )


def test_executed_deploy_requires_current_backup_snapshot_after_restore_gate(monkeypatch, tmp_path) -> None:
    env_file = tmp_path / "production.env"
    env_file.write_text("\n".join(f"{key}={value}" for key, value in valid_values().items()), encoding="utf-8")
    restore_path = write_restore_evidence(tmp_path / "restore.json", restore_evidence())
    monkeypatch.setattr(sys, "argv", [
        "managed_release.py",
        "--environment", "production",
        "--env-file", str(env_file),
        "--execute",
        "--allow-first-deploy-without-rollback",
        "--restore-drill-evidence", str(restore_path),
    ])

    with pytest.raises(managed_release.ReleaseError, match="requires --backup-snapshot-evidence"):
        managed_release.main()


def test_successful_deploy_requires_exact_release_id_readiness(monkeypatch, tmp_path) -> None:
    commands = []
    monkeypatch.setattr(managed_release, "run", lambda command, env: commands.append((command, env["RELEASE_ID"])))
    monkeypatch.setattr(managed_release, "wait_for_readiness", lambda url, timeout, expected_release_id: {
        "status": "ready",
        "release_id": expected_release_id,
    })
    result = managed_release.perform_release(
        environment="staging",
        env_file=tmp_path / "staging.env",
        action="deploy",
        target={"backend_image": "backend:new", "frontend_image": "frontend:new", "release_id": "new"},
        rollback_target={"backend_image": "backend:old", "frontend_image": "frontend:old", "release_id": "old"},
        process_env={},
        readiness_url="https://api.example/health/ready",
        readiness_timeout_seconds=1,
    )
    assert result["outcome"] == "deployed"
    assert result["target_readiness_verified"] is True
    assert result["database_migration_attempted"] is True
    assert len(commands) == 5
    assert all(release_id == "new" for _, release_id in commands)
    assert result["database_head_verified"] is True
    assert result["database_schema_drift_verified"] is True


def test_failed_new_release_automatically_restores_previous_images_and_verifies_readiness(monkeypatch, tmp_path) -> None:
    command_release_ids = []
    readiness_release_ids = []
    monkeypatch.setattr(managed_release, "run", lambda command, env: command_release_ids.append(env["RELEASE_ID"]))

    def readiness(url, timeout, expected_release_id):
        readiness_release_ids.append(expected_release_id)
        if expected_release_id == "new":
            raise managed_release.ReleaseError("new release unhealthy")
        return {"status": "ready", "release_id": "old"}

    monkeypatch.setattr(managed_release, "wait_for_readiness", readiness)
    result = managed_release.perform_release(
        environment="production",
        env_file=tmp_path / "production.env",
        action="deploy",
        target={"backend_image": "backend:new", "frontend_image": "frontend:new", "release_id": "new"},
        rollback_target={"backend_image": "backend:old", "frontend_image": "frontend:old", "release_id": "old"},
        process_env={},
        readiness_url="https://api.example/health/ready",
        readiness_timeout_seconds=1,
    )
    assert result["outcome"] == "automatically_rolled_back_after_failed_release"
    assert result["exit_code"] == 2
    assert result["automatic_rollback_attempted"] is True
    assert result["rollback_readiness_verified"] is True
    assert readiness_release_ids == ["new", "old"]
    assert command_release_ids == ["new", "new", "new", "new", "new", "old", "old"]
    assert result["database_downgrade_performed"] is False


def test_migration_failure_does_not_replace_application_or_run_rollback(monkeypatch, tmp_path) -> None:
    calls = 0

    def runner(command, env):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise managed_release.subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(managed_release, "run", runner)
    result = managed_release.perform_release(
        environment="staging",
        env_file=tmp_path / "staging.env",
        action="deploy",
        target={"backend_image": "backend:new", "frontend_image": "frontend:new", "release_id": "new"},
        rollback_target={"backend_image": "backend:old", "frontend_image": "frontend:old", "release_id": "old"},
        process_env={},
        readiness_url="https://api.example/health/ready",
        readiness_timeout_seconds=1,
    )
    assert result["outcome"] == "failed_without_application_change"
    assert result["failed_stage"] == "migration"
    assert result["automatic_rollback_attempted"] is False
    assert calls == 2


def test_post_migration_schema_drift_failure_does_not_replace_application(monkeypatch, tmp_path) -> None:
    commands = []

    def runner(command, env):
        commands.append(command)
        if command[-2:] == ["alembic", "check"]:
            raise managed_release.subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(managed_release, "run", runner)
    result = managed_release.perform_release(
        environment="staging",
        env_file=tmp_path / "staging.env",
        action="deploy",
        target={"backend_image": "backend:new", "frontend_image": "frontend:new", "release_id": "new"},
        rollback_target={"backend_image": "backend:old", "frontend_image": "frontend:old", "release_id": "old"},
        process_env={},
        readiness_url="https://api.example/health/ready",
        readiness_timeout_seconds=1,
    )

    assert result["outcome"] == "failed_without_application_change"
    assert result["failed_stage"] == "schema_drift_verification"
    assert result["database_head_verified"] is True
    assert result["database_schema_drift_verified"] is False
    assert result["automatic_rollback_attempted"] is False
    assert not any("up" in command for command in commands)


def test_release_state_is_mode_0600_and_contains_no_environment_credentials(tmp_path) -> None:
    state_path = tmp_path / "state.json"
    managed_release.save_release_state(state_path, {
        "current": {"backend_image": "backend:a", "frontend_image": "frontend:a", "release_id": "a"},
        "contains_credentials": False,
    })
    assert state_path.stat().st_mode & 0o777 == 0o600
    assert managed_release.load_release_state(state_path)["current"]["release_id"] == "a"
