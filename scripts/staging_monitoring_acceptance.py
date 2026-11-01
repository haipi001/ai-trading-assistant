#!/usr/bin/env python3
"""Verify real external alert delivery and persisted monitoring evidence.

The managed session token is read only from ``ATOS_SESSION_TOKEN``. The script
must target a non-local HTTPS staging deployment unless production execution is
explicitly allowed. It sends one operator-requested test alert, then proves the
delivery was persisted by reading the notification status and stability report.
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


class AcceptanceError(RuntimeError):
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

    def request(self, method: str, path: str, *, authenticated: bool = True) -> Response:
        headers = {"Accept": "application/json"}
        if authenticated:
            headers["Authorization"] = f"Bearer {self.session_token}"
        request = Request(f"{self.base_url}{path}", headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=30) as response:
                raw = response.read().decode("utf-8")
                return Response(response.status, json.loads(raw) if raw else {})
        except HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                payload = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                payload = {"error_class": "NonJsonErrorResponse"}
            return Response(exc.code, payload)


def validate_target(base_url: str, environment: str, allow_production: bool) -> list[str]:
    parsed = urlparse(base_url)
    errors: list[str] = []
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        errors.append("monitoring acceptance API must be a credential-free HTTPS URL")
    hostname = (parsed.hostname or "").lower()
    if hostname in {"localhost", "127.0.0.1", "0.0.0.0", "::1"} or hostname.endswith(".localhost"):
        errors.append("real monitoring acceptance cannot target localhost")
    if environment == "production" and not allow_production:
        errors.append("production alert mutation requires --allow-production in addition to --execute")
    return errors


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _monitoring_check(payload: object) -> dict:
    if not isinstance(payload, dict):
        return {}
    checks = payload.get("checks")
    if not isinstance(checks, list):
        return {}
    return next((item for item in checks if isinstance(item, dict) and item.get("key") == "monitoring"), {})


def _delivery_summary(payload: object) -> dict:
    if not isinstance(payload, dict):
        return {}
    webhook = payload.get("webhook_delivery")
    if not isinstance(webhook, dict):
        return {}
    summary = webhook.get("summary")
    return summary if isinstance(summary, dict) else {}


def run_acceptance(client: ApiClient, *, environment: str, expected_release_id: str, fault_count: int) -> dict:
    readiness = client.request("GET", "/health/ready", authenticated=False)
    before = client.request("GET", "/ops/notification-channels")
    before_summary = _delivery_summary(before.payload)
    delivery = client.request("POST", "/ops/notification-channels/webhook/test")
    after = client.request("GET", "/ops/notification-channels")
    baseline_metrics = client.request("GET", "/ops/observability")
    fault_responses = [client.request("POST", "/ops/observability/fault-injection") for _ in range(fault_count)]
    incident = client.request("POST", "/ops/observability/evaluate")
    incident_channels = client.request("GET", "/ops/notification-channels")
    stability = client.request("GET", "/ops/stability-report")

    ready_payload = readiness.payload if isinstance(readiness.payload, dict) else {}
    delivery_payload = delivery.payload if isinstance(delivery.payload, dict) else {}
    delivery_detail = delivery_payload.get("delivery") if isinstance(delivery_payload.get("delivery"), dict) else {}
    after_payload = after.payload if isinstance(after.payload, dict) else {}
    after_summary = _delivery_summary(after.payload)
    baseline_payload = baseline_metrics.payload if isinstance(baseline_metrics.payload, dict) else {}
    incident_payload = incident.payload if isinstance(incident.payload, dict) else {}
    incident_report = incident_payload.get("report") if isinstance(incident_payload.get("report"), dict) else {}
    incident_notification = incident_payload.get("notification") if isinstance(incident_payload.get("notification"), dict) else {}
    incident_delivery = incident_notification.get("external_delivery") if isinstance(incident_notification.get("external_delivery"), dict) else {}
    incident_summary = _delivery_summary(incident_channels.payload)
    stability_payload = stability.payload if isinstance(stability.payload, dict) else {}
    monitoring = _monitoring_check(stability.payload)
    before_count = int(before_summary.get("delivered") or 0)
    after_count = int(after_summary.get("delivered") or 0)

    checks = {
        "target_release_verified": readiness.status == 200 and ready_payload.get("status") == "ready" and ready_payload.get("release_id") == expected_release_id,
        "notification_preflight_readable": before.status == 200,
        "real_webhook_delivery_succeeded": (
            delivery.status == 201
            and delivery_payload.get("status") == "delivered"
            and delivery_detail.get("delivered") is True
            and delivery_detail.get("attempted") is True
            and delivery_detail.get("external_message_sent") is True
            and isinstance(delivery_detail.get("http_status"), int)
            and 200 <= delivery_detail["http_status"] < 300
            and bool(delivery_detail.get("delivery_event_id"))
        ),
        "delivery_evidence_persisted": (
            after.status == 200
            and after_payload.get("external_delivery_status") == "delivery_verified"
            and after_summary.get("real_delivery_evidence") is True
            and after_count >= before_count + 1
        ),
        "preexisting_slo_breach_absent": baseline_metrics.status == 200 and baseline_payload.get("status") in {"ok", "insufficient_data"},
        "controlled_staging_failures_observed": (
            len(fault_responses) == fault_count
            and all(item.status == 503 and isinstance(item.payload, dict) and item.payload.get("status") == "injected_staging_failure" for item in fault_responses)
        ),
        "real_http_metrics_detected_incident": (
            incident.status == 201
            and incident_payload.get("status") == "breached"
            and incident_report.get("real_request_metrics") is True
            and incident_report.get("sample_sufficient") is True
            and int(incident_report.get("errors") or 0) >= int(baseline_payload.get("errors") or 0) + fault_count
            and incident_payload.get("alert_created") is True
        ),
        "incident_external_alert_delivered": (
            incident_notification.get("external_notification_delivered") is True
            and incident_delivery.get("delivered") is True
            and incident_delivery.get("attempted") is True
            and incident_delivery.get("external_message_sent") is True
            and isinstance(incident_delivery.get("http_status"), int)
            and 200 <= incident_delivery["http_status"] < 300
        ),
        "incident_delivery_evidence_persisted": (
            incident_channels.status == 200
            and incident_summary.get("real_delivery_evidence") is True
            and int(incident_summary.get("delivered") or 0) >= after_count + 1
        ),
        "stability_monitoring_gate_passed": (
            stability.status == 200
            and stability_payload.get("environment") == environment
            and monitoring.get("status") == "ok"
        ),
        "execution_remained_disabled": stability_payload.get("execution_available") is False,
    }
    passed = all(checks.values())
    return {
        "status": "passed" if passed else "failed",
        "passed": passed,
        "checks": [{"key": key, "status": "passed" if value else "failed"} for key, value in checks.items()],
        "release_id": expected_release_id,
        "observed_release_id": ready_payload.get("release_id"),
        "delivery_http_status": delivery_detail.get("http_status"),
        "delivery_event_fingerprint": _fingerprint(str(delivery_detail.get("delivery_event_id"))) if delivery_detail.get("delivery_event_id") else None,
        "test_event_fingerprint": _fingerprint(str(delivery_payload.get("test_event_id"))) if delivery_payload.get("test_event_id") else None,
        "delivered_count_before": before_count,
        "delivered_count_after": after_count,
        "delivered_count_after_incident": int(incident_summary.get("delivered") or 0),
        "fault_count": fault_count,
        "baseline_slo_status": baseline_payload.get("status"),
        "incident_slo_status": incident_payload.get("status"),
        "incident_alert_created": incident_payload.get("alert_created") is True,
        "incident_delivery_event_fingerprint": _fingerprint(str(incident_delivery.get("delivery_event_id"))) if incident_delivery.get("delivery_event_id") else None,
        "real_external_message_sent": delivery_detail.get("external_message_sent") is True,
        "server_delivery_record_persisted": after_summary.get("real_delivery_evidence") is True,
        "stability_monitoring_status": monitoring.get("status"),
        "real_staging_calls_performed": True,
        "contains_session_token": False,
        "contains_webhook_secret": False,
        "production_execution_enabled": False,
    }


def save_evidence(output_dir: Path, payload: dict) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = output_dir / f"monitoring-acceptance-{stamp}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base-url", required=True)
    parser.add_argument("--environment", choices=("staging", "production"), default="staging")
    parser.add_argument("--expected-release-id", required=True)
    parser.add_argument("--fault-count", type=int, default=100)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--allow-production", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "private-evidence" / "monitoring")
    args = parser.parse_args()

    session_token = os.getenv(SESSION_ENV, "").strip()
    errors = validate_target(args.api_base_url, args.environment, args.allow_production)
    if not session_token:
        errors.append(f"{SESSION_ENV} is required")
    if not args.expected_release_id.strip():
        errors.append("expected release id is required")
    if args.fault_count < 1 or args.fault_count > 110:
        errors.append("fault count must be between 1 and 110")
    if errors:
        raise AcceptanceError("; ".join(errors))

    if args.execute:
        evidence = run_acceptance(
            ApiClient(args.api_base_url, session_token),
            environment=args.environment,
            expected_release_id=args.expected_release_id,
            fault_count=args.fault_count,
        )
    else:
        evidence = {
            "status": "dry_run_valid",
            "real_external_message_sent": False,
            "server_delivery_record_persisted": False,
            "real_staging_calls_performed": False,
            "contains_session_token": False,
            "contains_webhook_secret": False,
            "production_execution_enabled": False,
        }
    evidence.update(
        environment=args.environment,
        api_host=urlparse(args.api_base_url).hostname,
        expected_release_id=args.expected_release_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
    output = save_evidence(args.output_dir, evidence)
    print(json.dumps({"status": evidence["status"], "evidence": str(output)}))
    return 0 if evidence["status"] in {"dry_run_valid", "passed"} else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AcceptanceError as exc:
        print(json.dumps({"status": "blocked", "error_class": exc.__class__.__name__}))
        raise SystemExit(2)
