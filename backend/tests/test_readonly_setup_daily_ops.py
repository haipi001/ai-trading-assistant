from datetime import datetime
from datetime import timedelta
from datetime import timezone
from unittest.mock import Mock

from fastapi.testclient import TestClient

from app.services.ops_readiness import OpsReadinessService
from app.services.ops_readiness import check


def test_readonly_setup_uses_secret_reference_and_freshness_tracks_account_snapshot(client: TestClient) -> None:
    setup_response = client.post(
        "/data-sources/connections/read-only-setup",
        json={
            "provider": "ibkr_readonly",
            "account_label": "main-paper",
            "credentials_ref": "secretref:IBKR_READONLY",
            "config_json": {"gateway_host": "127.0.0.1", "gateway_port": 4002},
        },
    )

    assert setup_response.status_code == 201
    setup = setup_response.json()
    assert setup["execution_available"] is False
    assert setup["provider_status"] == "configured_pending_sync"
    assert setup["connection"]["mode"] == "read_only"
    assert setup["connection"]["credentials_ref"] == "secretref:IBKR_READONLY"
    assert setup["connection"]["config_json"]["execution_available"] is False
    assert setup["connection"]["config_json"]["order_routing_available"] is False

    sync_response = client.post(
        f"/data-sources/connections/{setup['connection']['id']}/sync-account",
        json={
            "sample_payload": {
                "as_of": datetime.now(timezone.utc).isoformat(),
                "account": {"account_id": "U123", "label": "main-paper", "base_currency": "USD"},
                "balances": [{"currency": "USD", "cash_value": 10000}],
                "positions": [
                    {
                        "symbol": "AAPL",
                        "asset_type": "stock",
                        "quantity": 5,
                        "average_cost": 180,
                        "market_price": 220,
                    }
                ],
                "orders": [],
            }
        },
    )
    assert sync_response.status_code == 201
    sync_payload = sync_response.json()
    assert sync_payload["snapshot"]["metadata_json"]["data_origin"] == "sample_payload"
    assert sync_payload["snapshot"]["metadata_json"]["real_external_evidence"] is False

    freshness_response = client.get("/data-sources/freshness")
    assert freshness_response.status_code == 200
    freshness = freshness_response.json()
    account_item = next(item for item in freshness["items"] if item["dataset_type"] == "read_only_account")
    assert account_item["status"] == "fresh"
    assert account_item["execution_available"] is False
    assert account_item["quality_score"] >= 0.8


def test_readonly_setup_rejects_inline_secret_reference(client: TestClient) -> None:
    response = client.post(
        "/data-sources/connections/read-only-setup",
        json={
            "provider": "cex_readonly",
            "account_label": "main",
            "credentials_ref": "sk-this-is-an-inline-token",
        },
    )

    assert response.status_code == 422
    assert "inline secret" in str(response.json()["detail"])


def test_ledger_reconciliation_policy_blocks_empty_ledger(client: TestClient) -> None:
    response = client.get("/ledger/reconciliation-policy")

    assert response.status_code == 200
    policy = response.json()
    assert policy["policy_status"] == "blocked"
    assert policy["can_promote_to_review"] is False
    assert policy["can_unlock_order_approval"] is False
    assert policy["execution_available"] is False
    assert "ledger_entries_missing" in policy["blockers"]
    assert "latest_reconciliation_missing" in policy["blockers"]


def test_ledger_reconciliation_policy_promotes_synced_readonly_account_to_review_only(client: TestClient) -> None:
    setup_response = client.post(
        "/data-sources/connections/read-only-setup",
        json={
            "provider": "ibkr_readonly",
            "account_label": "main-paper",
            "credentials_ref": "secretref:IBKR_READONLY",
            "config_json": {"gateway_host": "127.0.0.1", "gateway_port": 4002},
        },
    )
    assert setup_response.status_code == 201
    connection = setup_response.json()["connection"]
    sync_response = client.post(
        f"/data-sources/connections/{connection['id']}/sync-account",
        json={
            "sample_payload": {
                "as_of": datetime.now(timezone.utc).isoformat(),
                "account": {"account_id": "U123", "label": "main-paper", "base_currency": "USD"},
                "balances": [{"currency": "USD", "cash_value": 10000}],
                "positions": [
                    {
                        "symbol": "AAPL",
                        "asset_type": "stock",
                        "quantity": 5,
                        "average_cost": 180,
                        "market_price": 220,
                    }
                ],
                "orders": [],
            }
        },
    )
    assert sync_response.status_code == 201
    ledger_sync = client.post("/ledger/sync")
    assert ledger_sync.status_code == 201
    reconcile = client.post("/ledger/reconcile/extended")
    assert reconcile.status_code == 201

    response = client.get("/ledger/reconciliation-policy")

    assert response.status_code == 200
    policy = response.json()
    assert policy["policy_status"] in {"trusted", "review_required"}
    assert policy["can_promote_to_review"] is True
    assert policy["can_unlock_order_approval"] is False
    assert policy["execution_available"] is False


