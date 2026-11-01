from datetime import datetime
from datetime import timedelta
from datetime import timezone

from fastapi.testclient import TestClient


def create_asset(client: TestClient) -> dict:
    response = client.post(
        "/assets",
        json={
            "symbol": "AAPL",
            "name": "Apple Inc.",
            "asset_type": "stock",
            "market": "US",
            "venue": "NASDAQ",
            "currency": "USD",
            "tradable": True,
            "manual_enabled": True,
            "auto_enabled": False,
            "risk_level": "medium",
        },
    )
    assert response.status_code == 201
    return response.json()


def test_watchlist_item_can_be_created_and_deactivated(client: TestClient) -> None:
    asset = create_asset(client)

    response = client.post(
        "/daily-use/watchlist",
        json={
            "user_id": "user-1",
            "symbol": "aapl",
            "priority": "high",
            "alert_rules_json": {"price_above": 250},
            "notes": "Daily focus name.",
        },
    )

    assert response.status_code == 201
    item = response.json()
    assert item["symbol"] == "AAPL"
    assert item["asset_id"] == asset["id"]
    assert item["priority"] == "high"
    assert item["is_active"] is True

    list_response = client.get("/daily-use/watchlist?user_id=user-1")
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1

    delete_response = client.delete(f"/daily-use/watchlist/{item['id']}")
    assert delete_response.status_code == 200
    assert delete_response.json()["is_active"] is False
    assert client.get("/daily-use/watchlist?user_id=user-1").json() == []


def test_reminder_can_be_completed_and_counted(client: TestClient) -> None:
    due_at = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    response = client.post(
        "/daily-use/reminders",
        json={
            "user_id": "user-1",
            "title": "Review AAPL thesis",
            "reminder_type": "thesis_review",
            "due_at": due_at,
            "priority": "high",
            "payload_json": {"symbol": "AAPL"},
        },
    )

    assert response.status_code == 201
    reminder = response.json()
    overview = client.get("/daily-use/overview?user_id=user-1").json()
    assert overview["active_reminders_count"] == 1
    assert overview["due_reminders_count"] == 1
    assert overview["execution_available"] is False

    complete_response = client.post(f"/daily-use/reminders/{reminder['id']}/complete")
    assert complete_response.status_code == 200
    assert complete_response.json()["status"] == "done"
    assert complete_response.json()["completed_at"] is not None
    overview_after = client.get("/daily-use/overview?user_id=user-1").json()
    assert overview_after["active_reminders_count"] == 0


