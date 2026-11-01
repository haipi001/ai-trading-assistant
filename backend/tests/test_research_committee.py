import json
import pytest


RESEARCH_REQUEST = {
    "data_snapshot_id": "committee-snapshot-1",
    "asset_id": "asset-aapl",
    "market_facts": {
        "symbol": "AAPL",
        "price": 190.25,
        "news": ["Earnings date supplied as structured fact."],
    },
    "positions": [{"symbol": "AAPL", "market_value": 12000, "weight": 0.12}],
    "signals": [{"signal_type": "rsi", "direction": "neutral", "strength": 0.4}],
    "prior_reports": [{"report_id": "prior-1", "summary": "Prior report fact."}],
}


@pytest.fixture(autouse=True)
def trusted_committee_snapshot(trusted_snapshot_factory):
    trusted_snapshot_factory(RESEARCH_REQUEST["data_snapshot_id"])


def test_research_committee_stores_agent_runs(client):
    response = client.post("/agents/run-research", json=RESEARCH_REQUEST)

    assert response.status_code == 201
    payload = response.json()
    assert len(payload["agent_runs"]) == 8
    assert {run["agent_name"] for run in payload["agent_runs"]} == {
        "FundamentalAnalyst",
        "TechnicalAnalyst",
        "NewsAnalyst",
        "CryptoOnchainAnalyst",
        "BullResearcher",
        "BearResearcher",
        "RiskManager",
        "PortfolioManager",
    }
    assert all(run["status"] == "completed" for run in payload["agent_runs"])
    assert all(run["input_snapshot_id"] == "committee-snapshot-1" for run in payload["agent_runs"])


def test_research_committee_generates_final_report(client):
    response = client.post("/agents/run-research", json=RESEARCH_REQUEST)

    assert response.status_code == 201
    report = response.json()["final_report"]
    assert report["report_type"] == "single_asset_research"
    assert report["agent_name"] == "ResearchCommittee"
    assert report["data_snapshot_id"] == "committee-snapshot-1"
    assert report["suggested_action"] == "review_only"
    assert len(report["evidence"]["agent_run_ids"]) == 8


def test_research_committee_rejects_invalid_json(client, monkeypatch):
    class InvalidFundamentalAnalyst:
        agent_name = "FundamentalAnalyst"

        def run(self, *, data_snapshot_id, input_facts):
            return "{invalid json"

    monkeypatch.setattr("app.services.research_committee.FundamentalAnalyst", InvalidFundamentalAnalyst)

    response = client.post("/agents/run-research", json=RESEARCH_REQUEST)

    assert response.status_code == 422
    audit_response = client.get("/audit-logs")
    assert any(log["action"] == "agent_run.invalid_output_rejected" for log in audit_response.json())


def test_research_committee_rejects_schema_invalid_json(client, monkeypatch):
    class InvalidTechnicalAnalyst:
        agent_name = "TechnicalAnalyst"

        def run(self, *, data_snapshot_id, input_facts):
            return json.dumps({"agent_name": "TechnicalAnalyst", "data_snapshot_id": data_snapshot_id})

    monkeypatch.setattr("app.services.research_committee.TechnicalAnalyst", InvalidTechnicalAnalyst)

    response = client.post("/agents/run-research", json=RESEARCH_REQUEST)

    assert response.status_code == 422


def test_research_committee_does_not_create_execution_or_order_intent(client):
    response = client.post("/agents/run-research", json={**RESEARCH_REQUEST, "automation_level": "A3_ORDER_DRAFT"})

    assert response.status_code == 201
    payload = response.json()
    assert payload["order_intent_id"] is None
    assert payload["final_report"]["evidence"]["order_intent_created"] is False
    assert client.get("/orders/drafts").json() == []
