#!/usr/bin/env python3
"""Run a non-destructive PostgreSQL dump/restore drill into an isolated database.

The source database is never modified. The restored database and temporary dump
are removed after verification. This proves logical restore mechanics, not the
cloud provider's off-site backup encryption or retention controls; those remain
separate external evidence requirements.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse, urlunparse

import psycopg
from psycopg import sql


ROOT = Path(__file__).resolve().parents[1]
LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "postgres"}


class DrillError(RuntimeError):
    pass


def normalize_database_url(value: str) -> str:
    return value.replace("postgresql+psycopg://", "postgresql://", 1)


def validate_target(database_url: str, environment: str) -> list[str]:
    parsed = urlparse(normalize_database_url(database_url))
    errors: list[str] = []
    if parsed.scheme != "postgresql" or not parsed.hostname or not parsed.path.strip("/"):
        errors.append("database URL must identify a PostgreSQL host and database")
        return errors
    if environment == "production":
        if parsed.hostname in LOCAL_HOSTS:
            errors.append("production restore drill cannot target a local/container host")
        sslmode = parse_qs(parsed.query).get("sslmode", [""])[0]
        if sslmode not in {"require", "verify-ca", "verify-full"}:
            errors.append("production PostgreSQL must require TLS")
    return errors


def connection_parts(database_url: str) -> dict[str, str | int | None]:
    parsed = urlparse(normalize_database_url(database_url))
    return {
        "host": parsed.hostname,
        "port": parsed.port or 5432,
        "user": unquote(parsed.username or ""),
        "password": unquote(parsed.password or ""),
        "database": unquote(parsed.path.lstrip("/")),
    }


def with_database(database_url: str, database: str) -> str:
    parsed = urlparse(normalize_database_url(database_url))
    return urlunparse(parsed._replace(path=f"/{database}"))


def tool_environment(parts: dict[str, str | int | None]) -> dict[str, str]:
    env = dict(os.environ)
    if parts["password"]:
        env["PGPASSWORD"] = str(parts["password"])
    return env


def tool_connection_args(parts: dict[str, str | int | None], database: str) -> list[str]:
    return [
        "--host", str(parts["host"]),
        "--port", str(parts["port"]),
        "--username", str(parts["user"]),
        "--dbname", database,
    ]


def query_manifest(connection: psycopg.Connection) -> dict:
    with connection.cursor() as cursor:
        cursor.execute("SELECT version_num FROM alembic_version")
        version = cursor.fetchone()[0]
        cursor.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename")
        tables = [row[0] for row in cursor.fetchall()]
        counts: dict[str, int] = {}
        for table in tables:
            cursor.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table)))
            counts[table] = int(cursor.fetchone()[0])
    return {"alembic_version": version, "tables": tables, "row_counts": counts}


def fingerprint(parts: dict[str, str | int | None]) -> str:
    raw = f"{parts['host']}:{parts['port']}/{parts['database']}".encode()
    return hashlib.sha256(raw).hexdigest()[:16]


def save_evidence(output_dir: Path, payload: dict) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = output_dir / f"postgres-restore-drill-{stamp}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", choices=("staging", "production"), required=True)
    parser.add_argument("--database-url-env", default="MANAGED_DATABASE_URL")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--backup-encryption-proof-ref", required=True)
    parser.add_argument("--retention-policy-ref", required=True)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "private-evidence" / "postgres-restore-drills")
    args = parser.parse_args()

    database_url = os.getenv(args.database_url_env, "").strip()
    if not database_url:
        raise DrillError(f"missing {args.database_url_env}")
    errors = validate_target(database_url, args.environment)
    if errors:
        raise DrillError("; ".join(errors))
    for binary in ("pg_dump", "pg_restore"):
        if shutil.which(binary) is None:
            raise DrillError(f"missing required binary: {binary}")

    parts = connection_parts(database_url)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    restore_database = f"atos_restore_{stamp}_{os.getpid()}"
    base_evidence = {
        "environment": args.environment,
        "source_database_fingerprint": fingerprint(parts),
        "backup_encryption_proof_ref": args.backup_encryption_proof_ref,
        "retention_policy_ref": args.retention_policy_ref,
        "contains_credentials": False,
        "source_database_modified": False,
        "isolated_restore_database": True,
        "temporary_dump_destroyed": True,
        "restore_database_destroyed": True,
        "provider_backup_encryption_verified": False,
        "offsite_disaster_recovery_verified": False,
        "production_execution_enabled": False,
    }
    if not args.execute:
        output = save_evidence(args.output_dir, {**base_evidence, "status": "dry_run_valid", "restore_performed": False})
        print(json.dumps({"status": "dry_run_valid", "evidence": str(output)}))
        return 0

    source_dsn = normalize_database_url(database_url)
    maintenance_dsn = with_database(source_dsn, "postgres")
    tool_env = tool_environment(parts)
    source_manifest: dict | None = None
    restored_manifest: dict | None = None
    restore_created = False
    with tempfile.TemporaryDirectory(prefix="atos-postgres-restore-") as temporary:
        dump_path = Path(temporary) / "backup.dump"
        try:
            subprocess.run(
                ["pg_dump", *tool_connection_args(parts, str(parts["database"])), "--format=custom", "--no-owner", "--no-acl", "--file", str(dump_path)],
                env=tool_env, check=True,
            )
            with psycopg.connect(source_dsn) as source:
                source_manifest = query_manifest(source)
            with psycopg.connect(maintenance_dsn, autocommit=True) as maintenance:
                maintenance.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(restore_database)))
                restore_created = True
            subprocess.run(
                ["pg_restore", *tool_connection_args(parts, restore_database), "--no-owner", "--no-acl", "--exit-on-error", str(dump_path)],
                env=tool_env, check=True,
            )
            restore_dsn = with_database(source_dsn, restore_database)
            with psycopg.connect(restore_dsn) as restored:
                restored_manifest = query_manifest(restored)
        finally:
            if restore_created:
                with psycopg.connect(maintenance_dsn, autocommit=True) as maintenance:
                    maintenance.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(restore_database)))

    schema_match = bool(source_manifest and restored_manifest and source_manifest["alembic_version"] == restored_manifest["alembic_version"] and source_manifest["tables"] == restored_manifest["tables"])
    counts_match = bool(source_manifest and restored_manifest and source_manifest["row_counts"] == restored_manifest["row_counts"])
    status = "passed" if schema_match and counts_match else "failed"
    evidence = {
        **base_evidence,
        "status": status,
        "restore_performed": True,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "schema_match": schema_match,
        "row_counts_match": counts_match,
        "alembic_version": restored_manifest["alembic_version"] if restored_manifest else None,
        "table_count": len(restored_manifest["tables"]) if restored_manifest else 0,
    }
    output = save_evidence(args.output_dir, evidence)
    print(json.dumps({"status": status, "evidence": str(output)}))
    return 0 if status == "passed" else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (DrillError, psycopg.Error, subprocess.CalledProcessError) as exc:
        print(json.dumps({"status": "blocked", "error_class": exc.__class__.__name__}))
        raise SystemExit(2)
