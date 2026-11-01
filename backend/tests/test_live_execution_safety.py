from fastapi.testclient import TestClient

from test_paper_execution import create_approved_draft


def test_live_execution_config_health_check_fails_closed_and_rejects_raw_secret(client: TestClient) -> None:
    rejected = client.post(
        "/live-execution/configs",
        json={"exchange_type": "ibkr", "api_key_ref": "sk-live-inline-secret", "label": "Raw secret"},
    )
    assert rejected.status_code == 422

    created = client.post(
        "/live-execution/configs",
        json={"exchange_type": "ibkr", "api_key_ref": "env:IBKR_READONLY_KEY_REF", "label": "IBKR reference"},
    )
    assert created.status_code == 201
    config = created.json()
    assert config["is_active"] is True
    assert config["api_key_ref"] == "env:IBKR_READONLY_KEY_REF"

    health = client.post(f"/live-execution/configs/{config['id']}/health-check")
    assert health.status_code == 200
    payload = health.json()
    assert payload["connected"] is False
    assert payload["latency_ms"] == 0
    assert "fail closed" in payload["error"]

    audit_logs = client.get("/audit-logs").json()
    actions = {log["action"] for log in audit_logs}
    assert "live_execution_config.created" in actions
    assert "broker_state_check.fail_closed" in actions


def test_prepare_live_execution_blocks_by_default_even_for_approved_draft(client: TestClient) -> None:
    draft = create_approved_draft(client)

    response = client.post("/live-execution/prepare", json={"order_draft_id": draft["id"]})

    assert response.status_code == 200
    payload = response.json()
    assert payload["passed"] is False
    assert "global_live_trading_disabled" in payload["blocking_reasons"]
    assert "live_execution_disabled" in payload["blocking_reasons"]
    assert "live_execution_adapter_disabled" in payload["blocking_reasons"]
    assert "account_not_live_mode" in payload["blocking_reasons"]
    assert "broker_state_not_connected" in payload["blocking_reasons"]
    assert "dry_run_only_mode" in payload["warnings"]


