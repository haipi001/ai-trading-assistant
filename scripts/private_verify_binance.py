#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from datetime import timezone
from pathlib import Path
from urllib.request import Request
from urllib.request import urlopen


SENSITIVE_KEYS = {"api_key", "api_secret", "secret", "token", "authorization", "signature"}


def redact(value):
    if isinstance(value, dict):
        return {key: "[REDACTED]" if key.lower() in SENSITIVE_KEYS else redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description="Run private Binance Spot read-only verification and save a redacted evidence packet.")
    parser.add_argument("--api-base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--user-id", default="default-user")
    parser.add_argument("--permission-proof-ref", required=True)
    parser.add_argument("--withdrawal-disabled-proof-ref", required=True)
    parser.add_argument("--output-dir", default="private-evidence/binance-readonly")
    args = parser.parse_args()

    payload = {
        "permission_screenshot_ref": args.permission_proof_ref,
        "withdrawal_disabled_proof_ref": args.withdrawal_disabled_proof_ref,
        "verification_environment": "private",
    }
    request = Request(
        f"{args.api_base_url.rstrip('/')}/phase-development/real-readonly-data-proof/binance-private-verify?user_id={args.user_id}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=60) as response:
            packet = json.loads(response.read().decode())
    except Exception as exc:
        raise SystemExit(f"private verification request failed: {exc}") from exc

    safe_packet = redact(packet)
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    output_path = output_dir / f"binance-readonly-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    output_path.write_text(json.dumps(safe_packet, indent=2, ensure_ascii=True), encoding="utf-8")
    os.chmod(output_path, 0o600)
    print(json.dumps({"status": packet.get("status"), "evidence_path": str(output_path), "audit_packet_artifact_id": packet.get("audit_packet_artifact_id")}))
    return 0 if packet.get("status") == "verified_private_readonly" else 2


if __name__ == "__main__":
    raise SystemExit(main())
