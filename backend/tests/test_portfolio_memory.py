from fastapi.testclient import TestClient


def seed_mock_portfolio(client: TestClient) -> None:
    assert client.post("/mock/import-positions").status_code == 200
    assert client.post("/mock/update-quotes").status_code == 200


def test_total_equity_calculation(client: TestClient) -> None:
    seed_mock_portfolio(client)

    response = client.get("/portfolio/current")

    assert response.status_code == 200
    data = response.json()
    assert data["total_equity"] == 47645.44
    assert data["cash"] == 3750.0
    assert len(data["positions"]) == 9
    assert round(sum(position["market_value"] for position in data["positions"]), 2) == data["total_equity"]


def test_allocation_calculation(client: TestClient) -> None:
    seed_mock_portfolio(client)

    allocation = client.get("/portfolio/daily-summary").json()["allocation"]

    assert allocation == {
        "stocks": 0.153,
        "crypto": 0.7683,
        "stablecoin": 0.0787,
        "cash": 0.0,
    }


def test_top_winners_and_losers(client: TestClient) -> None:
    seed_mock_portfolio(client)

    summary = client.get("/portfolio/daily-summary").json()

    assert [winner["symbol"] for winner in summary["top_winners"][:3]] == ["SPY", "AAPL", "NVDA"]
    assert summary["top_losers"] == []
    assert summary["daily_pnl"] == 0


def test_concentration_risk_detection(client: TestClient) -> None:
    seed_mock_portfolio(client)

    summary = client.get("/portfolio/daily-summary").json()
    risks = summary["concentration_risks"]

    assert risks
    assert risks[0]["symbol"] == "BTC"
    assert risks[0]["weight"] == 0.3314
    assert "Review concentrated positions before adding exposure." in summary["suggested_attention"]


def test_portfolio_snapshot_works(client: TestClient) -> None:
    seed_mock_portfolio(client)

    response = client.post("/portfolio/snapshot")

    assert response.status_code == 201
    snapshot = response.json()
    assert snapshot["total_value"] == 47645.44
    assert snapshot["cash_value"] == 3750.0
    assert snapshot["positions_value"] == 43895.44
    assert snapshot["snapshot_json"]["total_equity"] == 47645.44

    snapshots = client.get("/portfolio/snapshots").json()
    assert len(snapshots) == 1
