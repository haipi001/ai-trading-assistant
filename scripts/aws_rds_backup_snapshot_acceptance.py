#!/usr/bin/env python3
"""Create and verify a retained encrypted AWS RDS manual snapshot.

The managed database URL and RDS instance id are read from environment. AWS
credentials remain inside the AWS CLI credential chain. Evidence contains only
hashes and non-secret verification facts; the snapshot itself is retained.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
DATABASE_URL_ENV = "MANAGED_DATABASE_URL"
INSTANCE_ID_ENV = "ATOS_RDS_INSTANCE_ID"
SNAPSHOT_ID_ENV = "ATOS_RDS_SNAPSHOT_ID"


class SnapshotError(RuntimeError):
    pass


def database_fingerprint(database_url: str) -> str:
    parsed = urlparse(database_url.replace("postgresql+psycopg://", "postgresql://", 1))
    if parsed.scheme != "postgresql" or not parsed.hostname or not parsed.path.strip("/"):
        raise SnapshotError("managed database URL must identify PostgreSQL")
    raw = f"{parsed.hostname}:{parsed.port or 5432}/{parsed.path.lstrip('/')}".encode()
    return hashlib.sha256(raw).hexdigest()[:16]


def reference_fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:16]


def safe_snapshot_id(release_id: str, now: datetime) -> str:
    release = re.sub(r"[^a-z0-9-]+", "-", release_id.lower()).strip("-")[:24] or "release"
    return f"atos-{release}-{now.strftime('%Y%m%d%H%M%S')}"[:63].rstrip("-")


def validate_inputs(*, environment: str, database_url: str, instance_id: str, snapshot_id: str) -> list[str]:
    errors: list[str] = []
    try:
        parsed = urlparse(database_url.replace("postgresql+psycopg://", "postgresql://", 1))
        database_fingerprint(database_url)
    except SnapshotError as exc:
        errors.append(str(exc))
        parsed = urlparse("")
    if environment == "production":
        if parsed.hostname in {"localhost", "127.0.0.1", "0.0.0.0", "postgres"}:
            errors.append("production snapshot cannot target a local/container database")
        if "sslmode=require" not in parsed.query and "sslmode=verify-" not in parsed.query:
            errors.append("production database must require TLS")
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9-]{0,62}", instance_id):
        errors.append("ATOS_RDS_INSTANCE_ID is invalid")
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,62}", snapshot_id) or snapshot_id.endswith("-") or "--" in snapshot_id:
        errors.append("RDS snapshot id is invalid")
    return errors


def run_aws(arguments: list[str]) -> dict:
    result = subprocess.run(
        ["aws", *arguments, "--output", "json", "--no-cli-pager"],
        check=True,
        capture_output=True,
        text=True,
    )
    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise SnapshotError("AWS CLI returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise SnapshotError("AWS CLI response must be an object")
    return payload


def verify_instance(payload: dict, *, database_url: str, instance_id: str) -> dict:
    instances = payload.get("DBInstances")
    if not isinstance(instances, list) or len(instances) != 1 or not isinstance(instances[0], dict):
        raise SnapshotError("AWS describe must return exactly one RDS instance")
    instance = instances[0]
    endpoint = instance.get("Endpoint") if isinstance(instance.get("Endpoint"), dict) else {}
    expected_host = urlparse(database_url.replace("postgresql+psycopg://", "postgresql://", 1)).hostname
    errors = []
    if instance.get("DBInstanceIdentifier") != instance_id:
        errors.append("RDS instance identifier mismatch")
    if instance.get("Engine") != "postgres":
        errors.append("RDS instance engine must be PostgreSQL")
    if endpoint.get("Address") != expected_host:
        errors.append("RDS instance endpoint does not match managed database URL")
    if instance.get("StorageEncrypted") is not True:
        errors.append("RDS instance storage must be encrypted")
    if not instance.get("KmsKeyId"):
        errors.append("RDS instance must report a KMS key")
    if errors:
        raise SnapshotError("; ".join(errors))
    return {
        "source_instance_verified": True,
        "source_instance_encrypted": True,
        "source_instance_kms_verified": True,
        "source_endpoint_fingerprint": reference_fingerprint(str(expected_host)),
    }


def verify_snapshot(payload: dict, *, instance_id: str, snapshot_id: str, now: datetime) -> dict:
    snapshots = payload.get("DBSnapshots")
    if not isinstance(snapshots, list) or len(snapshots) != 1 or not isinstance(snapshots[0], dict):
        raise SnapshotError("AWS describe must return exactly one RDS snapshot")
    snapshot = snapshots[0]
    errors = []
    if snapshot.get("DBSnapshotIdentifier") != snapshot_id:
        errors.append("snapshot identifier mismatch")
    if snapshot.get("DBInstanceIdentifier") != instance_id:
        errors.append("snapshot instance mismatch")
    if snapshot.get("Status") != "available":
        errors.append("snapshot is not available")
    if snapshot.get("SnapshotType") != "manual":
        errors.append("snapshot must be manual")
    if snapshot.get("Encrypted") is not True:
        errors.append("snapshot must be encrypted")
    if not snapshot.get("KmsKeyId"):
        errors.append("snapshot must report a KMS key")
    created_raw = str(snapshot.get("SnapshotCreateTime") or "")
    try:
        created_at = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
        if created_at.tzinfo is None:
            raise ValueError("timezone required")
    except ValueError:
        errors.append("snapshot create time is invalid")
        created_at = None
    age_minutes = None
    if created_at is not None:
        age_minutes = (now - created_at.astimezone(timezone.utc)).total_seconds() / 60
        if age_minutes < 0 or age_minutes > 60:
            errors.append("snapshot is not a newly created migration backup")
    if errors:
        raise SnapshotError("; ".join(errors))
    reference = str(snapshot.get("DBSnapshotArn") or snapshot_id)
    return {
        "snapshot_reference_fingerprint": reference_fingerprint(reference),
        "snapshot_created_at": created_at.astimezone(timezone.utc).isoformat() if created_at else "",
        "snapshot_age_minutes": round(float(age_minutes or 0), 2),
        "provider_snapshot_available": True,
        "provider_snapshot_encrypted": True,
        "kms_key_verified": True,
        "manual_snapshot_verified": True,
    }


def save_evidence(output_dir: Path, payload: dict) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = output_dir / f"aws-rds-backup-snapshot-{stamp}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", choices=("staging", "production"), required=True)
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--region")
    parser.add_argument("--profile")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "private-evidence" / "backup-snapshots")
    args = parser.parse_args()

    now = datetime.now(timezone.utc)
    database_url = os.getenv(DATABASE_URL_ENV, "").strip()
    instance_id = os.getenv(INSTANCE_ID_ENV, "").strip()
    snapshot_id = os.getenv(SNAPSHOT_ID_ENV, "").strip() or safe_snapshot_id(args.release_id, now)
    errors = validate_inputs(environment=args.environment, database_url=database_url, instance_id=instance_id, snapshot_id=snapshot_id)
    if errors:
        raise SnapshotError("; ".join(errors))
    if shutil.which("aws") is None:
        raise SnapshotError("AWS CLI is required")

    evidence = {
        "status": "dry_run_valid",
        "provider": "aws_rds",
        "environment": args.environment,
        "release_id": args.release_id,
        "source_database_fingerprint": database_fingerprint(database_url),
        "instance_fingerprint": reference_fingerprint(instance_id),
        "provider_snapshot_created": False,
        "provider_api_verified": False,
        "real_provider_calls_performed": False,
        "snapshot_retained": False,
        "contains_credentials": False,
        "production_execution_enabled": False,
        "generated_at": now.isoformat(),
    }
    if args.execute:
        common = []
        if args.region:
            common += ["--region", args.region]
        if args.profile:
            common += ["--profile", args.profile]
        instance = run_aws(["rds", "describe-db-instances", "--db-instance-identifier", instance_id, *common])
        evidence.update(verify_instance(instance, database_url=database_url, instance_id=instance_id))
        run_aws(["rds", "create-db-snapshot", "--db-instance-identifier", instance_id, "--db-snapshot-identifier", snapshot_id, *common])
        subprocess.run(
            ["aws", "rds", "wait", "db-snapshot-available", "--db-snapshot-identifier", snapshot_id, *common, "--no-cli-pager"],
            check=True,
        )
        described = run_aws(["rds", "describe-db-snapshots", "--db-snapshot-identifier", snapshot_id, *common])
        evidence.update(
            verify_snapshot(described, instance_id=instance_id, snapshot_id=snapshot_id, now=datetime.now(timezone.utc)),
            status="passed",
            provider_snapshot_created=True,
            provider_api_verified=True,
            real_provider_calls_performed=True,
            snapshot_retained=True,
            verified_at=datetime.now(timezone.utc).isoformat(),
        )
    output = save_evidence(args.output_dir, evidence)
    print(json.dumps({"status": evidence["status"], "evidence": str(output)}))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (SnapshotError, subprocess.CalledProcessError) as exc:
        print(json.dumps({"status": "blocked", "error_class": exc.__class__.__name__}))
        raise SystemExit(2)
