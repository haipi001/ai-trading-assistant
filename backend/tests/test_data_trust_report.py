from datetime import datetime
from datetime import timezone

from fastapi.testclient import TestClient


def create_mock_connection(client: TestClient) -> dict:
    response = client.post(
        "/data-sources/connections",
        json={
            "name": "Trust Report Mock",
            "provider": "mock_market_data",
            "source_type": "market_data",
            "mode": "read_only",
        },
    )
    assert response.status_code == 201
    return response.json()


def test_data_trust_report_blocks_missing_required_datasets(client: TestClient) -> None:
    response = client.get("/data-catalog/trust-report?decision_scope=research")

    assert response.status_code == 200
    report = response.json()
    assert report["decision_scope"] == "research"
    assert report["overall_status"] == "blocked"
    assert report["trusted_count"] == 0
    assert report["blocked_count"] == 2
    assert report["execution_available"] is False
    statuses = {item["dataset_type"]: item["status"] for item in report["items"]}
    assert statuses == {"market_quotes": "missing", "market_candles": "missing"}


def test_data_trust_report_marks_research_trusted_after_valid_market_imports(client: TestClient) -> None:
    connection = create_mock_connection(client)
    quote_response = client.post(
        f"/data-sources/connections/{connection['id']}/import-quotes",
        json={"symbols": ["AAPL", "NVDA"], "asset_type": "stock", "market": "US", "currency": "USD"},
    )
    assert quote_response.status_code == 201
    candle_response = client.post(
        f"/data-sources/connections/{connection['id']}/import-candles",
        json={"symbols": ["AAPL", "NVDA"], "timeframe": "1d", "limit": 5},
    )
    assert candle_response.status_code == 201

    response = client.get("/data-catalog/trust-report?decision_scope=research")

    assert response.status_code == 200
    report = response.json()
    assert report["overall_status"] == "trusted"
    assert report["trusted_count"] == 2
    assert report["blocked_count"] == 0
    assert report["review_only_count"] == 0
    assert all(item["quality_status"] == "VALID" for item in report["items"])
    assert all(item["status"] == "trusted" for item in report["items"])


def test_data_provenance_report_explains_hash_contract_and_scope_gates(client: TestClient) -> None:
    connection = create_mock_connection(client)
    quote_response = client.post(
        f"/data-sources/connections/{connection['id']}/import-quotes",
        json={"symbols": ["AAPL"], "asset_type": "stock", "market": "US", "currency": "USD"},
    )
    assert quote_response.status_code == 201
    candle_response = client.post(
        f"/data-sources/connections/{connection['id']}/import-candles",
        json={"symbols": ["AAPL"], "timeframe": "1d", "limit": 5},
    )
    assert candle_response.status_code == 201

    response = client.get("/data-catalog/provenance-report?decision_scope=research")

    assert response.status_code == 200
    report = response.json()
    assert report["decision_scope"] == "research"
    assert report["provenance_status"] == "trusted"
    assert report["trust_status"] == "trusted"
    assert report["execution_available"] is False
    required_items = [item for item in report["items"] if item["dataset_type"] in {"market_quotes", "market_candles"}]
    assert len(required_items) == 2
    assert all(item["computed_snapshot_hash"] for item in required_items)
    assert all(item["contract_version"] != "unspecified" for item in required_items)
    assert all(item["blockers"] == [] for item in required_items)


def test_data_trust_report_keeps_account_snapshot_review_only_for_ledger(client: TestClient) -> None:
    create_response = client.post(
        "/data-sources/connections",
        json={
            "name": "Trust CEX Read-only",
            "provider": "cex_readonly",
            "source_type": "exchange_account",
            "mode": "read_only",
            "config_json": {"exchange": "binance", "account_label": "main"},
        },
    )
    assert create_response.status_code == 201
    connection = create_response.json()

    sync_response = client.post(
        f"/data-sources/connections/{connection['id']}/sync-account",
        json={
            "sample_payload": {
                "as_of": datetime.now(timezone.utc).isoformat(),
                "account": {"account_id": "cex-main", "label": "main", "base_currency": "USD"},
                "balances": [{"currency": "USD", "cash_value": 1000}],
                "positions": [
                    {
                        "symbol": "BTC",
                        "asset_type": "crypto",
                        "quantity": 1,
                        "average_cost": 60000,
                        "market_price": 65000,
                    }
                ],
                "orders": [],
            }
        },
    )
    assert sync_response.status_code == 201

    response = client.get("/data-catalog/trust-report?decision_scope=ledger")

    assert response.status_code == 200
    report = response.json()
    assert report["overall_status"] == "review_only"
    assert report["review_only_count"] == 1
    assert report["blocked_count"] == 0
    item = report["items"][0]
    assert item["dataset_type"] == "read_only_account"
    assert item["status"] == "review_only"
    assert item["quality_status"] == "VALID"
    assert item["quality_score"] == 1
    assert item["entry"]["usable_for_trading"] is False
    assert any("ledger sync" in action.lower() for action in item["recommended_actions"])
