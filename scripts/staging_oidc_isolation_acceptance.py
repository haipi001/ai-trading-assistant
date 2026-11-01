#!/usr/bin/env python3
"""Run real two-identity OIDC/RBAC/tenant-isolation acceptance in staging.

The command is dry-run by default. `--execute` performs small, clearly named
staging mutations. OIDC access tokens and managed session tokens are read from
environment variables and are never printed or persisted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


ROOT = Path(__file__).resolve().parents[1]
TOKEN_A_ENV = "ATOS_OIDC_ACCESS_TOKEN_A"
TOKEN_B_ENV = "ATOS_OIDC_ACCESS_TOKEN_B"


class AcceptanceError(RuntimeError):
    pass


class Response(NamedTuple):
    status: int
    payload: object


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001, ANN201
        return None


class ApiClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.opener = build_opener(_NoRedirect())

    def request(self, method: str, path: str, *, bearer: str | None = None, payload: dict | None = None, headers: dict[str, str] | None = None) -> Response:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request_headers = {"Accept": "application/json", **(headers or {})}
        if payload is not None:
            request_headers["Content-Type"] = "application/json"
        if bearer:
            request_headers["Authorization"] = f"Bearer {bearer}"
        request = Request(f"{self.base_url}{path}", data=body, headers=request_headers, method=method)
        try:
            with self.opener.open(request, timeout=30) as response:
                raw = response.read().decode("utf-8")
                return Response(response.status, json.loads(raw) if raw else {})
        except HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                payload_value = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                payload_value = {"error_class": "NonJsonErrorResponse"}
            return Response(exc.code, payload_value)


def validate_target(base_url: str, environment: str, allow_production: bool) -> list[str]:
    parsed = urlparse(base_url)
    errors: list[str] = []
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        errors.append("acceptance API must be a credential-free HTTPS URL")
    if parsed.hostname in {"localhost", "127.0.0.1", "0.0.0.0"}:
        errors.append("real OIDC acceptance cannot target localhost")
    if environment == "production" and not allow_production:
        errors.append("production mutation requires --allow-production in addition to --execute")
    return errors


def subject_fingerprint(subject: str) -> str:
    return hashlib.sha256(subject.encode("utf-8")).hexdigest()[:16]


def _check(checks: list[dict], key: str, passed: bool, evidence: dict) -> None:
    checks.append({"key": key, "status": "passed" if passed else "failed", "evidence": evidence})


def run_acceptance(client: ApiClient, *, access_token_a: str, access_token_b: str, maximum_session_seconds: int) -> dict:
    checks: list[dict] = []
    login_a = client.request("POST", "/production/auth/login", payload={"access_token": access_token_a})
    login_b = client.request("POST", "/production/auth/login", payload={"access_token": access_token_b})
    _check(checks, "oidc_login_a", login_a.status == 200, {"http_status": login_a.status})
    _check(checks, "oidc_login_b", login_b.status == 200, {"http_status": login_b.status})
    if login_a.status != 200 or login_b.status != 200 or not isinstance(login_a.payload, dict) or not isinstance(login_b.payload, dict):
        return {"checks": checks, "passed": False}

    session_a = str(login_a.payload.get("session_token") or "")
    session_b = str(login_b.payload.get("session_token") or "")
    user_a = login_a.payload.get("user") if isinstance(login_a.payload.get("user"), dict) else {}
    user_b = login_b.payload.get("user") if isinstance(login_b.payload.get("user"), dict) else {}
    subject_a, subject_b = str(user_a.get("user_id") or ""), str(user_b.get("user_id") or "")
    role_a, role_b = str(user_a.get("role") or ""), str(user_b.get("role") or "")
    distinct = bool(subject_a and subject_b and subject_a != subject_b and session_a and session_b and session_a != session_b)
    _check(checks, "distinct_oidc_subjects_and_sessions", distinct, {
        "subject_a_fingerprint": subject_fingerprint(subject_a) if subject_a else None,
        "subject_b_fingerprint": subject_fingerprint(subject_b) if subject_b else None,
        "session_tokens_persisted": False,
    })
    least_privileged = role_a in {"viewer", "operator"} and role_b in {"viewer", "operator"}
    _check(checks, "least_privileged_test_identities", least_privileged, {"roles": sorted({role_a, role_b})})

    now = datetime.now(timezone.utc)
    expirations = []
    for payload in (login_a.payload, login_b.payload):
        try:
            expiry = datetime.fromisoformat(str(payload.get("expires_at")).replace("Z", "+00:00"))
            expirations.append((expiry - now).total_seconds())
        except (TypeError, ValueError):
            expirations.append(maximum_session_seconds + 1)
    short_sessions = all(0 < seconds <= maximum_session_seconds for seconds in expirations)
    _check(checks, "short_lived_sessions", short_sessions, {"maximum_allowed_seconds": maximum_session_seconds, "observed_ttl_seconds": [round(item) for item in expirations]})

    unauthenticated = client.request("GET", "/beta/whoami")
    _check(checks, "missing_session_fails_closed", unauthenticated.status == 401, {"http_status": unauthenticated.status})
    whoami_a = client.request("GET", "/beta/whoami", bearer=session_a)
    spoofed_b = client.request("GET", "/beta/whoami", bearer=session_b, headers={"X-AI-Trading-User": subject_a, "X-AI-Trading-Role": "owner"})
    spoof_payload = spoofed_b.payload if isinstance(spoofed_b.payload, dict) else {}
    _check(checks, "identity_headers_cannot_override_session", spoofed_b.status == 200 and spoof_payload.get("user_id") == subject_b and spoof_payload.get("role") == role_b, {"http_status": spoofed_b.status})
    _check(checks, "session_identity_matches_oidc_subject", whoami_a.status == 200 and isinstance(whoami_a.payload, dict) and whoami_a.payload.get("user_id") == subject_a, {"http_status": whoami_a.status})

    nonce = secrets.token_hex(6)
    account_a = client.request("POST", "/accounts", bearer=session_a, payload={"name": f"OIDC isolation A {nonce}", "account_type": "test", "broker": "staging-acceptance", "base_currency": "USD"})
    account_b = client.request("POST", "/accounts", bearer=session_b, payload={"name": f"OIDC isolation B {nonce}", "account_type": "test", "broker": "staging-acceptance", "base_currency": "USD"})
    account_a_id = account_a.payload.get("id") if isinstance(account_a.payload, dict) else None
    account_b_id = account_b.payload.get("id") if isinstance(account_b.payload, dict) else None
    _check(checks, "tenant_test_resources_created", account_a.status == 201 and account_b.status == 201 and account_a_id and account_b_id, {"status_a": account_a.status, "status_b": account_b.status})
    list_a = client.request("GET", "/accounts", bearer=session_a)
    list_b = client.request("GET", "/accounts", bearer=session_b)
    ids_a = {item.get("id") for item in list_a.payload if isinstance(item, dict)} if isinstance(list_a.payload, list) else set()
    ids_b = {item.get("id") for item in list_b.payload if isinstance(item, dict)} if isinstance(list_b.payload, list) else set()
    _check(checks, "account_list_tenant_isolation", account_a_id in ids_a and account_a_id not in ids_b and account_b_id in ids_b and account_b_id not in ids_a, {"status_a": list_a.status, "status_b": list_b.status})

    export_a = client.request("POST", "/daily-use/exports", bearer=session_a, payload={"export_type": "daily_snapshot", "include_sections": ["staging_oidc_isolation_acceptance"]})
    export_id = export_a.payload.get("id") if isinstance(export_a.payload, dict) else None
    resource_probe = client.request("GET", f"/daily-use/exports/{export_id}", bearer=session_b) if export_id else Response(0, {})
    _check(checks, "resource_id_tenant_isolation", export_a.status == 201 and resource_probe.status == 404, {"create_status": export_a.status, "cross_tenant_status": resource_probe.status})

    query_spoof = client.request("GET", f"/daily-use/exports?user_id={subject_a}", bearer=session_b)
    body_spoof = client.request("POST", "/daily-use/exports", bearer=session_b, payload={"user_id": subject_a, "export_type": "daily_snapshot", "include_sections": []})
    _check(checks, "query_user_scope_spoof_denied", query_spoof.status == 403, {"http_status": query_spoof.status})
    _check(checks, "json_user_scope_spoof_denied", body_spoof.status == 403, {"http_status": body_spoof.status})

    rbac_denial = client.request("POST", "/beta/users", bearer=session_b, payload={"user_id": f"forbidden-{nonce}", "display_name": "forbidden", "role": "viewer"})
    _check(checks, "rbac_privileged_write_denied", rbac_denial.status == 403, {"http_status": rbac_denial.status, "tested_role": role_b})

    logout_a = client.request("POST", "/production/auth/logout", bearer=session_a, payload={"session_token": session_a})
    revoked_a = client.request("GET", "/beta/whoami", bearer=session_a)
    surviving_b = client.request("GET", "/beta/whoami", bearer=session_b)
    _check(checks, "session_revocation", logout_a.status == 200 and revoked_a.status == 401, {"logout_status": logout_a.status, "revoked_session_status": revoked_a.status})
    _check(checks, "revocation_is_session_scoped", surviving_b.status == 200, {"other_session_status": surviving_b.status})

    return {
        "checks": checks,
        "passed": all(item["status"] == "passed" for item in checks),
        "real_oidc_calls_performed": True,
        "test_records_created": True,
        "contains_tokens": False,
        "production_execution_enabled": False,
    }


def save_evidence(output_dir: Path, payload: dict) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = output_dir / f"oidc-isolation-acceptance-{stamp}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base-url", required=True)
    parser.add_argument("--environment", choices=("staging", "production"), default="staging")
    parser.add_argument("--maximum-session-seconds", type=int, default=3700)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--allow-production", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "private-evidence" / "oidc-isolation")
    args = parser.parse_args()
    errors = validate_target(args.api_base_url, args.environment, args.allow_production)
    token_a, token_b = os.getenv(TOKEN_A_ENV, "").strip(), os.getenv(TOKEN_B_ENV, "").strip()
    if not token_a or not token_b or token_a == token_b:
        errors.append(f"distinct {TOKEN_A_ENV} and {TOKEN_B_ENV} values are required")
    if errors:
        raise AcceptanceError("; ".join(errors))
    if not args.execute:
        evidence = {"status": "dry_run_valid", "real_oidc_calls_performed": False, "contains_tokens": False, "production_execution_enabled": False}
    else:
        evidence = run_acceptance(ApiClient(args.api_base_url), access_token_a=token_a, access_token_b=token_b, maximum_session_seconds=args.maximum_session_seconds)
        evidence["status"] = "passed" if evidence["passed"] else "failed"
    evidence.update(environment=args.environment, api_host=urlparse(args.api_base_url).hostname, generated_at=datetime.now(timezone.utc).isoformat())
    output = save_evidence(args.output_dir, evidence)
    print(json.dumps({"status": evidence["status"], "evidence": str(output)}))
    return 0 if evidence["status"] in {"dry_run_valid", "passed"} else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AcceptanceError as exc:
        print(json.dumps({"status": "blocked", "error_class": exc.__class__.__name__}))
        raise SystemExit(2)
