import pytest
from fastapi.testclient import TestClient

from app.adapters.mock import MockStockBrokerAdapter


def test_mock_stock_account_import(client: TestClient) -> None:
    response = client.post("/mock/import-accounts")

    assert response.status_code == 200
    assert set(response.json()["accounts"]) == {
        "stock_paper_account",
        "crypto_paper_account",
        "onchain_watch_wallet",
    }

    accounts_response = client.get("/accounts")
    accounts = accounts_response.json()
    assert accounts_response.status_code == 200
    assert len(accounts) == 3
    assert all(account["live_trading_enabled"] is False for account in accounts)


def test_mock_crypto_balances_import(client: TestClient) -> None:
    response = client.post("/mock/import-positions")

    assert response.status_code == 200
    assert response.json()["positions"] == 9

    positions_response = client.get("/positions")
    assert positions_response.status_code == 200
    positions = positions_response.json()
    assert len(positions) == 9

    accounts_by_id = {account["id"]: account for account in client.get("/accounts").json()}
    crypto_positions = [
        position for position in positions if accounts_by_id[position["account_id"]]["name"] == "crypto_paper_account"
    ]
    assert len(crypto_positions) == 4
    assert {position["market_value"] > 0 for position in crypto_positions} == {True}


def test_mock_quote_update(client: TestClient) -> None:
    client.post("/mock/import-positions")

    response = client.post("/mock/update-quotes")

    assert response.status_code == 200
    assert response.json()["quotes"] == 7

    positions = client.get("/positions").json()
    assert all(position["market_price"] > 0 for position in positions)
    assert all(position["market_value"] > 0 for position in positions)

    audit_logs = client.get("/audit-logs").json()
    quote_updates = [audit_log for audit_log in audit_logs if audit_log["action"] == "mock_quote.updated"]
    assert len(quote_updates) == 7


def test_mock_place_order_blocked() -> None:
    adapter = MockStockBrokerAdapter()

    with pytest.raises(NotImplementedError):
        adapter.place_order(order_draft={"id": "draft-1"})
