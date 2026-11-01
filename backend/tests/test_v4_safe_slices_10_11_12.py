from fastapi.testclient import TestClient

from app.services.ops_readiness import OpsReadinessService
from app.services.ops_readiness import check
from test_paper_execution import create_approved_draft
from test_risk_approval import create_account
from test_risk_approval import create_asset


def test_statement_import_and_extended_reconciliation_are_read_only(client: TestClient) -> None:
    csv_text = "\n".join(
        [
            "type,symbol,side,quantity,price,cash_delta,fee,currency,occurred_at,account",
            "deposit,,,,,10000,0,USD,2026-06-01T00:00:00Z,Demo Broker Statement",
            "buy,AAPL,buy,5,100,-500,0,USD,2026-06-02T00:00:00Z,Demo Broker Statement",
            "cash_balance,,,,,9500,0,USD,2026-06-03T00:00:00Z,Demo Broker Statement",
            "tax_lot,AAPL,buy,5,100,0,0,USD,2026-06-03T00:00:00Z,Demo Broker Statement",
            "split,AAPL,,0,0,0,0,USD,2026-06-04T00:00:00Z,Demo Broker Statement",
        ]
    )

    import_response = client.post(
        "/ledger/statement-imports",
        json={
            "user_id": "human-user",
            "provider": "demo_broker_statement",
            "account_label": "Demo Broker Statement",
            "source_ref": "unit-test-statement",
            "csv_text": csv_text,
        },
    )

    assert import_response.status_code == 201
    payload = import_response.json()
    assert payload["execution_available"] is False
    assert payload["batch"]["imported_count"] == 5
    assert payload["catalog_entry"]["usable_for_trading"] is False
    assert {entry["entry_type"] for entry in payload["ledger_entries"]} >= {
        "cash_movement",
        "external_trade",
        "cash_balance",
        "external_tax_lot",
        "corporate_action",
    }

    batches_response = client.get("/ledger/statement-imports?user_id=human-user")
    assert batches_response.status_code == 200
    assert batches_response.json()[0]["source_ref"] == "unit-test-statement"

    preflight_response = client.get("/ledger/preflight?user_id=human-user")
    assert preflight_response.status_code == 200
    preflight = preflight_response.json()
    assert [item["key"] for item in preflight["local_next_steps"]] == [
        "statement_import",
        "row_detail",
        "repair_assignment",
        "rerun_reconciliation",
    ]
    assert preflight["promotion_gate"]["can_unlock_order_approval"] is False
    assert preflight["promotion_gate"]["can_execute_trades"] is False
    assert preflight["promotion_gate"]["execution_available"] is False

    reconcile_response = client.post("/ledger/reconcile/extended?user_id=human-user")
    assert reconcile_response.status_code == 201
    report = reconcile_response.json()
    assert report["execution_available"] is False
    assert report["run"]["scope"] == "extended_ledger"
    assert report["run"]["status"] == "warn"
    assert report["run"]["summary_json"]["cash_balance_entries"] == 1
    assert {item["break_type"] for item in report["breaks"]} >= {
        "tax_lot_quantity_mismatch",
        "corporate_action_not_recorded",
    }
    assert "cash_balance_mismatch" not in {item["break_type"] for item in report["breaks"]}

    workbench_response = client.get("/ledger/reconciliation-workbench?user_id=human-user")
    assert workbench_response.status_code == 200
    workbench = workbench_response.json()
    assert workbench["promotion_gate"]["can_unlock_order_approval"] is False
    assert workbench["promotion_gate"]["can_execute_trades"] is False
    assert workbench["local_next_steps"][0]["key"] == "statement_import"


def test_deep_review_tasks_can_be_assigned_and_completed(client: TestClient) -> None:
    asset = create_asset(client)
    account = create_account(client)
    draft = create_approved_draft(client, asset=asset, account=account, quantity=1, notional=None, limit_price=100)

    queue_response = client.get("/workflows/deep-review-queue?user_id=human-user&limit=10")
    assert queue_response.status_code == 200
    item = queue_response.json()["items"][0]

    assign_response = client.post(
        "/workflows/deep-review-tasks",
        json={
            "user_id": "human-user",
            "queue_item_id": item["id"],
            "item_type": item["item_type"],
            "title": item["title"],
            "detail": item["detail"],
            "priority": item["priority"],
            "assignee_id": "human-user",
            "related_entity_type": item["related_entity_type"],
            "related_entity_id": item["related_entity_id"],
            "payload_json": {"order_draft_id": draft["id"], "execution_available": False},
        },
    )

    assert assign_response.status_code == 201
    task = assign_response.json()
    assert task["status"] == "open"
    assert task["queue_item_id"] == item["id"]

    assigned_queue = client.get("/workflows/deep-review-queue?user_id=human-user&limit=10").json()
    assigned_item = next(row for row in assigned_queue["items"] if row["id"] == item["id"])
    assert assigned_item["task_id"] == task["id"]
    assert assigned_item["assignment_status"] == "open"
    assert assigned_item["assignee_id"] == "human-user"

    complete_response = client.post(f"/workflows/deep-review-tasks/{task['id']}/complete?user_id=human-user")
    assert complete_response.status_code == 201
    assert complete_response.json()["status"] == "completed"


def test_production_targets_feed_ops_stability_report(monkeypatch, client: TestClient) -> None:
    monkeypatch.setattr(
        OpsReadinessService,
        "_redis_check",
        lambda self: check("redis", "Redis", "ok", "Redis ping skipped in unit test."),
    )

    for target_type in ["error_reporting", "backup_target", "secret_manager", "deployment"]:
        response = client.post(
            "/ops/production-targets",
            json={
                "target_type": target_type,
                "provider": "manual",
                "label": f"{target_type} target",
                "reference_key": f"secretref:{target_type}",
                "status": "configured",
                "metadata_json": {"source": "unit_test", "execution_available": False},
            },
        )
        assert response.status_code == 201
        assert response.json()["status"] == "configured"

    targets_response = client.get("/ops/production-targets")
    assert targets_response.status_code == 200
    assert len(targets_response.json()) == 4

    stability_response = client.get("/ops/stability-report")
    assert stability_response.status_code == 200
    checks = {item["key"]: item for item in stability_response.json()["checks"]}
    assert checks["production_targets"]["status"] == "ok"
