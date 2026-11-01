from datetime import datetime
from datetime import timezone

from fastapi.testclient import TestClient

from app.services.ops_readiness import OpsReadinessService
from app.services.ops_readiness import check
from test_decision_narratives import create_thesis
from test_paper_execution import create_approved_draft
from test_paper_execution import create_strategy_playbook
from test_risk_approval import create_account
from test_risk_approval import create_asset


def test_ledger_sync_and_reconcile_from_positions_and_paper_execution(client: TestClient) -> None:
    asset = create_asset(client)
    account = create_account(client)
    draft = create_approved_draft(client, asset=asset, account=account, quantity=3, notional=None, limit_price=100)

    execute_response = client.post(
        f"/paper-executions/drafts/{draft['id']}/execute",
        json={"approver_id": "human-user", "fill_price": 100, "fee_bps": 0},
    )
    assert execute_response.status_code == 201

    sync_response = client.post("/ledger/sync?user_id=human-user")
    assert sync_response.status_code == 201
    sync_payload = sync_response.json()
    assert sync_payload["execution_available"] is False
    assert sync_payload["data_trust_status"] in {"blocked", "review_only", "trusted"}
    assert sync_payload["position_entries_created"] >= 1
    assert sync_payload["paper_entries_created"] == 1
    assert {entry["entry_type"] for entry in sync_payload["entries"]} >= {"position_snapshot", "paper_trade"}

    entries_response = client.get("/ledger/entries?user_id=human-user&limit=20")
    assert entries_response.status_code == 200
    entries = entries_response.json()
    assert any(entry["source_type"] == "paper_execution" for entry in entries)

    reconcile_response = client.post("/ledger/reconcile?user_id=human-user")
    assert reconcile_response.status_code == 201
    report = reconcile_response.json()
    assert report["execution_available"] is False
    assert report["data_trust_status"] in {"blocked", "review_only", "trusted"}
    assert report["run"]["status"] == "ok"
    assert report["run"]["breaks_count"] == 0
    assert report["breaks"] == []

    latest_response = client.get("/ledger/reconciliation/latest?user_id=human-user")
    assert latest_response.status_code == 200
    assert latest_response.json()["run"]["id"] == report["run"]["id"]

    workbench_response = client.get("/ledger/reconciliation-workbench?user_id=human-user")
    assert workbench_response.status_code == 200
    workbench = workbench_response.json()
    assert workbench["latest_reconciliation"]["run"]["id"] == report["run"]["id"]
    assert workbench["latest_reconciliation"]["breaks"] == []
    assert workbench["can_unlock_order_approval"] is False
    assert workbench["execution_available"] is False


def test_ledger_preflight_blocks_empty_ledger_sources(client: TestClient) -> None:
    response = client.get("/ledger/preflight?user_id=human-user")

    assert response.status_code == 200
    preflight = response.json()
    assert preflight["status"] == "block"
    assert preflight["data_trust_status"] == "blocked"
    assert preflight["can_sync"] is False
    assert preflight["can_reconcile"] is False
    assert preflight["execution_available"] is False
    checks = {check["key"]: check for check in preflight["checks"]}
    assert checks["data_trust"]["status"] == "block"
    assert checks["ledger_sources"]["status"] == "block"
    assert preflight["data_trust_report"]["decision_scope"] == "ledger"


def test_ledger_preflight_and_sync_use_review_only_account_trust(client: TestClient) -> None:
    create_response = client.post(
        "/data-sources/connections",
        json={
            "name": "Ledger Trust CEX Read-only",
            "provider": "cex_readonly",
            "source_type": "exchange_account",
            "mode": "read_only",
            "config_json": {"exchange": "binance", "account_label": "main"},
        },
    )
    assert create_response.status_code == 201
    connection = create_response.json()

    sync_account_response = client.post(
        f"/data-sources/connections/{connection['id']}/sync-account",
        json={
            "sample_payload": {
                "as_of": datetime.now(timezone.utc).isoformat(),
                "account": {"account_id": "ledger-cex-main", "label": "main", "base_currency": "USD"},
                "balances": [{"currency": "USD", "cash_value": 2500}],
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
    assert sync_account_response.status_code == 201

    preflight_response = client.get("/ledger/preflight?user_id=human-user")
    assert preflight_response.status_code == 200
    preflight = preflight_response.json()
    assert preflight["status"] == "warn"
    assert preflight["can_sync"] is True
    assert preflight["data_trust_status"] == "review_only"
    assert preflight["positions_count"] == 1

    ledger_sync_response = client.post("/ledger/sync?user_id=human-user")
    assert ledger_sync_response.status_code == 201
    ledger_sync = ledger_sync_response.json()
    assert ledger_sync["data_trust_status"] == "review_only"
    assert ledger_sync["position_entries_created"] == 1

    reconcile_response = client.post("/ledger/reconcile?user_id=human-user")
    assert reconcile_response.status_code == 201
    report = reconcile_response.json()
    assert report["data_trust_status"] == "review_only"
    assert report["run"]["summary_json"]["data_trust_status"] == "review_only"


def test_deep_review_queue_surfaces_thesis_draft_and_paper_next_actions(client: TestClient) -> None:
    asset = create_asset(client)
    account = create_account(client)
    playbook = create_strategy_playbook(client)
    thesis = create_thesis(client, asset["id"], playbook["id"])
    draft = create_approved_draft(client, asset=asset, account=account, quantity=1, notional=None, limit_price=100)

    response = client.get("/workflows/deep-review-queue?user_id=human-user&limit=20")

    assert response.status_code == 200
    queue = response.json()
    assert queue["execution_available"] is False
    assert queue["total_items"] >= 3
    item_types = {item["item_type"] for item in queue["items"]}
    assert "thesis_monitor_due" in item_types
    assert "missing_thesis_link" in item_types
    assert "approved_draft_waiting_paper" in item_types
    assert any(item["thesis_id"] == thesis["id"] for item in queue["items"])
    assert any(item["order_draft_id"] == draft["id"] for item in queue["items"])
    assert queue["blocked_count"] >= 1


def test_ops_restore_drill_records_safe_event_and_ci_preflight(monkeypatch, client: TestClient) -> None:
    monkeypatch.setattr(
        OpsReadinessService,
        "_redis_check",
        lambda self: check("redis", "Redis", "ok", "Redis ping skipped in unit test."),
    )
    backup_response = client.post("/daily-use/backup-manifest?user_id=default-user")
    assert backup_response.status_code == 201

    restore_response = client.post("/ops/restore-drill")

    assert restore_response.status_code == 201
    report = restore_response.json()
    assert report["execution_available"] is False
    assert report["status"] == "ok"
    assert report["latest_backup_artifact_id"] == backup_response.json()["id"]
    assert report["operational_event"]["event_type"] == "restore_drill"
    assert {step["key"] for step in report["restore_steps"]} >= {
        "backup_manifest",
        "database_restore_plan",
        "migration_check",
        "regression_check",
    }

    stability_response = client.get("/ops/stability-report")
    assert stability_response.status_code == 200
    stability = stability_response.json()
    checks = {item["key"]: item for item in stability["checks"]}
    assert checks["restore_drill"]["status"] == "ok"
    assert checks["ci"]["status"] == "ok"
    assert checks["monitoring"]["status"] in {"ok", "warn"}
    assert "git status --short" in stability["commands"]
