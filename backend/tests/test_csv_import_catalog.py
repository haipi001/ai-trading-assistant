from fastapi.testclient import TestClient


HOLDINGS_CSV = """account_name,account_type,asset_symbol,asset_name,asset_type,quantity,average_cost,current_price,market_value,currency,notes
Main CSV Account,brokerage,AAPL,Apple Inc.,stock,10,180,225,2250,USD,long-term core
Main CSV Account,brokerage,BTC,Bitcoin,crypto,0.5,42000,66000,33000,USD,cold storage read-only
Main CSV Account,brokerage,USD Cash,USD Cash,cash,1250,1,1,1250,USD,cash balance
"""


TRADES_CSV = """account_name,asset_symbol,asset_type,action,quantity,price,currency,transaction_date,notes
Trade Import Account,AAPL,stock,BUY,4,190,USD,2026-06-01,manual historical fill
Trade Import Account,NVDA,stock,SELL,1,910,USD,2026-06-02,manual historical trim
"""


def test_csv_holdings_import_creates_readonly_positions_snapshot_quality_and_catalog(client: TestClient) -> None:
    response = client.post(
        "/imports/csv",
        json={
            "import_type": "holdings",
            "csv_text": HOLDINGS_CSV,
            "source_name": "demo_csv_upload",
            "source_ref": "demo_csv/holdings.csv",
            "default_currency": "USD",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["import_type"] == "holdings"
    assert payload["rows_received"] == 3
    assert payload["rows_imported"] == 3
    assert payload["rows_skipped"] == 0
    assert payload["positions_upserted"] == 2
    assert payload["execution_available"] is False
    assert payload["snapshot"]["snapshot_type"] == "csv_holdings"
    assert payload["snapshot"]["metadata_json"]["execution_available"] is False
    assert payload["quality_report"]["metric_type"] == "holdings_csv_import_completeness"
    assert payload["quality_report"]["score"] == 1
    assert payload["catalog_entry"]["dataset_type"] == "csv_holdings"
    assert payload["catalog_entry"]["quality_status"] == "VALID"
    assert payload["catalog_entry"]["usable_for_trading"] is False
    assert payload["catalog_entry"]["contract_json"]["execution_available"] is False

    accounts = client.get("/accounts").json()
    account = next(row for row in accounts if row["name"] == "Main CSV Account")
    assert account["mode"] == "read_only"
    assert account["live_trading_enabled"] is False

    assets = client.get("/assets").json()
    imported_assets = {asset["symbol"]: asset for asset in assets if asset["symbol"] in {"AAPL", "BTC", "USD CASH"}}
    assert set(imported_assets) == {"AAPL", "BTC", "USD CASH"}
    assert all(
        asset["tradable"] is False and asset["manual_enabled"] is False and asset["auto_enabled"] is False
        for asset in imported_assets.values()
    )

    positions = client.get("/positions").json()
    synced_positions = [row for row in positions if row["account_id"] == account["id"]]
    assert len(synced_positions) == 2
    assert sum(position["market_value"] for position in synced_positions) == 35250

    entries_response = client.get("/data-catalog/entries?dataset_type=csv_holdings")
    assert entries_response.status_code == 200
    entries = entries_response.json()
    assert len(entries) == 1
    assert entries[0]["id"] == payload["catalog_entry"]["id"]

    overview_response = client.get("/data-catalog/overview")
    assert overview_response.status_code == 200
    overview = overview_response.json()
    assert overview["total_entries"] == 1
    assert overview["usable_for_trading_count"] == 0
    assert overview["blocked_count"] == 1
    assert overview["quality_counts"]["VALID"] == 1

    detail_response = client.get(f"/data-catalog/entries/{payload['catalog_entry']['id']}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["entry"]["id"] == payload["catalog_entry"]["id"]
    assert detail["snapshot"]["id"] == payload["snapshot"]["id"]
    assert detail["quality_report"]["id"] == payload["quality_report"]["id"]
    assert detail["contract_status"] == "blocked"
    assert detail["execution_available"] is False
    assert any("review-only" in blocker for blocker in detail["blockers"])
    assert any("reconcile" in action.lower() for action in detail["recommended_actions"])
    assert detail["related_action"]["method"] == "POST"


def test_data_catalog_versions_and_replays_snapshot_as_review_only(client: TestClient) -> None:
    import_response = client.post(
        "/imports/csv",
        json={
            "import_type": "holdings",
            "csv_text": HOLDINGS_CSV,
            "source_name": "demo_csv_upload",
            "source_ref": "demo_csv/holdings.csv",
            "default_currency": "USD",
        },
    )
    assert import_response.status_code == 201
    imported = import_response.json()
    entry_id = imported["catalog_entry"]["id"]
    original_snapshot_id = imported["snapshot"]["id"]

    version_response = client.post(f"/data-catalog/entries/{entry_id}/version")
    assert version_response.status_code == 200
    versioned = version_response.json()
    assert versioned["snapshot_id"] == original_snapshot_id
    assert versioned["dataset_version"].startswith("sha256:")
    assert versioned["execution_available"] is False

    preflight_response = client.get(f"/data-catalog/entries/{entry_id}/replay-preflight")
    assert preflight_response.status_code == 200
    preflight = preflight_response.json()
    assert preflight["status"] == "ready"
    assert preflight["can_replay"] is True
    assert preflight["replay_will_be_review_only"] is True
    assert preflight["execution_available"] is False

    replay_response = client.post(f"/data-catalog/entries/{entry_id}/replay")
    assert replay_response.status_code == 200
    replayed = replay_response.json()
    assert replayed["replay_created"] is True
    assert replayed["replay_snapshot"]["id"] != original_snapshot_id
    assert replayed["replay_snapshot"]["metadata_json"]["replay"] is True
    assert replayed["replay_catalog_entry"]["usable_for_trading"] is False
    assert replayed["replay_catalog_entry"]["contract_json"]["execution_available"] is False
    assert replayed["execution_available"] is False

    entries = client.get("/data-catalog/entries?dataset_type=csv_holdings").json()
    assert len(entries) == 2
    assert any(entry["source"].endswith(":replay") for entry in entries)


def test_csv_trade_import_records_history_without_upserting_positions(client: TestClient) -> None:
    response = client.post(
        "/imports/csv",
        json={
            "import_type": "trades",
            "csv_text": TRADES_CSV,
            "source_name": "demo_trade_csv",
            "source_ref": "demo_csv/trades.csv",
            "persist_positions": True,
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["rows_imported"] == 2
    assert payload["positions_upserted"] == 0
    assert payload["snapshot"]["snapshot_type"] == "csv_trades"
    assert payload["snapshot"]["metadata_json"]["execution_available"] is False
    assert payload["catalog_entry"]["dataset_type"] == "csv_trades"
    assert payload["catalog_entry"]["usable_for_trading"] is False

    positions = client.get("/positions").json()
    assert positions == []


def test_csv_import_rejects_secret_like_columns(client: TestClient) -> None:
    response = client.post(
        "/imports/csv",
        json={
            "import_type": "holdings",
            "csv_text": "asset_symbol,quantity,api_key\nAAPL,1,should-not-be-here\n",
        },
    )

    assert response.status_code == 422
    assert "secret-like" in response.json()["detail"]
