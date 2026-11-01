#!/usr/bin/env python3
"""Verify real cloud/Vault secret read, rotation, invalidation, and recovery.

Run the four phases around operator-controlled changes to a disposable secret.
The reference and session token come from environment and are never persisted.
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
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


ROOT = Path(__file__).resolve().parents[1]
SESSION_ENV = "ATOS_SESSION_TOKEN"
REFERENCE_ENV = "ATOS_SECRET_REFERENCE"
ALLOWED_REFERENCE_PREFIXES = ("aws-sm://", "gcp-sm://", "vault://")


class LifecycleError(RuntimeError):
    pass


class Response(NamedTuple):
    status: int
    payload: object


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001, ANN201
        return None


class ApiClient:
    def __init__(self, base_url: str, session_token: str):
        self.base_url = base_url.rstrip("/")
        self.session_token = session_token
        self.opener = build_opener(_NoRedirect())

    def request(self, method: str, path: str, payload: dict | None = None) -> Response:
        body = json.dumps(payload).encode() if payload is not None else None
        headers = {"Accept": "application/json", "Authorization": f"Bearer {self.session_token}"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        request = Request(f"{self.base_url}{path}", data=body, headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=30) as response:
                raw = response.read().decode()
                return Response(response.status, json.loads(raw) if raw else {})
        except HTTPError as exc:
            raw = exc.read().decode(errors="replace")
            try:
                value = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                value = {"error_class": "NonJsonErrorResponse"}
            return Response(exc.code, value)


def reference_fingerprint(reference: str) -> str:
    return hashlib.sha256(reference.encode()).hexdigest()[:16]


def validate_inputs(base_url: str, reference: str) -> list[str]:
    parsed = urlparse(base_url)
    errors: list[str] = []
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        errors.append("API base URL must be credential-free HTTPS")
    if parsed.hostname in {"localhost", "127.0.0.1", "0.0.0.0"}:
        errors.append("real secret lifecycle acceptance cannot target localhost")
    if not reference.startswith(ALLOWED_REFERENCE_PREFIXES):
        errors.append("a disposable AWS/GCP/Vault secret reference is required")
    return errors


def execute_phase(client: ApiClient, *, phase: str, reference: str, state: dict) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    if phase in {"baseline", "rotated", "recovered"}:
        response = client.request("POST", "/production/secrets/verify", {"reference": reference, "purpose": "secret_lifecycle_acceptance"})
        payload = response.payload if isinstance(response.payload, dict) else {}
        version = str(payload.get("version") or "")
        passed = response.status == 200 and payload.get("resolved") is True and bool(version)
        if phase == "rotated":
            passed = passed and bool(state.get("baseline_version")) and version != state.get("baseline_version")
        if phase == "recovered":
            passed = passed and state.get("invalidation_verified") is True
        updated = {
            **state,
            "reference_fingerprint": reference_fingerprint(reference),
            "backend": payload.get("backend"),
            f"{phase}_http_status": response.status,
            f"{phase}_version": version or None,
            f"{phase}_verified": passed,
            f"{phase}_at": now,
        }
        if phase == "baseline":
            updated["baseline_version"] = version or None
        return updated

    response = client.request("POST", "/production/secrets/verify", {"reference": reference, "purpose": "secret_lifecycle_acceptance"})
    listing = client.request("GET", "/beta/secrets/references?limit=100")
    references = listing.payload if isinstance(listing.payload, list) else []
    matching = next((item for item in references if isinstance(item, dict) and item.get("reference_key") == reference), {})
    passed = state.get("rotated_verified") is True and response.status == 422 and listing.status == 200 and matching.get("status") == "invalid"
    return {
        **state,
        "reference_fingerprint": reference_fingerprint(reference),
        "invalidation_http_status": response.status,
        "stored_status_after_invalidation": matching.get("status"),
        "invalidation_verified": passed,
        "invalidation_at": now,
    }


def save_state(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    safe = {
        **payload,
        "contains_secret_value": False,
        "contains_session_token": False,
        "production_execution_enabled": False,
    }
    path.write_text(json.dumps(safe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base-url", required=True)
    parser.add_argument("--phase", choices=("baseline", "rotated", "invalidated", "recovered"), required=True)
    parser.add_argument("--state-file", type=Path, default=ROOT / "private-evidence" / "secret-lifecycle" / "state.json")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    session_token = os.getenv(SESSION_ENV, "").strip()
    reference = os.getenv(REFERENCE_ENV, "").strip()
    errors = validate_inputs(args.api_base_url, reference)
    if not session_token:
        errors.append(f"{SESSION_ENV} is required")
    if errors:
        raise LifecycleError("; ".join(errors))
    state = json.loads(args.state_file.read_text(encoding="utf-8")) if args.state_file.exists() else {}
    if not args.execute:
        result = {**state, "status": "dry_run_valid", "phase": args.phase, "real_secret_manager_call_performed": False}
    else:
        result = execute_phase(ApiClient(args.api_base_url, session_token), phase=args.phase, reference=reference, state=state)
        verified = bool(result.get(f"{args.phase}_verified")) if args.phase != "invalidated" else bool(result.get("invalidation_verified"))
        result.update(status="passed" if verified else "failed", phase=args.phase, real_secret_manager_call_performed=True)
        if args.phase == "recovered" and verified:
            result["lifecycle_complete"] = all(result.get(key) is True for key in ("baseline_verified", "rotated_verified", "invalidation_verified", "recovered_verified"))
    result.update(api_host=urlparse(args.api_base_url).hostname, generated_at=datetime.now(timezone.utc).isoformat())
    save_state(args.state_file, result)
    print(json.dumps({"status": result["status"], "phase": args.phase, "state_file": str(args.state_file)}))
    return 0 if result["status"] in {"dry_run_valid", "passed"} else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except LifecycleError as exc:
        print(json.dumps({"status": "blocked", "error_class": exc.__class__.__name__}))
        raise SystemExit(2)
