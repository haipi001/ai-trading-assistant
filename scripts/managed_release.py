#!/usr/bin/env python3
"""Validate and deploy an immutable managed release with redacted evidence.

The default is a dry run. External deployment and database migration require
an explicit --execute flag. Database migrations are forward-only; rollback
switches application images and never performs an automatic Alembic downgrade.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import subprocess
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
MANAGED_COMPOSE = ROOT / "infra" / "compose.managed.yml"
OVERLAYS = {
    "staging": ROOT / "infra" / "compose.staging.yml",
    "production": ROOT / "infra" / "compose.production.yml",
}
SECRET_REF_PREFIXES = ("aws-sm://", "gcp-sm://", "vault://")
REQUIRED = {
    "COMPOSE_PROJECT_NAME",
    "BACKEND_IMAGE",
    "FRONTEND_IMAGE",
    "SERVICE_NAME",
    "RELEASE_ID",
    "DATABASE_URL",
    "REDIS_URL",
    "BACKEND_CORS_ORIGINS",
    "OIDC_ISSUER",
    "OIDC_USERINFO_URL",
    "OIDC_CLIENT_ID",
    "AUTH_SESSION_SECRET_REF",
    "LEGACY_TENANT_USER_ID",
    "ERROR_REPORTING_ENABLED",
    "NOTIFICATION_WEBHOOK_ALLOWED_HOSTS",
}


class ReleaseError(RuntimeError):
    pass


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ReleaseError(f"invalid env line: {raw_line!r}")
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _immutable_image(value: str) -> bool:
    if "@sha256:" in value:
        return True
    tail = value.rsplit("/", 1)[-1]
    return ":" in tail and not tail.endswith(":latest")


def validate_release_environment(values: dict[str, str], environment: str) -> list[str]:
    errors = [f"missing {key}" for key in sorted(REQUIRED) if not values.get(key)]
    if errors:
        return errors

    for key in ("BACKEND_IMAGE", "FRONTEND_IMAGE"):
        if not _immutable_image(values[key]):
            errors.append(f"{key} must use an immutable tag or digest")

    database = values["DATABASE_URL"]
    if not database.startswith(("postgresql://", "postgresql+psycopg://")):
        errors.append("DATABASE_URL must be PostgreSQL")
    if values["LEGACY_TENANT_USER_ID"] == "default-user":
        errors.append("LEGACY_TENANT_USER_ID must be the exact existing owner OIDC subject")

    for key in ("OIDC_ISSUER", "OIDC_USERINFO_URL"):
        parsed = urlparse(values[key])
        if parsed.scheme != "https" or not parsed.netloc:
            errors.append(f"{key} must be an absolute HTTPS URL")

    if environment == "production":
        if values.get("STAGING_FAULT_INJECTION_ENABLED", "false").lower() != "false":
            errors.append("production STAGING_FAULT_INJECTION_ENABLED must be false")
        if values["ERROR_REPORTING_ENABLED"].lower() != "true":
            errors.append("production ERROR_REPORTING_ENABLED must be true")
        if not values["REDIS_URL"].startswith("rediss://"):
            errors.append("production REDIS_URL must use TLS (rediss://)")
        if not values["AUTH_SESSION_SECRET_REF"].startswith(SECRET_REF_PREFIXES):
            errors.append("production AUTH_SESSION_SECRET_REF must use a cloud/Vault secret reference")
        forbidden_hosts = {"localhost", "127.0.0.1", "0.0.0.0", "postgres", "redis"}
        for key in ("DATABASE_URL", "REDIS_URL", "OIDC_ISSUER", "OIDC_USERINFO_URL"):
            host = urlparse(values[key].replace("postgresql+psycopg://", "postgresql://", 1)).hostname
            if host in forbidden_hosts:
                errors.append(f"production {key} cannot target a local/container hostname")
        if any(origin.startswith("http://") for origin in values["BACKEND_CORS_ORIGINS"].split(",")):
            errors.append("production CORS origins must use HTTPS")
    return errors


def redact(values: dict[str, str]) -> dict[str, str | bool]:
    return {
        "compose_project_name": values.get("COMPOSE_PROJECT_NAME", ""),
        "backend_image": values.get("BACKEND_IMAGE", ""),
        "frontend_image": values.get("FRONTEND_IMAGE", ""),
        "service_name": values.get("SERVICE_NAME", ""),
        "release_id": values.get("RELEASE_ID", ""),
        "database_scheme": urlparse(values.get("DATABASE_URL", "").replace("postgresql+psycopg://", "postgresql://", 1)).scheme,
        "redis_tls": values.get("REDIS_URL", "").startswith("rediss://"),
        "oidc_issuer_host": urlparse(values.get("OIDC_ISSUER", "")).hostname or "",
        "secret_reference_scheme": values.get("AUTH_SESSION_SECRET_REF", "").split("://", 1)[0],
        "contains_credentials": False,
    }


def database_fingerprint(database_url: str) -> str:
    parsed = urlparse(database_url.replace("postgresql+psycopg://", "postgresql://", 1))
    raw = f"{parsed.hostname}:{parsed.port or 5432}/{parsed.path.lstrip('/')}".encode()
    return hashlib.sha256(raw).hexdigest()[:16]


def validate_restore_drill_evidence(
    path: Path,
    *,
    environment: str,
    database_url: str,
    maximum_age_hours: int,
    now: datetime | None = None,
) -> dict[str, str | int | bool]:
    if maximum_age_hours < 1 or maximum_age_hours > 720:
        raise ReleaseError("restore drill maximum age must be between 1 and 720 hours")
    if not path.is_file():
        raise ReleaseError("managed PostgreSQL restore drill evidence file is missing")
    if path.stat().st_mode & 0o077:
        raise ReleaseError("restore drill evidence must not be group/world accessible")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseError("restore drill evidence is unreadable") from exc
    if not isinstance(payload, dict):
        raise ReleaseError("restore drill evidence must be an object")

    required_true = (
        "restore_performed",
        "isolated_restore_database",
        "temporary_dump_destroyed",
        "restore_database_destroyed",
        "schema_match",
        "row_counts_match",
    )
    errors = []
    if payload.get("status") != "passed":
        errors.append("restore drill status must be passed")
    if payload.get("environment") != environment:
        errors.append("restore drill environment does not match release")
    if payload.get("source_database_fingerprint") != database_fingerprint(database_url):
        errors.append("restore drill database fingerprint does not match release target")
    if payload.get("contains_credentials") is not False:
        errors.append("restore drill evidence must explicitly exclude credentials")
    if payload.get("source_database_modified") is not False:
        errors.append("restore drill must explicitly preserve the source database")
    for field in required_true:
        if payload.get(field) is not True:
            errors.append(f"restore drill evidence requires {field}=true")

    completed_raw = str(payload.get("completed_at") or "")
    try:
        completed_at = datetime.fromisoformat(completed_raw.replace("Z", "+00:00"))
        if completed_at.tzinfo is None:
            raise ValueError("timezone required")
    except ValueError:
        errors.append("restore drill completed_at must be a timezone-aware timestamp")
        completed_at = None
    observed_now = now or datetime.now(timezone.utc)
    age_hours = None
    if completed_at is not None:
        age_hours = (observed_now - completed_at.astimezone(timezone.utc)).total_seconds() / 3600
        if age_hours < 0:
            errors.append("restore drill completed_at cannot be in the future")
        elif age_hours > maximum_age_hours:
            errors.append("restore drill evidence is too old")
    if errors:
        raise ReleaseError("; ".join(errors))

    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {
        "status": "verified",
        "environment": environment,
        "database_fingerprint": database_fingerprint(database_url),
        "completed_at": completed_at.astimezone(timezone.utc).isoformat() if completed_at else "",
        "age_hours": round(float(age_hours or 0), 2),
        "maximum_age_hours": maximum_age_hours,
        "evidence_sha256": digest,
        "real_restore_performed": True,
        "contains_credentials": False,
    }


def validate_backup_snapshot_evidence(
    path: Path,
    *,
    environment: str,
    database_url: str,
    release_id: str,
    maximum_age_hours: int,
    now: datetime | None = None,
) -> dict[str, str | int | bool]:
    if maximum_age_hours < 1 or maximum_age_hours > 24:
        raise ReleaseError("backup snapshot maximum age must be between 1 and 24 hours")
    if not path.is_file():
        raise ReleaseError("AWS RDS backup snapshot evidence file is missing")
    if path.stat().st_mode & 0o077:
        raise ReleaseError("backup snapshot evidence must not be group/world accessible")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseError("backup snapshot evidence is unreadable") from exc
    if not isinstance(payload, dict):
        raise ReleaseError("backup snapshot evidence must be an object")

    errors = []
    if payload.get("status") != "passed":
        errors.append("backup snapshot status must be passed")
    if payload.get("provider") != "aws_rds":
        errors.append("backup snapshot provider must be aws_rds")
    if payload.get("environment") != environment:
        errors.append("backup snapshot environment does not match release")
    if payload.get("release_id") != release_id:
        errors.append("backup snapshot release id does not match target")
    if payload.get("source_database_fingerprint") != database_fingerprint(database_url):
        errors.append("backup snapshot database fingerprint does not match release target")
    if payload.get("contains_credentials") is not False:
        errors.append("backup snapshot evidence must explicitly exclude credentials")
    for field in (
        "provider_snapshot_created",
        "provider_api_verified",
        "real_provider_calls_performed",
        "snapshot_retained",
        "provider_snapshot_available",
        "provider_snapshot_encrypted",
        "kms_key_verified",
        "manual_snapshot_verified",
        "source_instance_verified",
        "source_instance_encrypted",
        "source_instance_kms_verified",
    ):
        if payload.get(field) is not True:
            errors.append(f"backup snapshot evidence requires {field}=true")
    if not payload.get("snapshot_reference_fingerprint"):
        errors.append("backup snapshot reference fingerprint is required")

    created_raw = str(payload.get("snapshot_created_at") or "")
    try:
        created_at = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
        if created_at.tzinfo is None:
            raise ValueError("timezone required")
    except ValueError:
        errors.append("backup snapshot created_at must be a timezone-aware timestamp")
        created_at = None
    observed_now = now or datetime.now(timezone.utc)
    age_hours = None
    if created_at is not None:
        age_hours = (observed_now - created_at.astimezone(timezone.utc)).total_seconds() / 3600
        if age_hours < 0:
            errors.append("backup snapshot created_at cannot be in the future")
        elif age_hours > maximum_age_hours:
            errors.append("backup snapshot evidence is too old")
    if errors:
        raise ReleaseError("; ".join(errors))

    return {
        "status": "verified",
        "provider": "aws_rds",
        "environment": environment,
        "database_fingerprint": database_fingerprint(database_url),
        "release_id": release_id,
        "snapshot_reference_fingerprint": str(payload["snapshot_reference_fingerprint"]),
        "snapshot_created_at": created_at.astimezone(timezone.utc).isoformat() if created_at else "",
        "age_hours": round(float(age_hours or 0), 2),
        "maximum_age_hours": maximum_age_hours,
        "evidence_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "real_provider_calls_performed": True,
        "snapshot_retained": True,
        "contains_credentials": False,
    }


def compose_command(environment: str, env_file: Path, *args: str) -> list[str]:
    return [
        "docker", "compose", "--env-file", str(env_file),
        "-f", str(MANAGED_COMPOSE), "-f", str(OVERLAYS[environment]), *args,
    ]


def run(command: list[str], *, env: dict[str, str]) -> None:
    subprocess.run(command, cwd=ROOT, env=env, check=True)


def wait_for_readiness(url: str, timeout_seconds: int, *, expected_release_id: str) -> dict:
    deadline = time.monotonic() + timeout_seconds
    last_error = "readiness timeout"
    while time.monotonic() < deadline:
        try:
            request = Request(url, headers={"Accept": "application/json"})
            with urlopen(request, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
                if response.status == 200 and payload.get("status") == "ready" and payload.get("release_id") == expected_release_id:
                    return payload
                last_error = "unexpected readiness status or release id"
        except (OSError, URLError, ValueError, json.JSONDecodeError) as exc:
            last_error = exc.__class__.__name__
        time.sleep(2)
    raise ReleaseError(last_error)


def save_evidence(output_dir: Path, payload: dict) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = output_dir / f"managed-release-{stamp}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)
    return path


def load_release_state(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseError("release state is unreadable") from exc
    if not isinstance(value, dict):
        raise ReleaseError("release state must be an object")
    return value


def save_release_state(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(path)
    path.chmod(0o600)


def release_descriptor(values: dict[str, str]) -> dict[str, str]:
    return {
        "backend_image": values["BACKEND_IMAGE"],
        "frontend_image": values["FRONTEND_IMAGE"],
        "release_id": values["RELEASE_ID"],
    }


def environment_for_release(base: dict[str, str], release: dict[str, str]) -> dict[str, str]:
    return {
        **base,
        "BACKEND_IMAGE": release["backend_image"],
        "FRONTEND_IMAGE": release["frontend_image"],
        "RELEASE_ID": release["release_id"],
    }


@contextmanager
def deployment_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ReleaseError("another managed release holds the deployment lock") from exc
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def release_commands(environment: str, env_file: Path, *, include_migration: bool) -> list[list[str]]:
    commands = [compose_command(environment, env_file, "pull", "backend", "frontend")]
    if include_migration:
        commands.append(compose_command(environment, env_file, "run", "--rm", "migrate"))
        commands.append(compose_command(environment, env_file, "run", "--rm", "migrate", "alembic", "current", "--check-heads"))
        commands.append(compose_command(environment, env_file, "run", "--rm", "migrate", "alembic", "check"))
    commands.append(compose_command(environment, env_file, "up", "-d", "--no-deps", "backend", "frontend"))
    return commands


def perform_release(
    *,
    environment: str,
    env_file: Path,
    action: str,
    target: dict[str, str],
    rollback_target: dict[str, str] | None,
    process_env: dict[str, str],
    readiness_url: str,
    readiness_timeout_seconds: int,
) -> dict:
    commands = release_commands(environment, env_file, include_migration=action == "deploy")
    evidence = {
        "target_release": target,
        "rollback_target": rollback_target,
        "target_readiness_verified": False,
        "automatic_rollback_attempted": False,
        "rollback_readiness_verified": False,
        "database_migration_attempted": False,
        "database_head_verified": False,
        "database_schema_drift_verified": False,
        "database_downgrade_performed": False,
        "production_execution_enabled": False,
        "outcome": "started",
    }
    target_env = environment_for_release(process_env, target)
    stage = "pull"
    try:
        run(commands[0], env=target_env)
        if action == "deploy":
            stage = "migration"
            evidence["database_migration_attempted"] = True
            run(commands[1], env=target_env)
            stage = "migration_head_verification"
            run(commands[2], env=target_env)
            evidence["database_head_verified"] = True
            stage = "schema_drift_verification"
            run(commands[3], env=target_env)
            evidence["database_schema_drift_verified"] = True
        stage = "replace_application"
        run(commands[-1], env=target_env)
        stage = "readiness"
        readiness = wait_for_readiness(readiness_url, readiness_timeout_seconds, expected_release_id=target["release_id"])
        evidence.update(
            target_readiness_verified=True,
            target_readiness_status=readiness.get("status"),
            observed_release_id=readiness.get("release_id"),
            outcome="deployed" if action == "deploy" else "rolled_back",
            exit_code=0,
        )
        return evidence
    except (ReleaseError, subprocess.CalledProcessError) as exc:
        evidence.update(failed_stage=stage, failure_error_class=exc.__class__.__name__)
        application_may_have_changed = stage in {"replace_application", "readiness"}
        if not application_may_have_changed:
            evidence.update(outcome="failed_without_application_change", exit_code=2)
            return evidence
        if rollback_target is None:
            evidence.update(outcome="failed_no_rollback_target", exit_code=2)
            return evidence

    evidence["automatic_rollback_attempted"] = True
    rollback_env = environment_for_release(process_env, rollback_target)
    rollback_commands = release_commands(environment, env_file, include_migration=False)
    try:
        run(rollback_commands[0], env=rollback_env)
        run(rollback_commands[-1], env=rollback_env)
        readiness = wait_for_readiness(readiness_url, readiness_timeout_seconds, expected_release_id=rollback_target["release_id"])
        evidence.update(
            rollback_readiness_verified=True,
            rollback_readiness_status=readiness.get("status"),
            observed_rollback_release_id=readiness.get("release_id"),
            outcome="automatically_rolled_back_after_failed_release",
            exit_code=2,
        )
    except (ReleaseError, subprocess.CalledProcessError) as rollback_exc:
        evidence.update(
            rollback_failure_error_class=rollback_exc.__class__.__name__,
            outcome="automatic_rollback_failed",
            exit_code=3,
        )
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", choices=sorted(OVERLAYS), required=True)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--action", choices=("deploy", "rollback"), default="deploy")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--readiness-url", default="http://127.0.0.1:8000/health/ready")
    parser.add_argument("--readiness-timeout-seconds", type=int, default=180)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "private-evidence" / "managed-releases")
    parser.add_argument("--state-file", type=Path)
    parser.add_argument("--lock-file", type=Path)
    parser.add_argument("--allow-first-deploy-without-rollback", action="store_true")
    parser.add_argument("--restore-drill-evidence", type=Path)
    parser.add_argument("--restore-drill-maximum-age-hours", type=int, default=720)
    parser.add_argument("--backup-snapshot-evidence", type=Path)
    parser.add_argument("--backup-snapshot-maximum-age-hours", type=int, default=4)
    args = parser.parse_args()

    values = {**os.environ, **load_env_file(args.env_file)}
    values["ENVIRONMENT"] = args.environment
    values["DEPLOYMENT_TARGET"] = f"managed-{args.environment}"
    errors = validate_release_environment(values, args.environment)
    if errors:
        raise ReleaseError("; ".join(errors))

    restore_drill = None
    backup_snapshot = None
    if args.execute and args.action == "deploy":
        if args.restore_drill_evidence is None:
            raise ReleaseError("executed deploy requires --restore-drill-evidence")
        restore_drill = validate_restore_drill_evidence(
            args.restore_drill_evidence,
            environment=args.environment,
            database_url=values["DATABASE_URL"],
            maximum_age_hours=args.restore_drill_maximum_age_hours,
        )
        if args.backup_snapshot_evidence is None:
            raise ReleaseError("executed deploy requires --backup-snapshot-evidence")
        backup_snapshot = validate_backup_snapshot_evidence(
            args.backup_snapshot_evidence,
            environment=args.environment,
            database_url=values["DATABASE_URL"],
            release_id=values["RELEASE_ID"],
            maximum_age_hours=args.backup_snapshot_maximum_age_hours,
        )

    state_file = args.state_file or args.output_dir / f"release-state-{args.environment}.json"
    lock_file = args.lock_file or args.output_dir / f"release-{args.environment}.lock"
    state = load_release_state(state_file)
    configured_target = release_descriptor(values)
    if args.action == "rollback":
        target = state.get("previous")
        rollback_target = state.get("current")
        if not isinstance(target, dict):
            raise ReleaseError("no previous successful release is available for rollback")
    else:
        target = configured_target
        rollback_target = state.get("current") if isinstance(state.get("current"), dict) else None
        if args.execute and rollback_target is None and not args.allow_first_deploy_without_rollback:
            raise ReleaseError("first deploy has no rollback target; pass --allow-first-deploy-without-rollback explicitly")

    process_env = {**os.environ, **values}
    target_env = environment_for_release(process_env, target)
    run(compose_command(args.environment, args.env_file, "config", "--quiet"), env=target_env)
    commands = release_commands(args.environment, args.env_file, include_migration=args.action == "deploy")

    evidence = {
        "environment": args.environment,
        "action": args.action,
        "mode": "executed" if args.execute else "dry_run",
        "validated_at": datetime.now(timezone.utc).isoformat(),
        "release": {**redact(values), **target},
        "rollback_target": rollback_target,
        "database_downgrade_performed": False,
        "production_execution_enabled": False,
        "commands_planned": [[re.sub(r"[^/]+$", "<env-file>", part) if part == str(args.env_file) else part for part in command] for command in commands],
        "readiness_verified": False,
        "restore_drill_gate": restore_drill or {
            "status": "not_verified_in_dry_run",
            "real_restore_performed": False,
            "contains_credentials": False,
        },
        "backup_snapshot_gate": backup_snapshot or {
            "status": "not_verified_in_dry_run",
            "real_provider_calls_performed": False,
            "snapshot_retained": False,
            "contains_credentials": False,
        },
    }
    result = {"outcome": "dry_run_valid", "exit_code": 0}
    if args.execute:
        with deployment_lock(lock_file):
            result = perform_release(
                environment=args.environment,
                env_file=args.env_file,
                action=args.action,
                target=target,
                rollback_target=rollback_target,
                process_env=process_env,
                readiness_url=args.readiness_url,
                readiness_timeout_seconds=args.readiness_timeout_seconds,
            )
            if result["exit_code"] == 0:
                save_release_state(state_file, {
                    "environment": args.environment,
                    "current": target,
                    "previous": rollback_target,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "contains_credentials": False,
                })
    evidence.update(result)
    evidence["readiness_verified"] = bool(result.get("target_readiness_verified"))

    output = save_evidence(args.output_dir, evidence)
    print(json.dumps({"status": result["outcome"], "evidence": str(output)}))
    return int(result["exit_code"])


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ReleaseError, subprocess.CalledProcessError) as exc:
        print(json.dumps({"status": "blocked", "error_class": exc.__class__.__name__}))
        raise SystemExit(2)
