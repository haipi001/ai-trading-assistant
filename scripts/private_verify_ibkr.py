#!/usr/bin/env python3
"""Run a real IBKR Client Portal read-only sync and save redacted evidence.

The proof files stay local and are represented only by SHA-256 fingerprints.
The optional managed application session comes from ``ATOS_SESSION_TOKEN`` and
is never persisted. The default mode performs validation without an API call.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple
from urllib.error import HTTPError
from urllib.parse import urlencode, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


ROOT = Path(__file__).resolve().parents[1]
SESSION_ENV = "ATOS_SESSION_TOKEN"
PROOF_SUFFIXES = {".png", ".jpg", ".jpeg", ".pdf"}


class VerificationError(RuntimeError):
    pass


class Response(NamedTuple):
    status: int
    payload: object


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001, ANN201
        return None


class ApiClient:
    def __init__(self, base_url: str, session_token: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.session_token = session_token
        self.opener = build_opener(_NoRedirect())

    def verify(self, *, user_id: str, payload: dict) -> Response:
        query = urlencode({"user_id": user_id})
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if self.session_token:
            headers["Authorization"] = f"Bearer {self.session_token}"
        request = Request(
            f"{self.base_url}/phase-development/real-readonly-data-proof/ibkr-private-verify?{query}",
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with self.opener.open(request, timeout=90) as response:
                raw = response.read().decode("utf-8")
                return Response(response.status, json.loads(raw) if raw else {})
        except HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                payload_value = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                payload_value = {"error_class": "NonJsonErrorResponse"}
            return Response(exc.code, payload_value)


def validate_target(base_url: str) -> list[str]:
    parsed = urlparse(base_url)
    errors: list[str] = []
    if not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
        errors.append("API base URL must be credential-free and contain no query or fragment")
    hostname = (parsed.hostname or "").lower()
    loopback = hostname in {"localhost", "127.0.0.1", "::1"} or hostname.endswith(".localhost")
    if parsed.scheme != "https" and not (parsed.scheme == "http" and loopback):
        errors.append("API base URL must use HTTPS, except for a loopback private app")
    return errors


def proof_fingerprint(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise VerificationError("proof must be a regular non-symlink file")
    if path.suffix.lower() not in PROOF_SUFFIXES:
        raise VerificationError("proof must be PNG, JPEG, or PDF")
    size = path.stat().st_size
    if size < 32 or size > 20 * 1024 * 1024:
        raise VerificationError("proof file size must be between 32 bytes and 20 MiB")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fingerprint(value: object) -> str | None:
    text = str(value or "").strip()
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16] if text else None


def sanitize_verified_packet(response: Response, *, user_id: str, proof_hashes: dict[str, str]) -> dict:
    payload = response.payload if isinstance(response.payload, dict) else {}
    checks = payload.get("proof_checks") if isinstance(payload.get("proof_checks"), dict) else {}
    sync = payload.get("sync_result") if isinstance(payload.get("sync_result"), dict) else {}
    reconciliation = sync.get("reconciliation") if isinstance(sync.get("reconciliation"), dict) else {}
    expected_checks = {
        "gateway_session_proof_recorded",
        "read_only_boundary_proof_recorded",
        "snapshot_recorded",
        "quality_report_passed",
        "catalog_lineage_recorded",
        "ledger_sync_recorded",
        "reconciliation_passed",
        "orders_endpoint_not_used",
    }
    read_endpoints = payload.get("read_endpoints") if isinstance(payload.get("read_endpoints"), list) else []
    forbidden = payload.get("forbidden") if isinstance(payload.get("forbidden"), list) else []
    validations = {
        "api_response_successful": response.status == 200,
        "provider_verified": payload.get("provider") == "ibkr_readonly" and payload.get("status") == "verified_private_readonly",
        "all_required_proof_checks_passed": expected_checks.issubset(checks) and all(checks.get(key) is True for key in expected_checks),
        "authenticated_snapshot_chain_recorded": all(bool(sync.get(key)) for key in ("snapshot_id", "quality_report_id", "catalog_entry_id")),
        "quality_threshold_passed": float(sync.get("quality_score") or 0) >= 0.8,
        "ledger_reconciliation_passed": bool(sync.get("ledger_sync")) and reconciliation.get("status") == "ok" and bool(reconciliation.get("run_id")),
        "orders_endpoint_not_used": sync.get("orders_seen") == 0 and checks.get("orders_endpoint_not_used") is True,
        "read_endpoint_allowlist_exact": set(read_endpoints) == {
            "/portfolio/accounts",
            "/portfolio/{accountId}/positions/{pageId}",
            "/portfolio/{accountId}/ledger",
        },
        "execution_remained_disabled": payload.get("execution_available") is False and payload.get("production_capability") is False,
        "forbidden_capabilities_recorded": {"order_endpoint", "order_placement", "withdrawal", "production_trading"}.issubset(set(forbidden)),
        "audit_packet_recorded": bool(payload.get("audit_packet_artifact_id")),
    }
    passed = all(validations.values())
    return {
        "status": "passed" if passed else "failed",
        "passed": passed,
        "provider": "ibkr_readonly",
        "checks": [{"key": key, "status": "passed" if value else "failed"} for key, value in validations.items()],
        "user_fingerprint": _fingerprint(user_id),
        "connection_fingerprint": _fingerprint(payload.get("connection_id")),
        "snapshot_fingerprint": _fingerprint(sync.get("snapshot_id")),
        "quality_report_fingerprint": _fingerprint(sync.get("quality_report_id")),
        "catalog_entry_fingerprint": _fingerprint(sync.get("catalog_entry_id")),
        "reconciliation_run_fingerprint": _fingerprint(reconciliation.get("run_id")),
        "audit_packet_fingerprint": _fingerprint(payload.get("audit_packet_artifact_id")),
        "quality_score": sync.get("quality_score"),
        "positions_synced": sync.get("positions_synced"),
        "balances_synced": sync.get("balances_synced"),
        "orders_seen": sync.get("orders_seen"),
        "reconciliation_status": reconciliation.get("status"),
        "proof_sha256": proof_hashes,
        "real_ibkr_gateway_calls_performed": response.status == 200 and payload.get("status") == "verified_private_readonly",
        "raw_provider_response_persisted": False,
        "contains_account_id": False,
        "contains_session_token": False,
        "contains_credentials": False,
        "execution_available": False,
    }


def save_evidence(output_dir: Path, payload: dict) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    output_dir.chmod(0o700)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = output_dir / f"ibkr-readonly-{stamp}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--gateway-session-proof", type=Path, required=True)
    parser.add_argument("--read-only-boundary-proof", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "private-evidence" / "ibkr-readonly")
    args = parser.parse_args()

    errors = validate_target(args.api_base_url)
    if not args.user_id.strip():
        errors.append("user id is required")
    if errors:
        raise VerificationError("; ".join(errors))
    proof_hashes = {
        "gateway_session": proof_fingerprint(args.gateway_session_proof),
        "read_only_boundary": proof_fingerprint(args.read_only_boundary_proof),
    }
    if args.execute:
        response = ApiClient(args.api_base_url, os.getenv(SESSION_ENV, "").strip() or None).verify(
            user_id=args.user_id,
            payload={
                "gateway_session_proof_ref": f"artifact://sha256/{proof_hashes['gateway_session']}",
                "read_only_boundary_proof_ref": f"artifact://sha256/{proof_hashes['read_only_boundary']}",
                "verification_environment": "private_local",
            },
        )
        evidence = sanitize_verified_packet(response, user_id=args.user_id, proof_hashes=proof_hashes)
    else:
        evidence = {
            "status": "dry_run_valid",
            "provider": "ibkr_readonly",
            "proof_sha256": proof_hashes,
            "real_ibkr_gateway_calls_performed": False,
            "contains_account_id": False,
            "contains_session_token": False,
            "contains_credentials": False,
            "execution_available": False,
        }
    evidence.update(
        api_host=urlparse(args.api_base_url).hostname,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
    output = save_evidence(args.output_dir, evidence)
    print(json.dumps({"status": evidence["status"], "evidence": str(output)}))
    return 0 if evidence["status"] in {"dry_run_valid", "passed"} else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except VerificationError as exc:
        print(json.dumps({"status": "blocked", "error_class": exc.__class__.__name__}))
        raise SystemExit(2)
