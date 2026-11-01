from datetime import datetime
from datetime import timedelta
from datetime import timezone

from fastapi.testclient import TestClient


def test_founder_daily_use_alpha_open_close_and_drilldown(client: TestClient) -> None:
    onboarding = client.get("/daily-use/onboarding?user_id=founder").json()
    assert onboarding["status"] == "incomplete"
    assert onboarding["execution_available"] is False

    updated = client.post(
        "/daily-use/onboarding?user_id=founder",
        json={
            "workspace_goal": "Review read-only portfolio evidence daily.",
            "risk_boundary_acknowledged": True,
            "read_only_data_plan": "Verify binance_spot_readonly privately.",
            "daily_review_time": "09:00",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "ready"

    due_at = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    reminder_response = client.post(
        "/daily-use/reminders",
        json={
            "user_id": "founder",
            "title": "Open read-only evidence packet",
            "reminder_type": "manual",
            "due_at": due_at,
            "priority": "high",
            "payload_json": {"workflow": "founder_daily_use_alpha"},
        },
    )
    assert reminder_response.status_code == 201
    reminder = reminder_response.json()

    daily_open = client.post("/daily-use/daily-open?user_id=founder")
    assert daily_open.status_code == 200
    assert daily_open.json()["execution_available"] is False
    assert daily_open.json()["queue_summary"]["high_priority_count"] >= 1

    drilldown = client.get(f"/daily-use/drilldown/reminder:{reminder['id']}?user_id=founder")
    assert drilldown.status_code == 200
    assert drilldown.json()["queue_item"]["related_entity_type"] == "Reminder"
    assert drilldown.json()["evidence"][0]["type"] == "reminder"

    daily_close = client.post("/daily-use/daily-close?user_id=founder", json={"reflection": "No execution action taken."})
    assert daily_close.status_code == 200
    assert daily_close.json()["execution_available"] is False
    assert daily_close.json()["review_json"]["reflection"] == "No execution action taken."


def test_local_cleanup_dismisses_only_e2e_reminders(client: TestClient) -> None:
    due_at = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    e2e = client.post(
        "/daily-use/reminders",
        json={
            "user_id": "cleanup-user",
            "title": "E2E guided task should not stay in a real local queue",
            "reminder_type": "manual",
            "due_at": due_at,
            "priority": "high",
            "payload_json": {"source": "local-self-use"},
        },
    ).json()
    normal = client.post(
        "/daily-use/reminders",
        json={
            "user_id": "cleanup-user",
            "title": "Review real local portfolio",
            "reminder_type": "manual",
            "due_at": due_at,
            "priority": "high",
            "payload_json": {"source": "user"},
        },
    ).json()

    response = client.post("/daily-use/local-cleanup/e2e-artifacts?user_id=cleanup-user", json={})
    assert response.status_code == 200
    assert response.json()["dismissed_reminders"] == 1
    assert response.json()["execution_available"] is False

    reminders = client.get("/daily-use/reminders?user_id=cleanup-user&limit=10").json()
    statuses = {item["id"]: item["status"] for item in reminders}
    assert statuses[e2e["id"]] == "dismissed"
    assert statuses[normal["id"]] == "pending"


def test_local_handoff_packet_exports_self_use_state_without_unlocking_execution(client: TestClient) -> None:
    start = client.post(
        "/daily-use/local-start?user_id=handoff-user",
        json={
            "data_mode": "simulation",
            "risk_boundary_acknowledged": True,
            "daily_review_time": "20:30",
            "workspace_goal": "daily_investment_review",
        },
    )
    assert start.status_code == 200
    client.post("/daily-use/scheduler-tick?user_id=handoff-user", json={"action": "refresh_reminders"})

    response = client.post("/daily-use/local-handoff-packet?user_id=handoff-user")
    assert response.status_code == 200
    packet = response.json()
    assert packet["packet_type"] == "local_self_use_handoff"
    assert packet["artifact_id"]
    assert packet["contains_secrets"] is False
    assert packet["execution_available"] is False
    assert packet["production_capability"] is False
    assert "不会自动实盘" in packet["safe_boundaries"]
    assert any(item["label"] == "启动后端" for item in packet["local_commands"])
    assert packet["today_queue"]["total_actions"] >= 0
    assert packet["next_action"]["route"].startswith("/?module=")

    exports = client.get("/daily-use/exports?user_id=handoff-user").json()
    assert any(item["id"] == packet["artifact_id"] and item["export_type"] == "local_self_use_handoff" for item in exports)


def test_investment_workflow_status_guides_local_loop_without_execution(client: TestClient) -> None:
    start = client.post(
        "/daily-use/local-start?user_id=workflow-user",
        json={
            "data_mode": "simulation",
            "risk_boundary_acknowledged": True,
            "daily_review_time": "20:30",
            "workspace_goal": "daily_investment_review",
        },
    )
    assert start.status_code == 200

    response = client.get("/daily-use/investment-workflow-status?user_id=workflow-user")
    assert response.status_code == 200
    payload = response.json()
    assert payload["execution_available"] is False
    assert payload["total_count"] == 5
    assert payload["progress_pct"] >= 0
    assert payload["next_action"]["route"].startswith("/?module=")
    assert "不会自动实盘" in payload["safe_boundary"]
    assert [step["key"] for step in payload["steps"]] == [
        "holdings",
        "thesis",
        "plan",
        "risk_review",
        "approval_draft",
    ]


def test_trusted_ledger_reports_and_repair_workflow(client: TestClient) -> None:
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
            "user_id": "ledger-user",
            "provider": "demo_broker_statement",
            "account_label": "Demo Broker Statement",
            "source_ref": "phase-development-test",
            "csv_text": csv_text,
        },
    )
    assert import_response.status_code == 201

    normalization = client.get("/ledger/statement-normalization-report?user_id=ledger-user")
    assert normalization.status_code == 200
    assert normalization.json()["normalized_entries_count"] == 5
    assert normalization.json()["execution_available"] is False

    reconcile = client.post("/ledger/reconcile/extended?user_id=ledger-user")
    assert reconcile.status_code == 201

    repair = client.post("/ledger/repair-workflow?user_id=ledger-user")
    assert repair.status_code == 201
    assert repair.json()["status"] == "ready_for_review"
    assert repair.json()["tasks"]
    assert repair.json()["execution_available"] is False

    promotion = client.get("/ledger/data-promotion-report?user_id=ledger-user")
    assert promotion.status_code == 200
    assert promotion.json()["can_unlock_order_approval"] is False
    assert {stage["stage"] for stage in promotion.json()["stages"]} == {"raw", "reviewed", "trusted"}


