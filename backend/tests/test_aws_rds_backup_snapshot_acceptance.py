from datetime import datetime, timedelta, timezone
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sys

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "aws_rds_backup_snapshot_acceptance.py"
SPEC = spec_from_file_location("aws_rds_backup_snapshot_acceptance", SCRIPT)
assert SPEC and SPEC.loader
snapshot = module_from_spec(SPEC)
SPEC.loader.exec_module(snapshot)


def described(*, now: datetime, **overrides) -> dict:
    value = {
        "DBSnapshotIdentifier": "atos-release-20260717120000",
        "DBInstanceIdentifier": "atos-production-db",
        "Status": "available",
        "SnapshotType": "manual",
        "Encrypted": True,
        "KmsKeyId": "arn:aws:kms:region:account:key/redacted",
        "SnapshotCreateTime": (now - timedelta(minutes=4)).isoformat(),
        "DBSnapshotArn": "arn:aws:rds:region:account:snapshot:atos-release-20260717120000",
    }
    value.update(overrides)
    return {"DBSnapshots": [value]}


def described_instance(**overrides) -> dict:
    value = {
        "DBInstanceIdentifier": "atos-production-db",
        "Engine": "postgres",
        "Endpoint": {"Address": "db.example", "Port": 5432},
        "StorageEncrypted": True,
        "KmsKeyId": "arn:aws:kms:region:account:key/redacted",
    }
    value.update(overrides)
    return {"DBInstances": [value]}


def test_source_rds_instance_must_match_managed_database_endpoint_and_encryption() -> None:
    result = snapshot.verify_instance(
        described_instance(),
        database_url="postgresql+psycopg://user:redacted@db.example/atos?sslmode=require",
        instance_id="atos-production-db",
    )
    assert result["source_instance_verified"] is True
    assert result["source_instance_encrypted"] is True
    assert len(result["source_endpoint_fingerprint"]) == 16
    assert "db.example" not in str(result)

    with pytest.raises(snapshot.SnapshotError, match="endpoint does not match"):
        snapshot.verify_instance(
            described_instance(),
            database_url="postgresql://user:redacted@other.example/atos?sslmode=require",
            instance_id="atos-production-db",
        )
    with pytest.raises(snapshot.SnapshotError, match="storage must be encrypted"):
        snapshot.verify_instance(
            described_instance(StorageEncrypted=False),
            database_url="postgresql://user:redacted@db.example/atos?sslmode=require",
            instance_id="atos-production-db",
        )


def test_verified_snapshot_requires_new_available_manual_encrypted_kms_snapshot() -> None:
    now = datetime(2026, 7, 17, 12, tzinfo=timezone.utc)
    result = snapshot.verify_snapshot(
        described(now=now),
        instance_id="atos-production-db",
        snapshot_id="atos-release-20260717120000",
        now=now,
    )

    assert result["provider_snapshot_available"] is True
    assert result["provider_snapshot_encrypted"] is True
    assert result["kms_key_verified"] is True
    assert result["manual_snapshot_verified"] is True
    assert result["snapshot_age_minutes"] == 4
    assert len(result["snapshot_reference_fingerprint"]) == 16
    assert "arn:aws" not in str(result)


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"Status": "creating"}, "not available"),
        ({"SnapshotType": "automated"}, "must be manual"),
        ({"Encrypted": False}, "must be encrypted"),
        ({"KmsKeyId": None}, "must report a KMS key"),
        ({"DBInstanceIdentifier": "other-db"}, "instance mismatch"),
    ],
)
def test_snapshot_verification_fails_closed_for_weak_or_wrong_snapshot(override, message) -> None:
    now = datetime(2026, 7, 17, 12, tzinfo=timezone.utc)
    with pytest.raises(snapshot.SnapshotError, match=message):
        snapshot.verify_snapshot(
            described(now=now, **override),
            instance_id="atos-production-db",
            snapshot_id="atos-release-20260717120000",
            now=now,
        )


