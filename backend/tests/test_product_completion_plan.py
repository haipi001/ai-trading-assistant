from fastapi.testclient import TestClient

from test_backtests import insert_candles
from test_live_execution_safety import create_approved_draft
from test_risk_approval import create_asset
from test_route_parity_safe_lab import create_playbook


def test_plan_1_certified_sync_plan_is_sample_only(client: TestClient) -> None:
    setup = client.post(
        "/data-sources/connections/read-only-setup",
        json={
            "provider": "cex_readonly",
            "account_label": "main",
            "credentials_ref": "secretref:CEX_READONLY",
            "config_json": {
                "exchange": "binance",
                "sample_snapshot": {
                    "positions": [{"symbol": "BTC", "quantity": "0.1", "market_value": "5000"}],
                    "balances": [{"currency": "USDT", "cash_value": "1000"}],
                    "orders": [],
                },
            },
        },
    )
    assert setup.status_code == 201

    response = client.post(f"/data-sources/connections/{setup.json()['connection']['id']}/certified-sync-plan")

    assert response.status_code == 200
    packet = response.json()
    assert packet["status"] == "ready_for_sample_sync"
    assert packet["sample_only"] is True
    assert packet["execution_available"] is False
    assert packet["real_broker_call_allowed"] is False


def test_plan_2_contract_enforcement_blocks_missing_required_data(client: TestClient) -> None:
    response = client.get("/data-catalog/contract-enforcement-report?decision_scope=research")

    assert response.status_code == 200
    packet = response.json()
    assert packet["enforcement_status"] == "blocked"
    assert packet["execution_available"] is False
    assert "market_quotes:missing_required_dataset" in packet["blockers"]


def test_plan_3_ledger_reconciliation_workbench_is_review_only(client: TestClient) -> None:
    response = client.get("/ledger/reconciliation-workbench")

    assert response.status_code == 200
    packet = response.json()
    assert packet["workbench_status"] == "blocked"
    assert packet["can_unlock_order_approval"] is False
    assert packet["execution_available"] is False


def test_plan_4_frontend_contract_surfaces_are_backed_by_api(client: TestClient) -> None:
    response = client.get("/ops/product-stability-packet")

    assert response.status_code == 200
    packet = response.json()
    assert packet["execution_available"] is False
    assert any(check["key"] == "execution_boundary" for check in packet["checks"])


def test_plan_5_review_action_plan_keeps_playbook_changes_manual(client: TestClient) -> None:
    response = client.get("/workflows/review-action-plan")

    assert response.status_code == 200
    packet = response.json()
    assert packet["execution_available"] is False
    assert any("Do not apply playbook changes automatically" in action for action in packet["next_actions"])


def test_plan_6_backtest_research_packet_does_not_create_orders(client: TestClient) -> None:
    asset = create_asset(client)
    playbook = create_playbook(client)
    insert_candles(asset["id"], [10, 10, 10, 12, 14, 13, 11, 9])
    created = client.post(
        "/backtest-runs",
        json={
            "strategy_playbook_id": playbook["id"],
            "name": "Product plan research packet",
            "date_from": "2026-01-01",
            "date_to": "2026-01-08",
            "initial_capital": "100000",
            "parameters_json": {"asset_id": asset["id"], "timeframe": "1d", "short_window": 2, "long_window": 3},
        },
    )
    assert created.status_code == 201
    assert client.post(f"/backtest-runs/{created.json()['id']}/start").status_code == 200

    response = client.post(f"/backtest-runs/{created.json()['id']}/research-packet")

    assert response.status_code == 200
    packet = response.json()
    assert packet["packet_status"] == "ready_for_research_review"
    assert packet["order_creation_allowed"] is False
    assert packet["execution_available"] is False
    assert client.get("/orders/drafts").json() == []


def test_plan_7_beta_invitation_packet_never_sends_invites(client: TestClient) -> None:
    response = client.get("/beta/invitation-packet")

    assert response.status_code == 200
    packet = response.json()
    assert packet["can_send_automatic_invites"] is False
    assert packet["deployment_triggered"] is False
    assert packet["execution_available"] is False


def test_plan_8_product_stability_packet_never_deploys_or_restores(client: TestClient) -> None:
    response = client.get("/ops/product-stability-packet")

    assert response.status_code == 200
    packet = response.json()
    assert packet["deployment_triggered"] is False
    assert packet["restore_executed"] is False
    assert packet["execution_available"] is False


def test_plan_9_broker_reconciliation_plan_stays_before_submission(client: TestClient) -> None:
    draft = create_approved_draft(client, notional=50)

    response = client.post(
        "/live-execution/broker-reconciliation-plan",
        json={"order_draft_id": draft["id"], "approver_id": "human-user", "force_fill_price": "50"},
    )

    assert response.status_code == 200
    packet = response.json()
    assert packet["execution_available"] is False
    assert packet["real_broker_call_allowed"] is False
    assert packet["external_order_id"] is None
    assert client.get("/live-execution/history").json() == []


def test_plan_10_small_pilot_go_no_go_is_unsigned_and_not_submitted(client: TestClient) -> None:
    draft = create_approved_draft(client, notional=50)

    response = client.post(
        "/live-execution/small-pilot-go-no-go",
        json={"order_draft_id": draft["id"], "approver_id": "human-user", "max_notional": "100", "force_fill_price": "50"},
    )

    assert response.status_code == 200
    packet = response.json()
    assert packet["decision"] == "NO_GO"
    assert packet["requires_human_signature"] is True
    assert packet["signature_available"] is False
    assert packet["broker_submission_status"] == "not_submitted"
    assert packet["execution_available"] is False
    assert packet["real_broker_call_allowed"] is False