def test_local_start_initializes_simulation_and_onboarding(client: TestClient) -> None:
    before = client.get("/daily-use/local-start?user_id=user-local")
    assert before.status_code == 200
    assert before.json()["status"] == "needs_setup"

    response = client.post(
        "/daily-use/local-start?user_id=user-local",
        json={
            "data_mode": "simulation",
            "risk_boundary_acknowledged": True,
            "daily_review_time": "20:30",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["data_mode"] == "simulation"
    assert payload["demo_seeded"] is True
    assert payload["execution_available"] is False
    assert payload["onboarding"]["state"]["first_daily_open"] is True
    assert payload["onboarding"]["completion_pct"] == 100
    assert payload["onboarding"]["next_step"] is None
    assert {step["key"] for step in payload["onboarding"]["step_details"]} >= {
        "workspace_goal",
        "risk_boundary_acknowledged",
        "read_only_data_plan",
        "investment_discipline",
        "daily_review_time",
        "first_daily_open",
    }
    assert payload["onboarding"]["state"]["investment_discipline"]["status"] == "ready"
    budgets = client.get("/risk-budgets?limit=100").json()
    local_asset_classes = {item["asset_class"] for item in budgets if item["user_id"] == "user-local"}
    assert {"stock", "equity", "etf", "crypto"} <= local_asset_classes
    scheduler = client.get("/daily-use/scheduler-status?user_id=user-local")
    assert scheduler.status_code == 200
    assert scheduler.json()["status"] == "running"
    assert scheduler.json()["active_jobs"] >= 3
    assert scheduler.json()["health_status"] == "needs_verification"
    assert scheduler.json()["verified_jobs"] == 0
    listed_jobs = client.get("/scheduled-jobs?limit=20")
    assert listed_jobs.status_code == 200
    assert any(item["job_type"] == "product_continuous_reminders" for item in listed_jobs.json())

    workspace = client.get("/daily-use/workspace-status?user_id=user-local")
    assert workspace.status_code == 200
    workspace_payload = workspace.json()
    assert workspace_payload["status"] == "ready"
    assert workspace_payload["ready_count"] == workspace_payload["total_count"] == 4
    assert workspace_payload["data_mode"] == "simulation"
    assert {item["key"] for item in workspace_payload["checks"]} == {"workspace", "data", "investment_discipline", "scheduler"}
    assert workspace_payload["execution_available"] is False

    readiness = client.get("/daily-use/self-use-readiness?user_id=user-local")
    assert readiness.status_code == 200
    readiness_payload = readiness.json()
    assert readiness_payload["mode"] == "local_self_use"
    assert readiness_payload["status"] in {"locally_usable", "usable_with_gaps"}
    assert readiness_payload["progress_pct"] < 100
    assert readiness_payload["remaining_pct"] > 0
    assert readiness_payload["next_action"]["route"].startswith("/?module=")
    assert "真实 Binance read-only snapshot" in readiness_payload["external_blockers"][0]
    assert readiness_payload["execution_available"] is False
    assert {item["key"] for item in readiness_payload["checks"]} >= {"onboarding", "data", "investment_discipline", "scheduler", "today_queue", "safety_boundary"}


def test_onboarding_status_exposes_next_step_details(client: TestClient) -> None:
    before = client.get("/daily-use/onboarding?user_id=onboarding-detail-user")
    assert before.status_code == 200
    payload = before.json()
    assert payload["status"] == "incomplete"
    assert payload["completion_pct"] == 0
    assert payload["next_step"]["key"] == "workspace_goal"
    assert payload["next_step"]["route"].startswith("/?module=")
    assert payload["step_details"][0]["status"] == "action_required"

    partial = client.post(
        "/daily-use/onboarding?user_id=onboarding-detail-user",
        json={"workspace_goal": "daily_investment_review"},
    )
    assert partial.status_code == 200
    partial_payload = partial.json()
    assert partial_payload["completion_pct"] == 17
    assert partial_payload["next_step"]["key"] == "risk_boundary_acknowledged"


def test_local_start_csv_mode_adds_data_setup_task_to_today_queue(client: TestClient) -> None:
    response = client.post(
        "/daily-use/local-start?user_id=csv-user",
        json={
            "data_mode": "csv",
            "risk_boundary_acknowledged": True,
            "daily_review_time": "20:30",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["initialized"] is True
    assert payload["status"] == "needs_data"
    assert payload["data_mode"] == "csv"
    assert payload["setup_tasks"][0]["id"] == "local_start:csv_import"
    assert payload["next_route"].endswith("setup=csv")
    assert payload["execution_available"] is False

    queue = client.get("/daily-use/action-queue?user_id=csv-user&source=local_start&limit=20")
    assert queue.status_code == 200
    task = queue.json()["actions"][0]
    assert task["id"] == "local_start:csv_import"
    assert task["title"] == "导入第一份 CSV 数据"
    assert task["action_label"] == "导入 CSV"
    assert task["route"].endswith("setup=csv")
    assert task["execution_available"] is False

    workspace = client.get("/daily-use/workspace-status?user_id=csv-user")
    assert workspace.status_code == 200
    assert workspace.json()["status"] == "action_required"
    assert workspace.json()["primary_action"]["id"] == "local_start:csv_import"


def test_data_mode_change_requires_confirmation_and_preserves_audit_history(client: TestClient) -> None:
    first = client.post("/daily-use/local-start?user_id=mode-switch-user", json={
        "data_mode": "simulation", "risk_boundary_acknowledged": True, "daily_review_time": "20:30",
    })
    assert first.status_code == 200
    assert first.json()["simulation_excluded_from_real_evidence"] is True
    denied = client.post("/daily-use/local-start?user_id=mode-switch-user", json={
        "data_mode": "read_only", "risk_boundary_acknowledged": True, "daily_review_time": "20:30",
    })
    assert denied.status_code == 422
    assert "SWITCH_DATA_MODE" in denied.json()["detail"]
    unchanged = client.get("/daily-use/local-start?user_id=mode-switch-user").json()
    assert unchanged["data_mode"] == "simulation"

    changed = client.post("/daily-use/local-start?user_id=mode-switch-user", json={
        "data_mode": "read_only",
        "risk_boundary_acknowledged": True,
        "daily_review_time": "20:30",
        "mode_change_confirmation": "SWITCH_DATA_MODE",
    })
    assert changed.status_code == 200
    payload = changed.json()
    assert payload["data_mode"] == "read_only"
    assert payload["simulation_data_user_id"] == "demo-user"
    assert payload["simulation_excluded_from_real_evidence"] is True
    assert [(item["from"], item["to"]) for item in payload["mode_history"]] == [(None, "simulation"), ("simulation", "read_only")]


def test_local_start_csv_task_clears_after_first_csv_import(client: TestClient) -> None:
    start = client.post(
        "/daily-use/local-start?user_id=csv-clear-user",
        json={
            "data_mode": "csv",
            "risk_boundary_acknowledged": True,
            "daily_review_time": "20:30",
        },
    )
    assert start.status_code == 200
    assert start.json()["setup_tasks"][0]["id"] == "local_start:csv_import"

    imported = client.post(
        "/imports/csv",
        json={
            "import_type": "holdings",
            "csv_text": (
                "account_name,account_type,asset_symbol,asset_name,asset_type,quantity,average_cost,current_price,market_value,currency\n"
                "Main CSV Account,brokerage,AAPL,Apple Inc.,stock,10,180,225,2250,USD\n"
            ),
            "source_name": "local_start_csv",
            "source_ref": "local-start/holdings.csv",
            "default_currency": "USD",
            "persist_positions": True,
            "can_be_used_for_trading": False,
        },
    )
    assert imported.status_code == 201

    status = client.get("/daily-use/local-start?user_id=csv-clear-user")
    assert status.status_code == 200
    assert status.json()["status"] == "ready"
    assert status.json()["setup_tasks"] == []

    queue = client.get("/daily-use/action-queue?user_id=csv-clear-user&source=local_start&limit=20")
    assert queue.status_code == 200
    assert queue.json()["actions"] == []


def test_local_start_readonly_mode_adds_readonly_setup_task_to_today_queue(client: TestClient) -> None:
    response = client.post(
        "/daily-use/local-start?user_id=readonly-user",
        json={
            "data_mode": "read_only",
            "risk_boundary_acknowledged": True,
            "daily_review_time": "20:30",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["initialized"] is True
    assert payload["status"] == "needs_data"
    assert payload["data_mode"] == "read_only"
    assert payload["setup_tasks"][0]["id"] == "local_start:read_only_setup"
    assert payload["next_route"].endswith("setup=read_only")

    queue = client.get("/daily-use/action-queue?user_id=readonly-user&source=local_start&limit=20")
    assert queue.status_code == 200
    task = queue.json()["actions"][0]
    assert task["id"] == "local_start:read_only_setup"
    assert task["title"] == "配置真实只读账户"
    assert task["action_label"] == "配置只读账户"
    assert task["route"].endswith("setup=read_only")
    assert task["execution_available"] is False


def test_local_start_readonly_task_advances_to_binance_evidence_after_connection(client: TestClient) -> None:
    start = client.post(
        "/daily-use/local-start?user_id=readonly-clear-user",
        json={
            "data_mode": "read_only",
            "risk_boundary_acknowledged": True,
            "daily_review_time": "20:30",
        },
    )
    assert start.status_code == 200
    assert start.json()["setup_tasks"][0]["id"] == "local_start:read_only_setup"

    setup = client.post(
        "/data-sources/connections/read-only-setup",
        json={
            "provider": "binance_spot_readonly",
            "account_label": "spot-readonly",
            "credentials_ref": "secretref:BINANCE_SPOT_READONLY",
            "config_json": {"account_label": "spot-readonly"},
        },
    )
    assert setup.status_code == 201
    assert setup.json()["execution_available"] is False

    status = client.get("/daily-use/local-start?user_id=readonly-clear-user")
    assert status.status_code == 200
    assert status.json()["status"] == "needs_data"
    assert status.json()["setup_tasks"][0]["id"] == "local_start:binance_evidence_preflight"
    assert status.json()["setup_tasks"][0]["action_label"] == "生成证据包"

    queue = client.get("/daily-use/action-queue?user_id=readonly-clear-user&source=local_start&limit=20")
    assert queue.status_code == 200
    task = queue.json()["actions"][0]
    assert task["id"] == "local_start:binance_evidence_preflight"
    assert task["title"] == "生成 Binance 只读证据包"
    assert task["route"].endswith("setup=read_only")


def test_binance_evidence_preflight_keeps_private_sync_in_today_queue(client: TestClient) -> None:
    start = client.post(
        "/daily-use/local-start?user_id=readonly-evidence-user",
        json={
            "data_mode": "read_only",
            "risk_boundary_acknowledged": True,
            "daily_review_time": "20:30",
        },
    )
    assert start.status_code == 200

    packet = client.post(
        "/data-sources/binance/read-only-evidence/preflight?user_id=readonly-evidence-user",
        json={
            "account_label": "spot-readonly",
            "credentials_ref": "secretref:BINANCE_SPOT_READONLY",
            "permission_screenshot_ref": "evidence://binance/permissions-redacted.png",
            "withdrawal_disabled_proof_ref": "evidence://binance/withdrawal-disabled.png",
            "verification_environment": "private_local",
        },
    )
    assert packet.status_code == 200
    assert packet.json()["status"] == "preflight_ready"
    assert packet.json()["external_api_called"] is False

    status = client.get("/daily-use/local-start?user_id=readonly-evidence-user")
    assert status.status_code == 200
    assert status.json()["status"] == "needs_data"
    task = status.json()["setup_tasks"][0]
    assert task["id"] == "local_start:binance_private_sync"
    assert "snapshot" in task["detail"]
    assert "quality report" in task["detail"]
    assert task["evidence_status"]["preflight_ready"] is True
    assert task["evidence_status"]["snapshot_ready"] is False
    assert task["evidence_status"]["quality_report_ready"] is False

    queue = client.get("/daily-use/action-queue?user_id=readonly-evidence-user&source=local_start&limit=20")
    assert queue.status_code == 200
    action = queue.json()["actions"][0]
    assert action["id"] == "local_start:binance_private_sync"
    assert action["action_label"] == "查看私有同步步骤"
    assert action["evidence_status"]["preflight_ready"] is True
    assert action["evidence_status"]["snapshot_ready"] is False
    assert action["evidence_status"]["quality_report_ready"] is False
    assert action["execution_available"] is False

    run = client.post("/daily-use/action-queue/local_start%3Abinance_private_sync/run?user_id=readonly-evidence-user")
    assert run.status_code == 200
    result = run.json()
    assert result["status"] == "manual_required"
    assert "私有环境" in result["message"]
    assert result["artifact_id"] == packet.json()["audit_packet_artifact_id"]
    assert result["summary"]["provider"] == "binance_spot_readonly"
    assert result["summary"]["evidence_status"]["preflight_ready"] is True
    assert result["summary"]["evidence_status"]["snapshot_ready"] is False
    assert result["summary"]["evidence_status"]["quality_report_ready"] is False
    assert result["summary"]["external_api_called"] is False
    assert result["summary"]["execution_available"] is False
    assert result["summary"]["order_routing_available"] is False
    assert result["summary"]["withdrawals_allowed"] is False
    assert result["summary"]["signing_available"] is False
    assert "真实只读 snapshot" in result["summary"]["missing_evidence"]
    assert "quality report" in result["summary"]["missing_evidence"]
    assert result["next_item"]["id"] == "local_start:binance_private_sync"


def test_runtime_scheduler_tick_records_last_run_evidence(client: TestClient) -> None:
    response = client.post(
        "/daily-use/local-start?user_id=user-scheduler",
        json={
            "data_mode": "simulation",
            "risk_boundary_acknowledged": True,
            "daily_review_time": "20:30",
        },
    )
    assert response.status_code == 200

    tick = client.post("/daily-use/scheduler-tick?user_id=user-scheduler", json={"action": "refresh_reminders"})
    assert tick.status_code == 200
    packet = tick.json()
    assert packet["status"] == "completed"
    assert packet["execution_available"] is False
    assert packet["queue"]["execution_available"] is False

    scheduler = packet["scheduler"]
    assert scheduler["status"] == "running"
    assert scheduler["health_status"] == "verified"
    assert scheduler["health_label"] == "已验证"
    assert scheduler["verified_jobs"] >= 1
    assert scheduler["stale_after_hours"] == 36
    assert scheduler["runtime_loop_enabled"] is True
    assert scheduler["runtime_poll_seconds"] >= 5
    assert scheduler["continuity_label"] == "持续运行已验证"
    assert "本地后台每" in scheduler["continuity_detail"]
    assert scheduler["next_run_at"] is not None
    reminder_job = next(item for item in scheduler["jobs"] if item["job_type"] == "product_continuous_reminders")
    assert reminder_job["last_run_at"] is not None
    assert reminder_job["last_run_status"] == "scheduled"
    assert reminder_job["schedule_label"] == "每 15 分钟刷新提醒"
    assert reminder_job["next_run_at"] is not None


def test_scheduler_persists_and_deduplicates_human_thesis_review_tasks(client: TestClient) -> None:
    asset = create_asset(client)
    thesis = client.post(
        "/investment-theses",
        json={
            "user_id": "auto-review-user",
            "asset_id": asset["id"],
            "entry_reason": "Validate the durable earnings thesis.",
            "key_drivers_json": {"items": ["earnings_quality"]},
            "invalidation_conditions_json": {"items": ["margin_breakdown"]},
            "expected_horizon": "swing",
            "target_condition": "Review after earnings",
            "max_loss_tolerance_pct": 0.08,
            "position_plan_json": {"max_weight": 0.1},
            "confidence": 0.7,
            "source": "test",
            "status": "active",
        },
    )
    assert thesis.status_code == 201

    first = client.post(
        "/daily-use/scheduler-tick?user_id=auto-review-user",
        json={"action": "refresh_reminders"},
    ).json()
    assert first["automatic_reviews"]["created"] >= 1
    thesis_action = next(item for item in first["queue"]["actions"] if item["source"] == "thesis_checkpoint")
    assert thesis_action["action_type"] == "record_thesis_checkpoint"
    assert thesis_action["execution_available"] is False

    second = client.post(
        "/daily-use/scheduler-tick?user_id=auto-review-user",
        json={"action": "refresh_reminders"},
    ).json()
    assert second["automatic_reviews"]["created"] == 0
    assert second["automatic_reviews"]["updated"] >= 1
    assert sum(1 for item in second["queue"]["actions"] if item["source"] == "thesis_checkpoint") == 1


def test_today_queue_actions_persist_for_reminders_and_derived_items(client: TestClient) -> None:
    due_at = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    reminder = client.post(
        "/daily-use/reminders",
        json={"user_id": "queue-user", "title": "Review thesis", "due_at": due_at, "priority": "high"},
    ).json()
    queue_item_id = f"reminder:{reminder['id']}"

    assigned = client.post(
        f"/daily-use/action-queue/{queue_item_id}/actions?user_id=queue-user",
        json={"action": "assign", "assignee_id": "queue-user"},
    )
    assert assigned.status_code == 200
    assert assigned.json()["assignee_id"] == "queue-user"
    assert assigned.json()["next_item"]["route"].startswith("/?module=")
    assert len(assigned.json()["next_item"]["guidance_steps"]) == 3

    completed = client.post(
        f"/daily-use/action-queue/{queue_item_id}/actions?user_id=queue-user",
        json={"action": "complete"},
    )
    assert completed.status_code == 200
    assert completed.json()["message"].startswith("任务已完成")
    assert all(item["id"] != queue_item_id for item in completed.json()["queue"]["actions"])

    queue = client.get("/daily-use/action-queue?user_id=queue-user").json()
    derived = next(item for item in queue["actions"] if not item["id"].startswith("reminder:"))
    dismissed = client.post(
        f"/daily-use/action-queue/{derived['id']}/actions?user_id=queue-user",
        json={"action": "dismiss"},
    )
    assert dismissed.status_code == 200
    assert all(item["id"] != derived["id"] for item in dismissed.json()["queue"]["actions"])


def test_today_queue_can_run_simulated_data_refresh_task(client: TestClient) -> None:
    started = client.post(
        "/daily-use/local-start?user_id=runner",
        json={"data_mode": "simulation", "risk_boundary_acknowledged": True, "daily_review_time": "20:30"},
    )
    assert started.status_code == 200

    queue = client.get("/daily-use/action-queue?user_id=runner&action_type=refresh_data").json()
    assert any(item["id"] == "data:fx_rates" for item in queue["actions"])

    response = client.post("/daily-use/action-queue/data:fx_rates/run?user_id=runner", json={})
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["snapshot_id"]
    assert payload["quality_report_id"]
    assert payload["summary"]["simulation_only"] is True
    assert payload["execution_available"] is False
    assert all(item["id"] != "data:fx_rates" for item in payload["queue"]["actions"])


def test_today_queue_run_readonly_account_returns_manual_steps_without_connection(client: TestClient) -> None:
    response = client.post("/daily-use/action-queue/data:read_only_account/run?user_id=manual-user", json={})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "manual_required"
    assert "只读" in payload["message"]
    assert payload["route"].endswith("setup=read_only")
    assert payload["execution_available"] is False


def test_today_queue_surfaces_missing_holding_thesis_with_direct_route(client: TestClient) -> None:
    asset = create_asset(client)
    account = client.post(
        "/accounts",
        json={"name": "Paper account", "account_type": "brokerage", "broker": "manual", "base_currency": "USD", "mode": "paper"},
    ).json()
    position_response = client.post(
        "/positions/import",
        json={
            "account_id": account["id"],
            "asset_id": asset["id"],
            "quantity": 10,
            "average_cost": 100,
            "market_price": 150,
            "market_value": 1500,
            "unrealized_pnl": 500,
            "realized_pnl": 0,
        },
    )
    assert position_response.status_code == 201

    queue = client.get("/daily-use/action-queue?user_id=thesis-user&source=thesis_coverage&limit=20")

    assert queue.status_code == 200
    action = next(item for item in queue.json()["actions"] if item["action_type"] == "create_holding_thesis")
    assert action["title"] == "为 AAPL 补充 Thesis"
    assert action["action_label"] == "补 Thesis"
    assert action["route"].startswith(f"/?module=holdings&asset={asset['id']}&create_thesis=1")
    assert action["execution_available"] is False


def test_portfolio_risk_drilldown_includes_position_asset_and_thesis(client: TestClient) -> None:
    asset = create_asset(client)
    account = client.post(
        "/accounts",
        json={"name": "Risk account", "account_type": "brokerage", "broker": "manual", "base_currency": "USD", "mode": "paper"},
    ).json()
    position = client.post(
        "/positions/import",
        json={
            "account_id": account["id"],
            "asset_id": asset["id"],
            "quantity": 100,
            "average_cost": 100,
            "market_price": 500,
            "market_value": 50000,
            "unrealized_pnl": 40000,
            "realized_pnl": 0,
            "weight": 1,
        },
    ).json()
    thesis_response = client.post(
        "/investment-theses",
        json={
            "user_id": "default-user",
            "asset_id": asset["id"],
            "account_id": account["id"],
            "entry_reason": "Risk drilldown thesis",
            "key_drivers_json": {"items": ["earnings_quality"]},
            "invalidation_conditions_json": {"items": ["margin_breakdown"]},
            "expected_horizon": "swing",
            "target_condition": "Review after next earnings",
            "max_loss_tolerance_pct": 0.08,
            "position_plan_json": {"max_weight": 0.2},
            "confidence": 0.7,
            "source": "test",
            "status": "active",
        },
    )
    assert thesis_response.status_code == 201

    queue = client.get("/daily-use/action-queue?user_id=default-user&source=portfolio_risk&limit=20").json()
    action = next(item for item in queue["actions"] if item["related_entity_id"] == position["id"])
    packet = client.get(f"/daily-use/drilldown/{action['id']}?user_id=default-user")

    assert packet.status_code == 200
    evidence_types = {item["type"] for item in packet.json()["evidence"]}
    assert {"position", "asset", "investment_thesis"}.issubset(evidence_types)
    assert packet.json()["execution_available"] is False


def test_cash_position_does_not_create_a_concentration_risk_task(client: TestClient) -> None:
    cash_asset = client.post(
        "/assets",
        json={
            "symbol": "CASHUSD",
            "name": "US Dollar",
            "asset_type": "cash",
            "market": "CASH",
            "venue": "CASH",
            "currency": "USD",
            "tradable": False,
            "manual_enabled": False,
            "auto_enabled": False,
            "risk_level": "low",
        },
    ).json()
    account = client.post(
        "/accounts",
        json={"name": "Cash account", "account_type": "cash", "broker": "manual", "base_currency": "USD", "mode": "paper"},
    ).json()
    client.post(
        "/positions/import",
        json={
            "account_id": account["id"],
            "asset_id": cash_asset["id"],
            "quantity": 100000,
            "average_cost": 1,
            "market_price": 1,
            "market_value": 100000,
            "unrealized_pnl": 0,
            "realized_pnl": 0,
        },
    )

    queue = client.get("/daily-use/action-queue?user_id=cash-user").json()
    assert all(item["title"] != "复查集中度风险：CASHUSD" for item in queue["actions"])


def test_portfolio_risk_queue_uses_imported_position_weight(client: TestClient) -> None:
    large_asset = client.post(
        "/assets",
        json={
            "symbol": "GIANTBASE",
            "name": "Giant Base",
            "asset_type": "stock",
            "market": "US",
            "venue": "NASDAQ",
            "currency": "USD",
            "tradable": True,
            "manual_enabled": True,
            "auto_enabled": False,
            "risk_level": "medium",
        },
    ).json()
    focus_asset = client.post(
        "/assets",
        json={
            "symbol": "WEIGHTRISK",
            "name": "Weighted Risk",
            "asset_type": "stock",
            "market": "US",
            "venue": "NASDAQ",
            "currency": "USD",
            "tradable": True,
            "manual_enabled": True,
            "auto_enabled": False,
            "risk_level": "high",
        },
    ).json()
    account = client.post(
        "/accounts",
        json={"name": "Weighted risk account", "account_type": "brokerage", "broker": "manual", "base_currency": "USD", "mode": "paper"},
    ).json()
    client.post(
        "/positions/import",
        json={
            "account_id": account["id"],
            "asset_id": large_asset["id"],
            "quantity": 100,
            "average_cost": 100,
            "market_price": 100,
            "market_value": 900000000000000000,
            "unrealized_pnl": 0,
            "realized_pnl": 0,
            "weight": 0.01,
        },
    )
    position = client.post(
        "/positions/import",
        json={
            "account_id": account["id"],
            "asset_id": focus_asset["id"],
            "quantity": 1,
            "average_cost": 100,
            "market_price": 100,
            "market_value": 100,
            "unrealized_pnl": 0,
            "realized_pnl": 0,
            "weight": 0.4,
        },
    ).json()

    queue = client.get("/daily-use/action-queue?user_id=default-user&source=portfolio_risk&limit=100").json()

    assert any(item["related_entity_id"] == position["id"] for item in queue["actions"])


def test_local_config_rejects_inline_secrets(client: TestClient) -> None:
    response = client.put(
        "/daily-use/local-config/dashboard",
        json={
            "user_id": "user-1",
            "value_json": {"api_key": "do-not-store"},
        },
    )

    assert response.status_code == 422
    assert "inline secrets" in str(response.json()["detail"])


def test_export_and_backup_manifest_are_read_only_and_redact_credentials(client: TestClient) -> None:
    create_asset(client)
    connection_response = client.post(
        "/data-sources/connections",
        json={
            "name": "Read-only source",
            "provider": "mock_market_data",
            "source_type": "market_data",
            "mode": "read_only",
            "credentials_ref": "local-secret-ref",
        },
    )
    assert connection_response.status_code == 201
    watchlist_response = client.post("/daily-use/watchlist", json={"user_id": "user-1", "symbol": "AAPL"})
    assert watchlist_response.status_code == 201
    config_response = client.put(
        "/daily-use/local-config/workspace",
        json={"user_id": "user-1", "value_json": {"default_module": "overview"}, "description": "Local workspace defaults."},
    )
    assert config_response.status_code == 200

    export_response = client.post(
        "/daily-use/exports",
        json={"user_id": "user-1", "export_type": "daily_snapshot", "include_sections": ["watchlist", "local_config", "data_sources"]},
    )

    assert export_response.status_code == 201
    artifact = export_response.json()
    assert artifact["summary_json"]["execution_available"] is False
    assert artifact["summary_json"]["contains_secrets"] is False
    data_source = artifact["payload_json"]["sections"]["data_sources"][0]
    assert data_source["credentials_ref"] == "redacted"
    assert data_source["has_credentials_ref"] is True

    backup_response = client.post("/daily-use/backup-manifest?user_id=user-1")
    assert backup_response.status_code == 201
    backup = backup_response.json()
    assert backup["export_type"] == "local_backup_manifest"
    assert backup["payload_json"]["execution_available"] is False
    assert "watchlist" in backup["payload_json"]["sections"]


def test_daily_open_close_history_persists_each_run(client: TestClient) -> None:
    for _ in range(2):
        assert client.post("/daily-use/daily-open?user_id=history-user").status_code == 200
    assert client.post("/daily-use/daily-close?user_id=history-user", json={"note": "done"}).status_code == 200

    response = client.get("/daily-use/daily-history?user_id=history-user")

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 3
    kinds = [record["kind"] for record in payload["records"]]
    assert kinds.count("open") == 2
    assert kinds.count("close") == 1
    assert payload["execution_available"] is False
    assert all(record["summary"] for record in payload["records"])


def test_daily_queue_batch_action_is_visible_only_audited_and_fail_closed(client: TestClient) -> None:
    for index in range(3):
        response = client.post(
            "/daily-use/reminders",
            json={
                "user_id": "batch-user",
                "title": f"Batch reminder {index}",
                "reminder_type": "manual",
                "priority": "high",
                "due_at": "2026-01-01T00:00:00Z",
                "payload_json": {},
            },
        )
        assert response.status_code == 201

    queue = client.get("/daily-use/action-queue?user_id=batch-user&limit=20").json()
    reminder_ids = [item["id"] for item in queue["actions"] if item["id"].startswith("reminder:")]
    response = client.post(
        "/daily-use/action-queue/batch-actions?user_id=batch-user",
        json={"queue_item_ids": reminder_ids[:2], "action": "complete"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["processed_count"] == 2
    assert payload["execution_available"] is False
    remaining_ids = {item["id"] for item in payload["queue"]["actions"]}
    assert not set(reminder_ids[:2]) & remaining_ids
    assert reminder_ids[2] in remaining_ids

    invalid = client.post(
        "/daily-use/action-queue/batch-actions?user_id=batch-user",
        json={"queue_item_ids": ["reminder:not-visible"], "action": "dismiss"},
    )
    assert invalid.status_code == 422
