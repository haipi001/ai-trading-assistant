import json
from typing import Any
import pytest


VALID_REPORT_REQUEST = {
    "report_type": "portfolio_daily_review",
    "data_snapshot_id": "snapshot-2026-05-28",
    "input_facts": {
        "total_equity": 100000,
        "cash": 12000,
        "allocation": {"stocks": 0.55, "crypto": 0.35, "cash": 0.10},
        "risks": ["NVDA concentration is above target."],
    },
}


@pytest.fixture(autouse=True)
def trusted_report_snapshot(trusted_snapshot_factory):
    trusted_snapshot_factory(VALID_REPORT_REQUEST["data_snapshot_id"])


def test_mock_ai_provider_generates_valid_report(client):
    response = client.post("/reports/generate", json=VALID_REPORT_REQUEST)

    assert response.status_code == 201
    payload = response.json()
    assert payload["report_id"] == payload["id"]
    assert payload["report_type"] == "portfolio_daily_review"
    assert payload["agent_name"] == "mock_research_agent"
    assert payload["data_snapshot_id"] == "snapshot-2026-05-28"
    assert payload["input_facts"] == VALID_REPORT_REQUEST["input_facts"]
    assert payload["suggested_action"] == "review_only"
    assert payload["key_risks"]["items"] == ["NVDA concentration is above target."]


def test_report_writes_audit_log(client):
    response = client.post("/reports/generate", json=VALID_REPORT_REQUEST)
    assert response.status_code == 201
    report_id = response.json()["id"]

    audit_response = client.get("/audit-logs")

    assert audit_response.status_code == 200
    logs = audit_response.json()
    assert any(
        log["action"] == "research_report.generated"
        and log["entity_type"] == "ResearchReport"
        and log["entity_id"] == report_id
        for log in logs
    )


def test_report_includes_data_snapshot_id(client):
    response = client.post("/reports/generate", json=VALID_REPORT_REQUEST)

    assert response.status_code == 201
    assert response.json()["data_snapshot_id"] == VALID_REPORT_REQUEST["data_snapshot_id"]


def test_report_generation_rejects_uncatalogued_snapshot_and_audits_gate(client):
    response = client.post(
        "/reports/generate",
        json={**VALID_REPORT_REQUEST, "data_snapshot_id": "uncatalogued-snapshot"},
    )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "data_trust_gate_blocked"
    assert detail["status"] == "blocked"
    assert "snapshot_not_catalogued" in detail["blockers"]
    assert any(
        log["action"] == "data_catalog.downstream_trust_gate_blocked"
        and log["entity_id"] == "uncatalogued-snapshot"
        for log in client.get("/audit-logs").json()
    )


def test_invalid_report_is_rejected_and_logged(client, monkeypatch):
    class InvalidProvider:
        def generate_report(
            self,
            *,
            report_type: str,
            agent_name: str,
            data_snapshot_id: str,
            input_facts: dict[str, Any],
            prompt_template: str,
        ) -> str:
            return json.dumps({"summary": "missing required fields"})

    monkeypatch.setattr("app.services.reports.MockAIProvider", InvalidProvider)

    response = client.post("/reports/generate", json=VALID_REPORT_REQUEST)

    assert response.status_code == 422
    audit_response = client.get("/audit-logs")
    assert any(log["action"] == "research_report.invalid_output_rejected" for log in audit_response.json())


def test_openai_provider_fails_closed_when_external_calls_are_disabled(client):
    response = client.post("/reports/generate", json={**VALID_REPORT_REQUEST, "provider": "openai"})

    assert response.status_code == 422
    assert "external LLM calls are disabled" in response.json()["detail"]


def test_deepseek_provider_fails_closed_when_external_calls_are_disabled(client):
    response = client.post("/reports/generate", json={**VALID_REPORT_REQUEST, "provider": "deepseek"})

    assert response.status_code == 422
    assert "external LLM calls are disabled" in response.json()["detail"]


def test_report_with_executable_order_language_is_rejected_and_logged(client, monkeypatch):
    """Red-team: a provider that tries to sneak an execution instruction into suggested_action
    must be blocked by schema validation before the report is ever stored, and the rejection
    must be audited so an attempted override attempt is not silently dropped."""

    class ExecutionLeakingProvider:
        def generate_report(self, *, report_type, agent_name, data_snapshot_id, input_facts, prompt_template):
            return json.dumps(
                {
                    "report_id": "leak-1",
                    "report_type": report_type,
                    "agent_name": agent_name,
                    "data_snapshot_id": data_snapshot_id,
                    "input_facts": input_facts,
                    "summary": "Structured summary.",
                    "bullish_case": "Structured bullish case.",
                    "bearish_case": "Structured bearish case.",
                    "key_risks": ["Valuation"],
                    "suggested_action": "Place a market order to buy immediately before the close.",
                    "confidence": 0.8,
                    "evidence": {"source": data_snapshot_id},
                    "limitations": "Snapshot facts only.",
                }
            )

    monkeypatch.setattr("app.services.reports.MockAIProvider", ExecutionLeakingProvider)

    response = client.post("/reports/generate", json=VALID_REPORT_REQUEST)

    assert response.status_code == 422
    assert "executable order instructions" in response.json()["detail"]
    audit_response = client.get("/audit-logs")
    assert any(log["action"] == "research_report.invalid_output_rejected" for log in audit_response.json())