def test_phase_development_summary_exposes_nine_safe_slices(client: TestClient) -> None:
    response = client.get("/phase-development/summary?user_id=default-user")
    assert response.status_code == 200
    payload = response.json()
    assert payload["phases_total"] == 9
    assert payload["developed_safe_slices"] == 9
    assert payload["production_capability"] is False
    assert payload["execution_available"] is False
    assert all(phase["execution_available"] is False for phase in payload["phases"])

    readonly = client.get("/phase-development/real_readonly_data_proof?user_id=default-user")
    assert readonly.status_code == 200
    assert readonly.json()["evidence_packet"]["provider"] == "binance_spot_readonly"
    assert readonly.json()["real_broker_call_allowed"] is False


def test_phase_development_operations_remain_review_only(client: TestClient) -> None:
    verify = client.post("/phase-development/real-readonly-data-proof/binance-private-verify?user_id=operator")
    assert verify.status_code == 200
    assert verify.json()["execution_available"] is False
    assert verify.json()["production_capability"] is False

    research = client.post(
        "/phase-development/research-evidence/configure?user_id=operator",
        json={
            "llm_allowlist": ["openai:gpt-4.1-mini"],
            "credential_reference": "secretref:openai-readonly",
            "structured_eval": {"citations_required": True, "thesis_delta_required": True},
        },
    )
    assert research.status_code == 200
    assert research.json()["evidence_packet"]["configured_llm_allowlist"] == ["openai:gpt-4.1-mini"]
    assert research.json()["evidence_packet"]["configured_secret_reference"] == "secretref:openai-readonly"
    eval_packet = client.get("/phase-development/research-evidence/eval?user_id=operator")
    assert eval_packet.status_code == 200
    assert eval_packet.json()["execution_available"] is False
    assert eval_packet.json()["eval_artifact_id"]
    eval_history = client.get("/phase-development/research-evidence/eval-history?user_id=operator")
    assert eval_history.status_code == 200
    assert eval_history.json()["total"] == 1
    assert eval_history.json()["items"][0]["thesis_delta"]

    beta = client.post(
        "/phase-development/private-beta-foundation/checklist?user_id=operator",
        json={"auth": True, "rbac": True, "secrets": True, "monitoring": True, "backups": True, "admin_console": True},
    )
    assert beta.status_code == 200
    assert beta.json()["execution_available"] is False
    assert beta.json()["evidence_packet"]["admin_console_checklist"]["admin_console"] is True

    traction = client.post(
        "/phase-development/traction-loop/configure?user_id=operator",
        json={"waitlist_enabled": True, "activation_analytics": ["daily_open"], "pricing_config": {"plan": "private_beta"}, "data_room_export": True},
    )
    assert traction.status_code == 200
    assert traction.json()["execution_available"] is False
    assert traction.json()["evidence_packet"]["loop_config"]["data_room_export"] is True

    sandbox = client.post(
        "/phase-development/broker-sandbox-proof/state?user_id=operator",
        json={"state": "validated", "idempotency_key": "sandbox-proof-001", "external_order_id": None},
    )
    assert sandbox.status_code == 200
    assert sandbox.json()["evidence_packet"]["production_execution_allowed"] is False
    assert sandbox.json()["evidence_packet"]["idempotency_key"] == "sandbox-proof-001"

    pilot = client.post(
        "/phase-development/controlled-pilot/gates?user_id=operator",
        json={
            "pilot_legal_approval": {"approved": True},
            "pilot_ops_approval": {"approved": True},
            "pilot_allowlist": {"enabled": True},
            "pilot_limits": {"configured": True},
            "pilot_monitoring": {"enabled": True},
            "pilot_rollback": {"ready": True},
            "pilot_kill_switch": {"enabled": True},
        },
    )
    assert pilot.status_code == 200
    assert pilot.json()["evidence_packet"]["small_pilot_allowed"] is False
    assert all(pilot.json()["evidence_packet"]["gates"].values())
    assert "dex_swap" in pilot.json()["evidence_packet"]["forbidden_until_release"]


