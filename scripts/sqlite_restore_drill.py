#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sqlite3
from datetime import datetime
from datetime import timezone
from pathlib import Path


CORE_TABLES = ("audit_logs", "data_snapshots", "investment_ledger_entries", "order_drafts", "user_accounts")


def table_count(connection: sqlite3.Connection, table: str) -> int | None:
    exists = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    return int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]) if exists else None


def main() -> int:
    parser = argparse.ArgumentParser(description="Perform an isolated SQLite backup/restore drill and save evidence.")
    parser.add_argument("--source", default="backend/data/ai_trading_os.db")
    parser.add_argument("--output-dir", default="private-evidence/restore-drills")
    args = parser.parse_args()

    source = Path(args.source).expanduser().resolve()
    if not source.exists():
        raise SystemExit(f"source database not found: {source}")
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = output_dir / f"backup-{stamp}.sqlite3"
    restored = output_dir / f"restored-{stamp}.sqlite3"

    with sqlite3.connect(source) as src, sqlite3.connect(backup) as dst:
        src.backup(dst)
    with sqlite3.connect(backup) as src, sqlite3.connect(restored) as dst:
        src.backup(dst)

    with sqlite3.connect(source) as original, sqlite3.connect(restored) as recovery:
        integrity = recovery.execute("PRAGMA integrity_check").fetchone()[0]
        original_counts = {table: table_count(original, table) for table in CORE_TABLES}
        restored_counts = {table: table_count(recovery, table) for table in CORE_TABLES}
    counts_match = original_counts == restored_counts
    evidence = {
        "status": "passed" if integrity == "ok" and counts_match else "failed",
        "source_path": str(source),
        "backup_path": str(backup),
        "restored_path": str(restored),
        "integrity_check": integrity,
        "original_counts": original_counts,
        "restored_counts": restored_counts,
        "counts_match": counts_match,
        "executed_at": stamp,
        "production_restore_performed": False,
    }
    evidence_path = output_dir / f"restore-drill-{stamp}.json"
    evidence_path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    for path in (backup, restored, evidence_path):
        os.chmod(path, 0o600)
    print(json.dumps({"status": evidence["status"], "evidence_path": str(evidence_path)}))
    return 0 if evidence["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
