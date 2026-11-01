#!/usr/bin/env python3
"""Download a redacted eight-stage acceptance report from a private deployment."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from datetime import timezone
from pathlib import Path
from urllib.request import Request
from urllib.request import urlopen


def main() -> int:
    parser = argparse.ArgumentParser(description="Save the evidence-driven production acceptance report.")
    parser.add_argument("--api-base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--session-token-env", default="ATOS_SESSION_TOKEN")
    parser.add_argument("--output-dir", default="private-evidence/production-acceptance")
    args = parser.parse_args()

    headers = {"Accept": "application/json"}
    token = os.getenv(args.session_token_env, "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(f"{args.api_base_url.rstrip('/')}/production/acceptance", headers=headers)
    with urlopen(request, timeout=30) as response:
        report = json.loads(response.read().decode("utf-8"))

    report["retrieved_at"] = datetime.now(timezone.utc).isoformat()
    report["source"] = args.api_base_url
    report["contains_credentials"] = False
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"acceptance-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    output_path.chmod(0o600)
    print(json.dumps({"status": report.get("status"), "progress": report.get("overall_progress_pct"), "output": str(output_path)}))
    return 0 if report.get("human_small_pilot_review_allowed") else 2


if __name__ == "__main__":
    raise SystemExit(main())
