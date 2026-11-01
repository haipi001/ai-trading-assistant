from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "staging_monitoring_acceptance.py"
SPEC = importlib.util.spec_from_file_location("staging_monitoring_acceptance", SCRIPT)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class FakeClient:
    def __init__(self, responses):
        self.responses = iter(responses)

    def request(self, method, path, *, authenticated=True):
        return next(self.responses)


def response(status, payload):
    return module.Response(status, payload)


def successful_responses(*, release_id="release-42", persisted=True, monitoring_status="ok", baseline_status="ok"):
    return [
        response(200, {"status": "ready", "release_id": release_id}),
        response(200, {"webhook_delivery": {"summary": {"delivered": 2, "real_delivery_evidence": True}}}),
        response(201, {
            "status": "delivered",
            "test_event_id": "test-secret-id",
            "delivery": {
                "delivered": True,
                "attempted": True,
                "external_message_sent": True,
                "http_status": 204,
                "delivery_event_id": "delivery-secret-id",
            },
        }),
        response(200, {
            "external_delivery_status": "delivery_verified",
            "webhook_delivery": {"summary": {"delivered": 3, "real_delivery_evidence": persisted}},
        }),
        response(200, {"status": baseline_status, "errors": 0, "real_request_metrics": True}),
        response(503, {"status": "injected_staging_failure", "execution_available": False}),
        response(503, {"status": "injected_staging_failure", "execution_available": False}),
        response(201, {
            "status": "breached",
            "alert_created": True,
            "report": {"errors": 2, "sample_sufficient": True, "real_request_metrics": True},
            "notification": {
                "external_notification_delivered": True,
                "external_delivery": {
                    "delivered": True,
                    "attempted": True,
                    "external_message_sent": True,
                    "http_status": 202,
                    "delivery_event_id": "incident-delivery-secret-id",
                },
            },
        }),
        response(200, {
            "external_delivery_status": "delivery_verified",
            "webhook_delivery": {"summary": {"delivered": 4, "real_delivery_evidence": True}},
        }),
        response(200, {
            "environment": "staging",
            "execution_available": False,
            "checks": [{"key": "monitoring", "status": monitoring_status}],
        }),
    ]


def test_acceptance_requires_https_nonlocal_target_and_explicit_production_flag():
    assert module.validate_target("http://staging.example", "staging", False)
    assert module.validate_target("https://localhost", "staging", False)
    assert module.validate_target("https://user:pass@staging.example", "staging", False)
    assert module.validate_target("https://api.example", "production", False)
    assert module.validate_target("https://api.example", "production", True) == []


def test_real_delivery_must_be_persisted_and_monitoring_gate_must_pass():
    result = module.run_acceptance(FakeClient(successful_responses()), environment="staging", expected_release_id="release-42", fault_count=2)
    assert result["status"] == "passed"
    assert result["real_external_message_sent"] is True
    assert result["server_delivery_record_persisted"] is True
    assert result["delivered_count_after"] == result["delivered_count_before"] + 1
    assert result["delivered_count_after_incident"] == result["delivered_count_after"] + 1
    assert result["incident_alert_created"] is True
    assert result["contains_session_token"] is False
    assert "secret-id" not in str(result)


def test_release_mismatch_fails_closed():
    result = module.run_acceptance(FakeClient(successful_responses(release_id="wrong")), environment="staging", expected_release_id="release-42", fault_count=2)
    assert result["status"] == "failed"
    assert next(item for item in result["checks"] if item["key"] == "target_release_verified")["status"] == "failed"


def test_unpersisted_delivery_fails_closed_even_after_successful_http_send():
    result = module.run_acceptance(FakeClient(successful_responses(persisted=False)), environment="staging", expected_release_id="release-42", fault_count=2)
    assert result["status"] == "failed"
    assert next(item for item in result["checks"] if item["key"] == "delivery_evidence_persisted")["status"] == "failed"


def test_stability_monitoring_gate_failure_is_not_accepted():
    result = module.run_acceptance(FakeClient(successful_responses(monitoring_status="block")), environment="staging", expected_release_id="release-42", fault_count=2)
    assert result["status"] == "failed"
    assert next(item for item in result["checks"] if item["key"] == "stability_monitoring_gate_passed")["status"] == "failed"


def test_preexisting_slo_breach_cannot_be_reused_as_new_incident_evidence():
    result = module.run_acceptance(
        FakeClient(successful_responses(baseline_status="breached")),
        environment="staging",
        expected_release_id="release-42",
        fault_count=2,
    )
    assert result["status"] == "failed"
    assert next(item for item in result["checks"] if item["key"] == "preexisting_slo_breach_absent")["status"] == "failed"


def test_evidence_file_is_private_and_contains_no_token(tmp_path):
    path = module.save_evidence(tmp_path, {"status": "passed", "contains_session_token": False})
    assert path.stat().st_mode & 0o077 == 0
    assert "token-value" not in path.read_text()