def test_snapshot_verification_rejects_old_or_ambiguous_provider_response() -> None:
    now = datetime(2026, 7, 17, 12, tzinfo=timezone.utc)
    with pytest.raises(snapshot.SnapshotError, match="newly created"):
        snapshot.verify_snapshot(
            described(now=now, SnapshotCreateTime=(now - timedelta(minutes=61)).isoformat()),
            instance_id="atos-production-db",
            snapshot_id="atos-release-20260717120000",
            now=now,
        )
    with pytest.raises(snapshot.SnapshotError, match="exactly one"):
        snapshot.verify_snapshot(
            {"DBSnapshots": []},
            instance_id="atos-production-db",
            snapshot_id="atos-release-20260717120000",
            now=now,
        )


def test_production_inputs_require_remote_tls_postgres_and_valid_rds_ids() -> None:
    valid = snapshot.validate_inputs(
        environment="production",
        database_url="postgresql+psycopg://user:redacted@db.example/atos?sslmode=require",
        instance_id="atos-production-db",
        snapshot_id="atos-release-20260717120000",
    )
    assert valid == []

    errors = snapshot.validate_inputs(
        environment="production",
        database_url="postgresql://user:redacted@localhost/atos",
        instance_id="bad_instance",
        snapshot_id="Bad--Snapshot-",
    )
    assert any("local/container" in error for error in errors)
    assert any("require TLS" in error for error in errors)
    assert any("INSTANCE_ID" in error for error in errors)
    assert any("snapshot id" in error for error in errors)


def test_generated_snapshot_id_is_safe_and_bounded() -> None:
    now = datetime(2026, 7, 17, 12, tzinfo=timezone.utc)
    value = snapshot.safe_snapshot_id("GIT_SHA/Feature With Spaces!" * 4, now)
    assert len(value) <= 63
    assert value.startswith("atos-git-sha-feature-with-sp")


def test_execute_creates_waits_describes_and_saves_only_redacted_evidence(monkeypatch, tmp_path) -> None:
    instance_id = "atos-staging-db"
    database_url = "postgresql+psycopg://user:redacted@db.example/atos?sslmode=require"
    provider_calls = []
    wait_calls = []

    def fake_aws(arguments):
        provider_calls.append(arguments)
        operation = arguments[1]
        if operation == "describe-db-instances":
            return described_instance(DBInstanceIdentifier=instance_id)
        if operation == "create-db-snapshot":
            return {"DBSnapshot": {"Status": "creating"}}
        if operation == "describe-db-snapshots":
            snapshot_id = arguments[arguments.index("--db-snapshot-identifier") + 1]
            return described(
                now=datetime.now(timezone.utc),
                DBInstanceIdentifier=instance_id,
                DBSnapshotIdentifier=snapshot_id,
                DBSnapshotArn=f"arn:aws:rds:region:account:snapshot:{snapshot_id}",
            )
        raise AssertionError(arguments)

    monkeypatch.setenv(snapshot.DATABASE_URL_ENV, database_url)
    monkeypatch.setenv(snapshot.INSTANCE_ID_ENV, instance_id)
    monkeypatch.delenv(snapshot.SNAPSHOT_ID_ENV, raising=False)
    monkeypatch.setattr(snapshot.shutil, "which", lambda binary: "/usr/local/bin/aws" if binary == "aws" else None)
    monkeypatch.setattr(snapshot, "run_aws", fake_aws)
    monkeypatch.setattr(snapshot.subprocess, "run", lambda command, check: wait_calls.append(command))
    monkeypatch.setattr(sys, "argv", [
        "aws_rds_backup_snapshot_acceptance.py",
        "--environment", "staging",
        "--release-id", "git-abc123",
        "--region", "ap-southeast-1",
        "--execute",
        "--output-dir", str(tmp_path),
    ])

    assert snapshot.main() == 0
    evidence_path = next(tmp_path.glob("aws-rds-backup-snapshot-*.json"))
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    serialized = json.dumps(evidence)

    assert [call[1] for call in provider_calls] == ["describe-db-instances", "create-db-snapshot", "describe-db-snapshots"]
    assert wait_calls and "db-snapshot-available" in wait_calls[0]
    assert evidence["status"] == "passed"
    assert evidence["provider_api_verified"] is True
    assert evidence["source_instance_verified"] is True
    assert evidence["snapshot_retained"] is True
    assert evidence_path.stat().st_mode & 0o777 == 0o600
    assert instance_id not in serialized
    assert "arn:aws" not in serialized
    assert "user:redacted" not in serialized