def test_live_approval_is_blocked_when_readiness_fails(client: TestClient) -> None:
    draft = create_approved_draft(client)

    response = client.post(
        "/live-execution/approve",
        json={
            "order_draft_id": draft["id"],
            "approver_id": "human-user",
            "decision_reason": "Try live approval safely.",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["approved"] is False
    assert "global_live_trading_disabled" in payload["details"]["blocking_reasons"]

    audit_logs = client.get("/audit-logs").json()
    actions = {log["action"] for log in audit_logs}
    assert "live_execution.approval_blocked" in actions


def test_execute_live_order_records_blocked_attempt_without_fill_or_position_change(client: TestClient) -> None:
    draft = create_approved_draft(client)

    response = client.post(
        "/live-execution/execute",
        json={
            "order_draft_id": draft["id"],
            "approver_id": "human-user",
            "decision_reason": "Controlled live execution dry run.",
            "force_fill_price": "225.12",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "blocked"
    assert payload["filled_quantity"] == "0"
    assert payload["fill_price"] == "225.12"
    assert "real_live_execution_not_implemented" in payload["blocking_reasons"]
    assert payload["rollback_plan"]["external_order_id"] is None
    assert payload["rollback_plan"]["portfolio_reversal_required"] is False

    refreshed_draft = client.get(f"/orders/drafts/{draft['id']}").json()
    assert refreshed_draft["execution_status"] == "live_blocked"

    paper_executions = client.get("/paper-executions").json()
    assert paper_executions == []
    positions = client.get("/positions").json()
    assert positions == []

    history = client.get("/live-execution/history").json()
    assert len(history) == 1
    assert history[0]["order_draft_id"] == draft["id"]
    assert history[0]["status"] == "blocked"

    journal_entries = client.get("/trade-journal-entries").json()
    assert len(journal_entries) == 1
    assert "Live execution request blocked" in journal_entries[0]["notes"]

    audit_logs = client.get("/audit-logs").json()
    actions = {log["action"] for log in audit_logs}
    assert "live_execution.blocked" in actions
    assert "trade_journal.created_from_live_execution_blocked" in actions


def test_live_execution_sandbox_run_does_not_mutate_draft_or_create_execution(client: TestClient) -> None:
    draft = create_approved_draft(client)

    response = client.post(
        "/live-execution/sandbox-run",
        json={
            "order_draft_id": draft["id"],
            "approver_id": "human-user",
            "decision_reason": "Sandbox dry-run only.",
            "force_fill_price": "225.12",
            "scenario_label": "stage_8_sandbox",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "blocked"
    assert payload["sandbox_only"] is True
    assert payload["execution_available"] is False
    assert payload["real_broker_call_performed"] is False
    assert payload["requested_order"]["requested_quantity"] == "1"
    assert payload["requested_order"]["requested_price"] == "225.12"
    assert payload["broker_submission"]["status"] == "not_submitted"
    assert payload["broker_submission"]["external_order_id"] is None
    assert "global_live_trading_disabled" in payload["blocking_reasons"]
    assert "broker_state_not_connected" in payload["blocking_reasons"]

    refreshed_draft = client.get(f"/orders/drafts/{draft['id']}").json()
    assert refreshed_draft["execution_status"] == draft["execution_status"]
    assert client.get("/live-execution/history").json() == []
    assert client.get("/paper-executions").json() == []
    assert client.get("/positions").json() == []

    audit_logs = client.get("/audit-logs").json()
    assert any(log["action"] == "live_execution.sandbox_run" for log in audit_logs)


def test_live_execution_sandbox_certification_preserves_dry_run_boundary(client: TestClient) -> None:
    draft = create_approved_draft(client)

    response = client.post(
        "/live-execution/sandbox-certification",
        json={
            "order_draft_id": draft["id"],
            "approver_id": "human-user",
            "force_fill_price": "225.12",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "blocked"
    assert payload["certification_level"] == "dry_run_only"
    assert payload["execution_available"] is False
    assert payload["real_broker_call_allowed"] is False
    assert payload["real_broker_call_performed"] is False
    assert payload["external_order_id"] is None
    assert payload["broker_submission"]["status"] == "not_submitted"
    assert "global_live_trading_disabled" in payload["blockers"]
    assert payload["rollback_plan"]["external_order_id"] is None

    refreshed_draft = client.get(f"/orders/drafts/{draft['id']}").json()
    assert refreshed_draft["execution_status"] == draft["execution_status"]
    assert client.get("/live-execution/history").json() == []
    audit_logs = client.get("/audit-logs").json()
    assert any(log["action"] == "live_execution.sandbox_certification_checked" for log in audit_logs)


def test_small_pilot_readiness_checks_size_and_blocks_without_live_readiness(client: TestClient) -> None:
    draft = create_approved_draft(client, notional=50)

    response = client.post(
        "/live-execution/small-pilot-readiness",
        json={
            "order_draft_id": draft["id"],
            "approver_id": "human-user",
            "max_notional": "100",
            "force_fill_price": "50",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    checks = {check["key"]: check for check in payload["checks"]}
    assert payload["pilot_status"] == "blocked"
    assert payload["execution_available"] is False
    assert payload["real_broker_call_allowed"] is False
    assert payload["estimated_notional"] == "50"
    assert payload["max_notional"] == "100"
    assert checks["pilot_size"]["status"] == "ok"
    assert checks["human_approval"]["status"] == "ok"
    assert checks["live_readiness"]["status"] == "block"
    assert "global_live_trading_disabled" in payload["blockers"]


def test_small_pilot_approval_packet_is_unsigned_and_not_submitted(client: TestClient) -> None:
    draft = create_approved_draft(client, notional=50)

    response = client.post(
        "/live-execution/small-pilot-approval-packet",
        json={
            "order_draft_id": draft["id"],
            "approver_id": "human-user",
            "max_notional": "100",
            "force_fill_price": "50",
        },
    )

    assert response.status_code == 200
    packet = response.json()
    assert packet["packet_status"] == "blocked"
    assert packet["unsigned_packet"] is True
    assert packet["requires_human_signature"] is True
    assert packet["signature_available"] is False
    assert packet["broker_submission_status"] == "not_submitted"
    assert packet["external_order_id"] is None
    assert packet["execution_available"] is False
    assert packet["real_broker_call_allowed"] is False
    assert "global_live_trading_disabled" in packet["blockers"]
    assert packet["sandbox_certification"]["real_broker_call_performed"] is False
    assert client.get("/live-execution/history").json() == []

    audit_logs = client.get("/audit-logs").json()
    assert any(log["action"] == "live_execution.small_pilot_approval_packet_created" for log in audit_logs)

    refreshed_draft = client.get(f"/orders/drafts/{draft['id']}").json()
    assert refreshed_draft["execution_status"] == draft["execution_status"]
    assert client.get("/live-execution/history").json() == []
    assert client.get("/positions").json() == []

    audit_logs = client.get("/audit-logs").json()
    assert any(log["action"] == "live_execution.small_pilot_readiness_checked" for log in audit_logs)


def test_broker_sandbox_proof_packet_exports_state_machine_without_execution(client: TestClient) -> None:
    draft = create_approved_draft(client, notional=50)

    response = client.post(
        "/live-execution/broker-sandbox-proof-packet",
        json={
            "order_draft_id": draft["id"],
            "approver_id": "human-user",
            "force_fill_price": "50",
        },
    )

    assert response.status_code == 200
    packet = response.json()
    assert packet["packet_type"] == "broker_sandbox_proof_packet"
    assert packet["artifact_id"]
    assert packet["packet_status"] == "blocked"
    assert packet["contains_secrets"] is False
    assert packet["execution_available"] is False
    assert packet["real_broker_call_allowed"] is False
    assert packet["real_broker_call_performed"] is False
    assert packet["production_execution_allowed"] is False
    assert packet["external_order_id"] is None
    assert packet["idempotency"]["required"] is True
    assert packet["state_machine"][0]["state"] == "draft_approved"
    assert packet["broker_reconciliation"]["external_order_id"] is None
    assert "global_live_trading_disabled" in packet["blockers"]
    assert "no real broker submission" in packet["safe_boundary"].lower()
    assert client.get("/live-execution/history").json() == []
    assert client.get("/positions").json() == []

    audit_logs = client.get("/audit-logs").json()
    assert any(log["action"] == "live_execution.broker_sandbox_proof_packet_created" for log in audit_logs)


def test_small_pilot_readiness_blocks_oversized_draft(client: TestClient) -> None:
    draft = create_approved_draft(client, notional=250)

    response = client.post(
        "/live-execution/small-pilot-readiness",
        json={"order_draft_id": draft["id"], "max_notional": "100", "force_fill_price": "250"},
    )

    assert response.status_code == 200
    payload = response.json()
    checks = {check["key"]: check for check in payload["checks"]}
    assert payload["pilot_status"] == "blocked"
    assert checks["pilot_size"]["status"] == "block"
    assert "pilot_notional_exceeds_limit" in payload["blockers"]


def test_kill_switch_blocks_and_can_be_disengaged(client: TestClient) -> None:
    engage = client.post(
        "/kill-switch/engage",
        json={"reason": "Manual safety stop", "engaged_by": "human-user"},
    )
    assert engage.status_code == 201
    switch = engage.json()
    assert switch["disengaged_at"] is None

    active = client.get("/kill-switch/active")
    assert active.status_code == 200
    assert len(active.json()) == 1

    check = client.post("/kill-switch/check")
    assert check.status_code == 200
    assert check.json() == {"blocked": True, "reason": "Manual safety stop"}

    disengage = client.post("/kill-switch/disengage", json={"reason": "Manual reset"})
    assert disengage.status_code == 200
    assert disengage.json() == {"disengaged": True}

    assert client.get("/kill-switch/active").json() == []
    history = client.get("/kill-switch/history").json()
    assert len(history) == 1
    assert history[0]["id"] == switch["id"]
    assert history[0]["disengaged_at"] is not None

    audit_logs = client.get("/audit-logs").json()
    actions = {log["action"] for log in audit_logs}
    assert {"kill_switch.engaged", "kill_switch.disengaged"}.issubset(actions)