def test_daily_action_queue_combines_due_reminders_watchlist_data_and_backup(client: TestClient) -> None:
    due_at = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    reminder_response = client.post(
        "/daily-use/reminders",
        json={
            "user_id": "user-1",
            "title": "Review AAPL thesis",
            "reminder_type": "thesis_review",
            "due_at": due_at,
            "priority": "high",
        },
    )
    assert reminder_response.status_code == 201
    watch_response = client.post(
        "/daily-use/watchlist",
        json={"user_id": "user-1", "symbol": "AAPL", "priority": "high", "notes": "Daily focus."},
    )
    assert watch_response.status_code == 201

    queue_response = client.get("/daily-use/action-queue?user_id=user-1&limit=20")

    assert queue_response.status_code == 200
    queue = queue_response.json()
    action_types = {item["action_type"] for item in queue["actions"]}
    assert "complete_reminder" in action_types
    assert "review_watchlist" in action_types
    assert "refresh_data" in action_types
    assert "create_backup_manifest" in action_types
    assert queue["due_count"] >= 1
    assert queue["high_priority_count"] >= 2
    assert queue["execution_available"] is False

    filtered_response = client.get(
        "/daily-use/action-queue?user_id=user-1&source=reminders&priority=high&action_type=complete_reminder"
    )
    assert filtered_response.status_code == 200
    filtered = filtered_response.json()
    assert filtered["total_actions"] == 1
    assert filtered["actions"][0]["source"] == "reminders"
    assert filtered["actions"][0]["priority"] == "high"
    assert filtered["actions"][0]["action_type"] == "complete_reminder"


def test_ops_stability_report_returns_safe_preflight(monkeypatch, client: TestClient) -> None:
    monkeypatch.setattr(
        OpsReadinessService,
        "_redis_check",
        lambda self: check("redis", "Redis", "ok", "Redis ping skipped in unit test."),
    )

    response = client.get("/ops/stability-report")

    assert response.status_code == 200
    report = response.json()
    checks = {item["key"]: item for item in report["checks"]}
    assert report["execution_available"] is False
    assert report["overall_status"] in {"ok", "warn", "block"}
    assert checks["database"]["status"] == "ok"
    assert checks["safety"]["status"] == "ok"
    assert checks["api_abuse_protection"]["status"] == "warn"
    assert checks["safe_request_logging"]["status"] == "ok"
    assert checks["observability_metrics"]["status"] == "warn"
    assert "./scripts/regression_check.sh" in report["commands"]


def test_api_abuse_protection_blocks_production_when_not_enabled() -> None:
    service = OpsReadinessService(Mock())
    service.settings = service.settings.model_copy(
        update={
            "environment": "production",
            "deployment_target": "managed-production",
            "managed_auth_required": True,
            "api_rate_limit_enabled": False,
        }
    )

    result = service._api_abuse_check()

    assert result["status"] == "block"
    assert result["blockers"] == ["Enable managed auth and Redis-backed API rate limiting before private beta."]


def test_api_abuse_protection_reports_active_limits() -> None:
    service = OpsReadinessService(Mock())
    service.settings = service.settings.model_copy(
        update={
            "environment": "staging",
            "deployment_target": "managed-staging",
            "managed_auth_required": True,
            "api_rate_limit_enabled": True,
            "api_rate_limit_requests": 80,
            "api_login_rate_limit_requests": 8,
            "api_rate_limit_window_seconds": 60,
        }
    )

    result = service._api_abuse_check()

    assert result["status"] == "ok"
    assert "8 login" in result["detail"]
    assert "80 API" in result["detail"]


def test_safe_logging_blocks_production_when_disabled() -> None:
    service = OpsReadinessService(Mock())
    service.settings = service.settings.model_copy(
        update={
            "environment": "production",
            "deployment_target": "managed-production",
            "safe_request_logging_enabled": False,
        }
    )

    result = service._safe_logging_check()

    assert result["status"] == "block"
    assert result["blockers"] == ["Enable SAFE_REQUEST_LOGGING_ENABLED before private beta."]


def test_observability_metrics_block_production_when_disabled() -> None:
    service = OpsReadinessService(Mock())
    service.settings = service.settings.model_copy(
        update={
            "environment": "production",
            "deployment_target": "managed-production",
            "observability_metrics_enabled": False,
        }
    )

    result = service._observability_metrics_check()

    assert result["status"] == "block"
    assert result["blockers"] == ["Enable OBSERVABILITY_METRICS_ENABLED before private beta."]