def test_private_verify_records_only_redacted_evidence_references(client: TestClient) -> None:
    response = client.post(
        "/phase-development/real-readonly-data-proof/binance-private-verify?user_id=evidence-user",
        json={
            "permission_screenshot_ref": "artifact://binance/permission-redacted.png",
            "withdrawal_disabled_proof_ref": "artifact://binance/withdrawal-disabled-redacted.png",
            "verification_environment": "private",
        },
    )
    assert response.status_code == 200
    assert response.json()["evidence_refs"]["verification_environment"] == "private"
    assert response.json()["execution_available"] is False

    rejected = client.post(
        "/phase-development/real-readonly-data-proof/binance-private-verify?user_id=evidence-user",
        json={"api_secret": "must-not-be-stored"},
    )
    assert rejected.status_code == 422


def test_private_verify_cannot_report_verified_without_required_external_proofs(client: TestClient) -> None:
    response = client.post(
        "/phase-development/real-readonly-data-proof/binance-private-verify?user_id=evidence-user",
        json={"verification_environment": "private"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] != "verified_private_readonly"
    if payload["status"] != "missing_connection":
        assert "permission_screenshot_ref_required" in payload["proof_blockers"]
        assert "withdrawal_disabled_proof_ref_required" in payload["proof_blockers"]


def test_risk_drilldown_exposes_decision_evidence_links(client: TestClient) -> None:
    response = client.get("/phase-development/portfolio-risk-terminal/drilldown/account?user_id=default-user")
    assert response.status_code == 200
    assert set(response.json()["deep_links"]) == {"positions", "theses", "ledger", "today_queue"}
    assert response.json()["execution_available"] is False


def test_ibkr_private_verification_requires_proofs_before_gateway_call(client: TestClient) -> None:
    setup = client.post(
        "/data-sources/connections/read-only-setup",
        json={
            "provider": "ibkr_readonly",
            "account_label": "proof-gated",
            "credentials_ref": "secretref:IBKR_PROOF_GATED_SESSION",
            "config_json": {"gateway_host": "127.0.0.1", "gateway_port": 5000},
        },
    )
    assert setup.status_code == 201

    response = client.post(
        "/phase-development/real-readonly-data-proof/ibkr-private-verify?user_id=proof-gated-user",
        json={"verification_environment": "private_local"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "verification_blocked"
    assert set(payload["proof_blockers"]) == {
        "gateway_session_proof_ref_required",
        "read_only_boundary_proof_ref_required",
    }
    assert payload["sync_result"] is None
    assert payload["proof_checks"]["snapshot_recorded"] is False
    assert payload["execution_available"] is False


def test_sandbox_state_machine_is_idempotent_and_rejects_skips(client: TestClient) -> None:
    first = client.post(
        "/phase-development/broker-sandbox-proof/state?user_id=sandbox-state-user",
        json={"state": "validated", "idempotency_key": "sandbox-state-001"},
    )
    assert first.status_code == 200
    repeated = client.post(
        "/phase-development/broker-sandbox-proof/state?user_id=sandbox-state-user",
        json={"state": "validated", "idempotency_key": "sandbox-state-001"},
    )
    assert repeated.status_code == 200
    skipped = client.post(
        "/phase-development/broker-sandbox-proof/state?user_id=sandbox-state-user",
        json={"state": "reconciled", "idempotency_key": "sandbox-state-002", "ledger_reconciliation_required": True},
    )
    assert skipped.status_code == 422


def test_ledger_repair_statement_row_detail_and_rerun(client: TestClient) -> None:
    csv_text = "\n".join(
        [
            "type,symbol,side,quantity,price,cash_delta,fee,currency,occurred_at,account",
            "deposit,,,,,10000,0,USD,2026-06-01T00:00:00Z,Demo Broker Statement",
            "buy,AAPL,buy,5,100,-500,0,USD,2026-06-02T00:00:00Z,Demo Broker Statement",
        ]
    )
    import_response = client.post(
        "/ledger/statement-imports",
        json={
            "user_id": "row-user",
            "provider": "demo_broker_statement",
            "account_label": "Demo Broker Statement",
            "source_ref": "row-detail-test",
            "csv_text": csv_text,
        },
    )
    assert import_response.status_code == 201
    batch_id = import_response.json()["batch"]["id"]

    row_detail = client.get(f"/ledger/statement-imports/{batch_id}/rows/2?user_id=row-user")
    assert row_detail.status_code == 200
    assert row_detail.json()["status"] == "imported"
    assert row_detail.json()["normalized_entry"]["entry_type"] == "external_trade"

    rerun = client.post("/ledger/repair-workflow/rerun-reconciliation?user_id=row-user")
    assert rerun.status_code == 201
    assert rerun.json()["execution_available"] is False


def test_portfolio_risk_anomaly_enters_today_queue(client: TestClient) -> None:
    connection_response = client.post(
        "/data-sources/connections",
        json={
            "name": "Risk Read-only Sample",
            "provider": "cex_readonly",
            "source_type": "exchange_account",
            "mode": "read_only",
            "config_json": {"exchange": "binance", "account_label": "risk"},
        },
    )
    assert connection_response.status_code == 201
    connection = connection_response.json()
    sync_response = client.post(
        f"/data-sources/connections/{connection['id']}/sync-account",
        json={
            "sample_payload": {
                "as_of": "2026-06-13T10:00:00Z",
                "account": {"account_id": "risk-main", "label": "risk", "account_type": "exchange_account", "base_currency": "USD"},
                "positions": [
                    {
                        "symbol": "RISK",
                        "name": "Risk Concentration Inc.",
                        "asset_type": "stock",
                        "market": "US",
                        "venue": "NASDAQ",
                        "currency": "USD",
                        "quantity": 10,
                        "average_cost": 100,
                        "market_price": 100,
                    }
                ],
                "balances": [],
                "orders": [],
            }
        },
    )
    assert sync_response.status_code == 201
    queue = client.get("/daily-use/action-queue?user_id=default-user&source=portfolio_risk")
    assert queue.status_code == 200
    assert queue.json()["actions"][0]["action_type"] == "review_portfolio_risk"
