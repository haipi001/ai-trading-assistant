from fastapi.testclient import TestClient
from datetime import datetime
from datetime import timedelta
from datetime import timezone
import json
from urllib.parse import parse_qs
from urllib.parse import urlparse

import app.adapters.market_data_readonly as readonly_adapters
from app.db.session import get_db
from app.main import app
from app.models import DataSourceConnection
from app.services.runtime_scheduler import RuntimeSchedulerService


def create_mock_connection(client: TestClient) -> dict:
    response = client.post(
        "/data-sources/connections",
        json={
            "name": "Unit Test Mock Quotes",
            "provider": "mock_market_data",
            "source_type": "market_data",
            "mode": "read_only",
        },
    )
    assert response.status_code == 201
    return response.json()


def test_data_source_provider_registry_exposes_read_only_interfaces(client: TestClient) -> None:
    response = client.get("/data-sources/providers")

    assert response.status_code == 200
    providers = {provider["provider"]: provider for provider in response.json()}
    assert {
        "mock_market_data",
        "stooq_public_eod",
        "yfinance_public",
        "custom_http_readonly",
        "ibkr_readonly",
        "futu_readonly",
        "cex_readonly",
        "binance_spot_readonly",
        "wallet_readonly",
    }.issubset(providers)
    assert providers["custom_http_readonly"]["mode"] == "read_only"
    assert providers["custom_http_readonly"]["supports_custom_config"] is True
    assert providers["ibkr_readonly"]["requires_credentials"] is True
    assert "authenticated_account_snapshot" in providers["binance_spot_readonly"]["capabilities"]
    assert providers["wallet_readonly"]["source_type"] == "wallet_account"


def test_data_source_connections_never_accept_inline_secrets(client: TestClient) -> None:
    response = client.post(
        "/data-sources/connections",
        json={
            "name": "Bad Secret Source",
            "provider": "custom_http_readonly",
            "mode": "read_only",
            "config_json": {"headers": {"Authorization": "Bearer should-not-be-stored"}},
        },
    )

    assert response.status_code == 422
    assert "inline secrets" in str(response.json()["detail"])


def test_default_data_source_connections_are_created_read_only(client: TestClient) -> None:
    response = client.post("/data-sources/connections/defaults")

    assert response.status_code == 201
    connections = response.json()
    providers = {connection["provider"]: connection for connection in connections}
    assert {"mock_market_data", "stooq_public_eod", "yfinance_public"}.issubset(providers)
    assert all(connection["mode"] == "read_only" for connection in connections)


def test_data_source_fallback_policy_is_fail_closed_and_review_only(client: TestClient) -> None:
    defaults = client.post("/data-sources/connections/defaults")
    assert defaults.status_code == 201

    response = client.get("/data-sources/fallback-policy")
    assert response.status_code == 200
    payload = response.json()
    assert payload["execution_available"] is False
    assert payload["can_unlock_order_approval"] is False
    assert payload["overall_status"] in {"review_required", "fail_closed", "ready"}

    items = {item["dataset_type"]: item for item in payload["items"]}
    assert "market_quotes" in items
    assert items["market_quotes"]["primary_provider"] == "yfinance_public"
    assert "stooq_public_eod" in items["market_quotes"]["fallback_providers"]
    assert items["market_quotes"]["can_unlock_order_approval"] is False
    assert items["market_quotes"]["execution_available"] is False
    assert items["market_quotes"]["route"] == "/?module=settings&tab=data"

    assert "read_only_account" in items
    assert items["read_only_account"]["status"] in {"manual_review_available", "fallback_required", "fail_closed"}
    assert any("read_only_account" in action for action in items["read_only_account"]["next_actions"])


class FakeUrlResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self) -> "FakeUrlResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def test_yfinance_public_quote_and_hourly_candle_import_are_read_only(client: TestClient, monkeypatch) -> None:
    def fake_open(request, *, timeout):
        assert "query1.finance.yahoo.com" in request.full_url
        return FakeUrlResponse(
            {
                "chart": {
                    "result": [
                        {
                            "meta": {
                                "regularMarketPrice": 184.25,
                                "regularMarketTime": 1717588800,
                                "currency": "USD",
                            },
                            "timestamp": [1717581600, 1717585200, 1717588800],
                            "indicators": {
                                "quote": [
                                    {
                                        "open": [183.1, 183.7, 184.0],
                                        "high": [183.9, 184.4, 184.6],
                                        "low": [182.8, 183.5, 183.9],
                                        "close": [183.6, 184.1, 184.25],
                                        "volume": [1000, 1200, 1400],
                                    }
                                ]
                            },
                        }
                    ],
                    "error": None,
                }
            }
        )

    monkeypatch.setattr(readonly_adapters, "open_readonly_url", fake_open)

    create_response = client.post(
        "/data-sources/connections",
        json={
            "name": "Yahoo Finance Read-only",
            "provider": "yfinance_public",
            "mode": "read_only",
            "config_json": {"timeout_seconds": 3},
        },
    )
    assert create_response.status_code == 201
    connection = create_response.json()

    health_response = client.post(f"/data-sources/connections/{connection['id']}/health")
    assert health_response.status_code == 200
    assert health_response.json()["status"] == "ok"

    quote_response = client.post(
        f"/data-sources/connections/{connection['id']}/import-quotes",
        json={"symbols": ["AAPL"], "asset_type": "stock", "market": "US", "currency": "USD"},
    )
    assert quote_response.status_code == 201
    assert quote_response.json()["quotes_imported"] == 1
    assert quote_response.json()["symbols"] == ["AAPL"]

    candle_response = client.post(
        f"/data-sources/connections/{connection['id']}/import-candles",
        json={"symbols": ["AAPL"], "timeframe": "1h", "limit": 2, "asset_type": "stock", "market": "US", "currency": "USD"},
    )
    assert candle_response.status_code == 201
    payload = candle_response.json()
    assert payload["candles_imported"] == 2
    assert payload["timeframe"] == "1h"
    assert payload["symbols"] == ["AAPL"]

    assets = client.get("/assets").json()
    aapl = next(asset for asset in assets if asset["symbol"] == "AAPL")
    candles = client.get(f"/candles?asset_id={aapl['id']}&timeframe=1h&limit=10").json()
    assert len(candles) == 2
    assert all(candle["source"].startswith("yfinance_public:") for candle in candles)


def test_readonly_account_placeholders_fail_closed(client: TestClient) -> None:
    response = client.post("/data-sources/connections/read-only-account-placeholders")

    assert response.status_code == 201
    connections = response.json()
    providers = {connection["provider"]: connection for connection in connections}
    assert {"ibkr_readonly", "futu_readonly", "cex_readonly", "binance_spot_readonly", "wallet_readonly"}.issubset(providers)
    assert providers["cex_readonly"]["config_json"]["withdrawals_allowed"] is False
    assert providers["binance_spot_readonly"]["config_json"]["order_routing_available"] is False
    assert providers["wallet_readonly"]["config_json"]["signing_available"] is False

    health_response = client.post(f"/data-sources/connections/{providers['ibkr_readonly']['id']}/health")
    assert health_response.status_code == 200
    health = health_response.json()
    assert health["status"] == "unconfigured"
    assert health["details"]["execution_available"] is False


def test_readonly_account_preflight_blocks_unconfigured_placeholder(client: TestClient) -> None:
    response = client.post("/data-sources/connections/read-only-account-placeholders")
    assert response.status_code == 201
    providers = {connection["provider"]: connection for connection in response.json()}

    preflight_response = client.post(
        f"/data-sources/connections/{providers['ibkr_readonly']['id']}/read-only-preflight"
    )

    assert preflight_response.status_code == 200
    preflight = preflight_response.json()
    assert preflight["status"] == "blocked"
    assert preflight["requires_credentials"] is True
    assert preflight["has_credentials_ref"] is False
    assert {"credentials_ref", "gateway_host", "gateway_port"}.issubset(preflight["missing_requirements"])
    assert preflight["execution_available"] is False
    assert preflight["order_routing_available"] is False
    assert preflight["withdrawals_allowed"] is False
    assert preflight["signing_available"] is False
    assert preflight["details"]["safe_to_sync_sample_only"] is False

    audit_logs = client.get("/audit-logs").json()
    assert "data_source_connection.readonly_preflight_checked" in {log["action"] for log in audit_logs}


def test_readonly_account_preflight_accepts_reference_and_metadata_only(client: TestClient) -> None:
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

    preflight_response = client.post(f"/data-sources/connections/{connection['id']}/read-only-preflight")

    assert preflight_response.status_code == 200
    preflight = preflight_response.json()
    assert preflight["status"] == "ready_for_sample_sync"
    assert preflight["missing_requirements"] == []
    assert preflight["blocking_reasons"] == []
    assert preflight["has_credentials_ref"] is True
    assert preflight["execution_available"] is False
    assert preflight["details"]["required_config_keys"] == ["gateway_host", "gateway_port"]


def test_readonly_certification_reports_adapter_contract_and_sample_boundary(client: TestClient) -> None:
    setup_response = client.post(
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
    assert setup_response.status_code == 201
    connection = setup_response.json()["connection"]

    response = client.post(f"/data-sources/connections/{connection['id']}/read-only-certification")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "certified_sample_sync"
    assert payload["certification_level"] == "sample_sync_only"
    assert payload["sample_sync_allowed"] is True
    assert payload["execution_available"] is False
    assert payload["adapter_contract"]["contract_version"] == "readonly_adapter_v1"
    assert payload["adapter_contract"]["network_order_submission_allowed"] is False
    assert "withdrawals:write" in payload["forbidden_scopes"]
    assert "trading:disabled" in payload["required_scopes"]

    audit_logs = client.get("/audit-logs").json()
    assert "data_source_connection.readonly_certification_checked" in {log["action"] for log in audit_logs}


def test_readonly_certification_blocks_declared_write_permissions(client: TestClient) -> None:
    create_response = client.post(
        "/data-sources/connections",
        json={
            "name": "Unsafe Permission Source",
            "provider": "cex_readonly",
            "source_type": "exchange_account",
            "mode": "read_only",
            "credentials_ref": "secretref:CEX_READONLY",
            "config_json": {"exchange": "binance", "permissions": ["account:read", "withdrawals:write"]},
        },
    )
    assert create_response.status_code == 201
    connection = create_response.json()

    response = client.post(f"/data-sources/connections/{connection['id']}/read-only-certification")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "blocked"
    assert payload["sample_sync_allowed"] is False
    assert "forbidden_scope_declared:withdrawals:write" in payload["blockers"]


def test_readonly_account_preflight_blocks_dangerous_cex_permissions(client: TestClient) -> None:
    create_response = client.post(
        "/data-sources/connections",
        json={
            "name": "Unsafe CEX Read-only",
            "provider": "cex_readonly",
            "source_type": "exchange_account",
            "mode": "read_only",
            "credentials_ref": "secretref:CEX_READONLY",
            "config_json": {
                "exchange": "binance",
                "withdrawals_allowed": True,
                "trading_enabled": True,
            },
        },
    )
    assert create_response.status_code == 201
    connection = create_response.json()

    preflight_response = client.post(f"/data-sources/connections/{connection['id']}/read-only-preflight")

    assert preflight_response.status_code == 200
    preflight = preflight_response.json()
    assert preflight["status"] == "blocked"
    assert "withdrawals_allowed_must_be_false" in preflight["blocking_reasons"]
    assert "trading_enabled_must_be_false" in preflight["blocking_reasons"]
    assert preflight["withdrawals_allowed"] is False
    assert preflight["execution_available"] is False


def test_readonly_wallet_preflight_requires_public_address(client: TestClient) -> None:
    setup_response = client.post(
        "/data-sources/connections/read-only-setup",
        json={"provider": "wallet_readonly", "account_label": "cold-wallet"},
    )
    assert setup_response.status_code == 201
    connection = setup_response.json()["connection"]

    blocked_response = client.post(f"/data-sources/connections/{connection['id']}/read-only-preflight")

    assert blocked_response.status_code == 200
    blocked = blocked_response.json()
    assert blocked["status"] == "blocked"
    assert blocked["requires_credentials"] is False
    assert "public_address" in blocked["missing_requirements"]

    ready_setup_response = client.post(
        "/data-sources/connections/read-only-setup",
        json={
            "provider": "wallet_readonly",
            "account_label": "cold-wallet",
            "config_json": {"chain_id": "1", "public_address": "0x1111111111111111111111111111111111111111"},
        },
    )
    assert ready_setup_response.status_code == 201
    ready_connection = ready_setup_response.json()["connection"]

    ready_response = client.post(f"/data-sources/connections/{ready_connection['id']}/read-only-preflight")

    assert ready_response.status_code == 200
    ready = ready_response.json()
    assert ready["status"] == "ready_for_sample_sync"
    assert ready["missing_requirements"] == []
    assert ready["signing_available"] is False


def test_readonly_account_sync_fails_closed_without_sample_payload(client: TestClient) -> None:
    response = client.post("/data-sources/connections/read-only-account-placeholders")
    assert response.status_code == 201
    providers = {connection["provider"]: connection for connection in response.json()}

    sync_response = client.post(f"/data-sources/connections/{providers['ibkr_readonly']['id']}/sync-account", json={})

    assert sync_response.status_code == 422
    assert "not syncable" in sync_response.json()["detail"]


def test_readonly_account_sample_sync_creates_account_positions_quality_and_audit(client: TestClient) -> None:
    create_response = client.post(
        "/data-sources/connections",
        json={
            "name": "CEX Read-only Sample",
            "provider": "cex_readonly",
            "source_type": "exchange_account",
            "mode": "read_only",
            "config_json": {"exchange": "binance", "account_label": "main"},
        },
    )
    assert create_response.status_code == 201
    connection = create_response.json()
    assert connection["status"] == "unconfigured"

    sync_response = client.post(
        f"/data-sources/connections/{connection['id']}/sync-account",
        json={
            "sample_payload": {
                "as_of": "2026-06-13T10:00:00Z",
                "account": {
                    "account_id": "cex-demo-main",
                    "label": "main",
                    "account_type": "exchange_account",
                    "base_currency": "USD",
                },
                "balances": [
                    {"currency": "USD", "cash_value": 1500},
                    {"currency": "USDT", "value": 500},
                ],
                "positions": [
                    {
                        "symbol": "BTC",
                        "name": "Bitcoin",
                        "asset_type": "crypto",
                        "market": "CRYPTO",
                        "venue": "binance",
                        "currency": "USD",
                        "quantity": 2,
                        "average_cost": 42000,
                        "market_price": 45000,
                    },
                    {
                        "symbol": "ETH",
                        "name": "Ethereum",
                        "asset_type": "crypto",
                        "market": "CRYPTO",
                        "venue": "binance",
                        "currency": "USD",
                        "quantity": 10,
                        "average_cost": 2800,
                        "market_price": 3000,
                    },
                ],
                "orders": [
                    {"provider_order_id": "order-1", "symbol": "BTC", "side": "buy", "status": "filled"},
                ],
            }
        },
    )

    assert sync_response.status_code == 201
    payload = sync_response.json()
    assert payload["positions_synced"] == 2
    assert payload["balances_synced"] == 2
    assert payload["orders_seen"] == 1
    assert payload["account"]["mode"] == "read_only"
    assert payload["account"]["live_trading_enabled"] is False
    assert payload["snapshot"]["snapshot_type"] == "read_only_account"
    assert payload["snapshot"]["metadata_json"]["execution_available"] is False
    assert payload["snapshot"]["metadata_json"]["withdrawals_allowed"] is False
    assert payload["snapshot"]["metadata_json"]["account_id"] == payload["account"]["id"]
    assert payload["quality_report"]["metric_type"] == "account_sync_completeness"
    assert payload["quality_report"]["score"] == 1
    assert payload["catalog_entry"]["data_snapshot_id"] == payload["snapshot"]["id"]
    assert payload["ledger_sync"]["entries_created"] >= 2
    assert payload["reconciliation"]["run_id"]
    assert payload["reconciliation"]["status"] == "ok"
    assert payload["portfolio_snapshot"]["positions_value"] == 120000
    assert payload["portfolio_snapshot"]["cash_value"] == 2000
    assert payload["portfolio_snapshot"]["total_value"] == 122000

    accounts = client.get("/accounts").json()
    account = next(row for row in accounts if row["id"] == payload["account"]["id"])
    assert account["broker"] == "cex_readonly"
    assert account["live_trading_enabled"] is False

    assets = client.get("/assets").json()
    imported_assets = {asset["symbol"]: asset for asset in assets if asset["symbol"] in {"BTC", "ETH"}}
    assert set(imported_assets) == {"BTC", "ETH"}
    assert all(asset["tradable"] is False and asset["manual_enabled"] is False and asset["auto_enabled"] is False for asset in imported_assets.values())

    positions = client.get("/positions").json()
    synced_positions = [row for row in positions if row["account_id"] == payload["account"]["id"]]
    assert len(synced_positions) == 2
    assert sum(position["market_value"] for position in synced_positions) == 120000

    snapshots_response = client.get("/data-pipeline/snapshots?snapshot_type=read_only_account")
    assert snapshots_response.status_code == 200
    assert snapshots_response.json()[0]["id"] == payload["snapshot"]["id"]

    explanation_response = client.get(f"/data-pipeline/quality-reports/{payload['quality_report']['id']}/explain")
    assert explanation_response.status_code == 200
    explanation = explanation_response.json()
    assert explanation["level"] == "good"
    assert explanation["blocks_trading_decisions"] is False

    catalog_response = client.get("/data-catalog/entries?dataset_type=read_only_account")
    assert catalog_response.status_code == 200
    catalog_entries = catalog_response.json()
    assert len(catalog_entries) == 1
    assert catalog_entries[0]["data_snapshot_id"] == payload["snapshot"]["id"]
    assert catalog_entries[0]["quality_status"] == "VALID"
    assert catalog_entries[0]["usable_for_trading"] is False

    audit_logs = client.get("/audit-logs").json()
    actions = {log["action"] for log in audit_logs}
    assert {
        "data_source.account_synced_read_only",
        "data_snapshot.account_created_from_data_source",
        "data_snapshot.account_evidence_chain_completed",
        "data_catalog.entry_created",
    }.issubset(actions)


def test_account_auto_refresh_retries_with_backoff_recovers_and_exposes_history(client: TestClient) -> None:
    create_response = client.post(
        "/data-sources/connections",
        json={
            "name": "Recovering read-only CEX",
            "provider": "cex_readonly",
            "source_type": "exchange_account",
            "mode": "read_only",
            "config_json": {},
        },
    )
    assert create_response.status_code == 201
    connection = create_response.json()

    configure = client.put(
        f"/data-sources/connections/{connection['id']}/auto-refresh",
        json={"user_id": "refresh-user", "enabled": True, "interval_minutes": 15},
    )
    assert configure.status_code == 200
    configured = configure.json()
    assert configured["status"] == "active"
    assert configured["schedule"]["retry_policy"] == {"base_seconds": 30, "max_seconds": 1800}
    assert configured["execution_available"] is False

    db_generator = app.dependency_overrides[get_db]()
    db = next(db_generator)
    try:
        first_attempt = datetime(2026, 7, 16, 4, 0, tzinfo=timezone.utc)
        first_run = RuntimeSchedulerService(db).run_due_jobs_once(current_time=first_attempt)
        assert first_run["jobs_run"] == 1
        assert first_run["results"][0]["status"] == "retry_scheduled"

        rate_limited = RuntimeSchedulerService(db).run_due_jobs_once(current_time=first_attempt + timedelta(seconds=20))
        assert rate_limited["jobs_run"] == 0

        second_failure = RuntimeSchedulerService(db).run_due_jobs_once(current_time=first_attempt + timedelta(seconds=31))
        assert second_failure["jobs_run"] == 1
        assert second_failure["results"][0]["status"] == "retry_scheduled"

        stored_connection = db.get(DataSourceConnection, connection["id"])
        stored_connection.config_json = {
            "sample_snapshot": {
                "as_of": (first_attempt + timedelta(seconds=92)).isoformat(),
                "account": {"account_id": "recovered-cex", "label": "main", "base_currency": "USD"},
                "balances": [{"currency": "USD", "cash_value": 5000}],
                "positions": [],
                "orders": [],
            }
        }
        db.add(stored_connection)
        db.commit()

        recovered = RuntimeSchedulerService(db).run_due_jobs_once(current_time=first_attempt + timedelta(seconds=92))
        assert recovered["jobs_run"] == 1
        assert recovered["results"][0]["status"] == "succeeded"
    finally:
        db.close()
        db_generator.close()

    history_response = client.get(
        f"/data-sources/connections/{connection['id']}/sync-history?user_id=refresh-user"
    )
    assert history_response.status_code == 200
    history = history_response.json()
    assert history["job"]["last_run_status"] == "succeeded"
    assert history["job"]["last_run_summary"]["consecutive_failures"] == 0
    assert [item["status"] for item in history["history"]] == ["succeeded", "retry_scheduled", "retry_scheduled"]
    assert history["history"][1]["details"]["retry_delay_seconds"] == 60
    assert history["history"][2]["details"]["retry_delay_seconds"] == 30
    assert "api_key" not in json.dumps(history).lower()
    assert history["execution_available"] is False


def test_binance_spot_authenticated_readonly_adapter_signs_and_syncs_account(client: TestClient, monkeypatch) -> None:
    seen: dict[str, object] = {}

    monkeypatch.setenv(
        "BINANCE_READONLY_CREDENTIALS",
        json.dumps({"api_key": "unit-test-api-key", "api_secret": "unit-test-api-secret"}),
    )

    def fake_open(request, *, timeout):
        parsed = urlparse(request.full_url)
        query = parse_qs(parsed.query)
        seen["url"] = request.full_url
        seen["headers"] = dict(request.header_items())
        seen["timeout"] = timeout
        assert parsed.path == "/api/v3/account"
        assert "timestamp" in query
        assert query["recvWindow"] == ["5000"]
        assert query["omitZeroBalances"] == ["true"]
        assert query.get("signature", [""])[0]
        assert dict(request.header_items())["X-mbx-apikey"] == "unit-test-api-key"
        return FakeUrlResponse(
            {
                "accountType": "SPOT",
                "canTrade": False,
                "canWithdraw": False,
                "updateTime": 1717588800000,
                "permissions": ["SPOT"],
                "balances": [
                    {"asset": "USDT", "free": "125.5", "locked": "0"},
                    {"asset": "BTC", "free": "0.25", "locked": "0.05"},
                    {"asset": "ZERO", "free": "0", "locked": "0"},
                ],
            }
        )

    monkeypatch.setattr(readonly_adapters, "open_readonly_url", fake_open)

    setup_response = client.post(
        "/data-sources/connections/read-only-setup",
        json={
            "provider": "binance_spot_readonly",
            "account_label": "main",
            "credentials_ref": "env:BINANCE_READONLY_CREDENTIALS",
            "config_json": {"account_label": "main", "base_currency": "USD", "timeout_seconds": 3},
        },
    )
    assert setup_response.status_code == 201
    connection = setup_response.json()["connection"]

    preflight_response = client.post(f"/data-sources/connections/{connection['id']}/read-only-preflight")
    assert preflight_response.status_code == 200
    assert preflight_response.json()["status"] == "ready_for_sample_sync"

    sync_response = client.post(f"/data-sources/connections/{connection['id']}/sync-account", json={})

    assert sync_response.status_code == 201
    payload = sync_response.json()
    assert seen["timeout"] == 3
    assert payload["balances_synced"] == 2
    assert payload["positions_synced"] == 2
    assert payload["orders_seen"] == 0
    assert payload["account"]["broker"] == "binance_spot_readonly"
    assert payload["snapshot"]["data_json"]["account"]["provider_account_type"] == "SPOT"
    assert "market_value_unpriced:BTC" in payload["snapshot"]["data_json"]["warnings"]
    assert payload["snapshot"]["metadata_json"]["execution_available"] is False
    assert payload["snapshot"]["metadata_json"]["withdrawals_allowed"] is False
    assert payload["quality_report"]["source"] == "binance_spot_readonly"
    assert float(payload["quality_report"]["score"]) < 0.8


def test_ibkr_client_portal_authenticated_readonly_sync_uses_get_only_and_full_evidence_chain(client: TestClient, monkeypatch) -> None:
    seen: list[tuple[str, str]] = []

    def fake_urlopen(request, *, timeout, context):
        parsed = urlparse(request.full_url)
        seen.append((request.get_method(), parsed.path))
        assert timeout == 4
        if parsed.path == "/v1/api/portfolio/accounts":
            return FakeUrlResponse([{
                "id": "DU1234567",
                "accountId": "DU1234567",
                "displayName": "Paper Main",
                "currency": "USD",
                "brokerageAccess": True,
                "accountStatus": 1784217600000,
            }])
        if parsed.path == "/v1/api/portfolio/DU1234567/positions/0":
            return FakeUrlResponse([{
                "acctId": "DU1234567",
                "conid": 265598,
                "contractDesc": "AAPL",
                "assetClass": "STK",
                "currency": "USD",
                "position": 12,
                "avgCost": 180,
                "mktPrice": 225,
                "mktValue": 2700,
                "unrealizedPnl": 540,
                "realizedPnl": 0,
                "listingExchange": "NASDAQ",
            }])
        if parsed.path == "/v1/api/portfolio/DU1234567/ledger":
            return FakeUrlResponse({
                "USD": {
                    "currency": "USD",
                    "cashbalance": 5000,
                    "settledcash": 4800,
                    "netliquidationvalue": 7700,
                    "exchangerate": 1,
                    "timestamp": 1784217600000,
                }
            })
        raise AssertionError(f"unexpected IBKR path: {parsed.path}")

    monkeypatch.setattr(readonly_adapters, "urlopen", fake_urlopen)
    setup = client.post(
        "/data-sources/connections/read-only-setup",
        json={
            "provider": "ibkr_readonly",
            "account_label": "paper-main",
            "credentials_ref": "secretref:IBKR_CLIENT_PORTAL_SESSION",
            "config_json": {
                "gateway_host": "127.0.0.1",
                "gateway_port": 5000,
                "account_id": "DU1234567",
                "timeout_seconds": 4,
                "allow_insecure_localhost": True,
            },
        },
    )
    assert setup.status_code == 201
    connection = setup.json()["connection"]
    assert "authenticated_account_snapshot" in connection["capabilities_json"]
    assert "account_sync_placeholder" not in connection["capabilities_json"]

    preflight = client.post(f"/data-sources/connections/{connection['id']}/read-only-preflight")
    assert preflight.status_code == 200
    assert preflight.json()["details"]["authenticated_sync_available"] is True

    response = client.post(
        f"/data-sources/connections/{connection['id']}/sync-account",
        json={"user_id": "ibkr-user"},
    )
    assert response.status_code == 201
    payload = response.json()
    assert seen == [
        ("GET", "/v1/api/portfolio/accounts"),
        ("GET", "/v1/api/portfolio/DU1234567/positions/0"),
        ("GET", "/v1/api/portfolio/DU1234567/ledger"),
    ]
    assert payload["account"]["broker"] == "ibkr_readonly"
    assert payload["account"]["live_trading_enabled"] is False
    assert payload["positions_synced"] == 1
    assert payload["balances_synced"] == 1
    assert payload["orders_seen"] == 0
    assert payload["snapshot"]["data_json"]["positions"][0]["symbol"] == "AAPL"
    assert payload["snapshot"]["data_json"]["balances"][0]["cash_value"] == 5000
    assert payload["snapshot"]["metadata_json"]["execution_available"] is False
    assert payload["snapshot"]["metadata_json"]["data_origin"] == "authenticated_provider"
    assert payload["snapshot"]["metadata_json"]["real_external_evidence"] is True
    assert payload["quality_report"]["score"] == 1
    assert payload["catalog_entry"]["data_snapshot_id"] == payload["snapshot"]["id"]
    assert payload["reconciliation"]["status"] == "ok"
    assert payload["reconciliation"]["run_id"]

    private_verify = client.post(
        "/phase-development/real-readonly-data-proof/ibkr-private-verify?user_id=ibkr-user",
        json={
            "gateway_session_proof_ref": "artifact://ibkr/gateway-session-redacted.png",
            "read_only_boundary_proof_ref": "artifact://ibkr/read-only-boundary-redacted.png",
            "verification_environment": "private_ci",
        },
    )
    assert private_verify.status_code == 200
    packet = private_verify.json()
    assert packet["status"] == "verified_private_readonly"
    assert packet["proof_checks"]["orders_endpoint_not_used"] is True
    assert packet["proof_checks"]["reconciliation_passed"] is True
    assert packet["audit_packet_artifact_id"]
    assert packet["execution_available"] is False


def test_ibkr_client_portal_rejects_insecure_remote_gateway(client: TestClient) -> None:
    setup = client.post(
        "/data-sources/connections/read-only-setup",
        json={
            "provider": "ibkr_readonly",
            "account_label": "unsafe-remote",
            "credentials_ref": "secretref:IBKR_REMOTE_SESSION",
            "config_json": {
                "gateway_host": "gateway.example.test",
                "gateway_port": 5000,
                "allow_insecure_localhost": True,
            },
        },
    )
    assert setup.status_code == 422
    assert "loopback Client Portal Gateway" in setup.json()["detail"]


def test_binance_account_sync_redacts_signed_provider_errors(client: TestClient, monkeypatch) -> None:
    secret_signature = "super-secret-signed-query"
    monkeypatch.setenv(
        "BINANCE_REDACTION_CREDENTIALS",
        json.dumps({"api_key": "redaction-api-key", "api_secret": "redaction-api-secret"}),
    )

    def fail_with_signed_url(request, *, timeout):
        raise ValueError(f"provider failed at {request.full_url}&debug={secret_signature}")

    monkeypatch.setattr(readonly_adapters, "open_readonly_url", fail_with_signed_url)
    setup = client.post(
        "/data-sources/connections/read-only-setup",
        json={
            "provider": "binance_spot_readonly",
            "account_label": "redaction-check",
            "credentials_ref": "env:BINANCE_REDACTION_CREDENTIALS",
            "config_json": {"account_label": "redaction-check"},
        },
    )
    assert setup.status_code == 201
    connection_id = setup.json()["connection"]["id"]

    response = client.post(f"/data-sources/connections/{connection_id}/sync-account", json={})
    assert response.status_code == 422
    assert secret_signature not in response.text
    assert "signature=" not in response.text

    connections = client.get("/data-sources/connections").json()
    connection = next(item for item in connections if item["id"] == connection_id)
    assert connection["last_error"] == "read_only_account_sync_failed:ValueError"
    assert secret_signature not in json.dumps(connection)
    history = client.get(f"/data-sources/connections/{connection_id}/sync-history").json()
    assert history["history"][0]["status"] == "failed"
    assert history["history"][0]["details"]["error_code"] == "ValueError"
    assert secret_signature not in json.dumps(history)


def test_binance_spot_authenticated_sync_fails_closed_when_provider_can_trade_or_withdraw(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv(
        "BINANCE_READONLY_CREDENTIALS",
        json.dumps({"api_key": "unit-test-api-key", "api_secret": "unit-test-api-secret"}),
    )

    setup_response = client.post(
        "/data-sources/connections/read-only-setup",
        json={
            "provider": "binance_spot_readonly",
            "account_label": "unsafe",
            "credentials_ref": "env:BINANCE_READONLY_CREDENTIALS",
            "config_json": {"account_label": "unsafe"},
        },
    )
    connection = setup_response.json()["connection"]

    for unsafe_flag in ("canTrade", "canWithdraw"):
        def fake_open(request, *, timeout, flag=unsafe_flag):
            return FakeUrlResponse({
                "accountType": "SPOT",
                "canTrade": flag == "canTrade",
                "canWithdraw": flag == "canWithdraw",
                "balances": [{"asset": "USDT", "free": "1", "locked": "0"}],
            })

        monkeypatch.setattr(readonly_adapters, "open_readonly_url", fake_open)
        response = client.post(f"/data-sources/connections/{connection['id']}/sync-account", json={})
        assert response.status_code == 422
        assert "failed closed" in response.json()["detail"]


def test_binance_private_verification_requires_and_records_full_trust_chain(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv(
        "BINANCE_PRIVATE_VERIFY_CREDENTIALS",
        json.dumps({"api_key": "unit-test-api-key", "api_secret": "unit-test-api-secret"}),
    )

    def fake_open(request, *, timeout):
        return FakeUrlResponse({
            "accountType": "SPOT",
            "canTrade": False,
            "canWithdraw": False,
            "updateTime": 1717588800000,
            "permissions": ["SPOT"],
            "balances": [{"asset": "USDT", "free": "125.5", "locked": "0"}],
        })

    monkeypatch.setattr(readonly_adapters, "open_readonly_url", fake_open)
    setup_response = client.post(
        "/data-sources/connections/read-only-setup",
        json={
            "provider": "binance_spot_readonly",
            "account_label": "verified",
            "credentials_ref": "env:BINANCE_PRIVATE_VERIFY_CREDENTIALS",
            "config_json": {"account_label": "verified", "base_currency": "USD"},
        },
    )
    assert setup_response.status_code == 201

    response = client.post(
        "/phase-development/real-readonly-data-proof/binance-private-verify?user_id=verified-user",
        json={
            "permission_screenshot_ref": "artifact://binance/permission-redacted.png",
            "withdrawal_disabled_proof_ref": "artifact://binance/withdrawal-disabled-redacted.png",
            "verification_environment": "private_ci",
        },
    )
    assert response.status_code == 200
    packet = response.json()
    assert packet["status"] == "verified_private_readonly"
    assert packet["sync_result"]["snapshot_id"]
    assert packet["sync_result"]["quality_report_id"]
    assert packet["sync_result"]["quality_score"] >= 0.8
    assert packet["sync_result"]["catalog_entry_id"]
    assert packet["ledger_sync"] is not None
    assert packet["reconciliation"]["status"] == "ok"
    assert all(packet["proof_checks"].values())
    assert packet["execution_available"] is False


def test_binance_readonly_evidence_preflight_records_safe_packet_without_external_call(client: TestClient) -> None:
    response = client.post(
        "/data-sources/binance/read-only-evidence/preflight?user_id=operator",
        json={
            "account_label": "main",
            "credentials_ref": "env://BINANCE_READONLY_CREDENTIALS",
            "permission_screenshot_ref": "artifact://binance/permission-redacted.png",
            "withdrawal_disabled_proof_ref": "artifact://binance/withdrawal-disabled-redacted.png",
            "verification_environment": "private_local",
        },
    )

    assert response.status_code == 200
    packet = response.json()
    assert packet["status"] == "preflight_ready"
    assert packet["provider"] == "binance_spot_readonly"
    assert packet["external_api_called"] is False
    assert packet["execution_available"] is False
    assert packet["withdrawals_allowed"] is False
    assert packet["proof_checks"]["secret_reference_recorded"] is True
    assert packet["proof_checks"]["permission_screenshot_recorded"] is True
    assert packet["proof_checks"]["withdrawal_disabled_proof_recorded"] is True
    assert packet["evidence_refs"]["credentials_ref"] == "redacted"
    assert packet["required_evidence"][0]["key"] == "secret_reference"
    assert any(item["key"] == "quality_report" for item in packet["required_evidence"])
    assert any("withdrawals are disabled" in step for step in packet["private_verification_runbook"])
    assert packet["private_verification_endpoints"]["sync_account"].endswith("/sync-account")
    assert packet["private_verification_endpoints"]["phase_private_verify"].endswith("/binance-private-verify")
    assert packet["audit_packet_artifact_id"]

    audit_logs = client.get("/audit-logs").json()
    assert "data_source_connection.binance_readonly_evidence_preflight" in {log["action"] for log in audit_logs}


def test_mock_quote_import_creates_snapshot_quality_report_and_audit(client: TestClient) -> None:
    connection = create_mock_connection(client)

    health_response = client.post(f"/data-sources/connections/{connection['id']}/health")
    assert health_response.status_code == 200
    assert health_response.json()["status"] == "ok"

    import_response = client.post(
        f"/data-sources/connections/{connection['id']}/import-quotes",
        json={"symbols": ["AAPL", "NVDA"], "asset_type": "stock", "market": "US", "currency": "USD"},
    )

    assert import_response.status_code == 201
    payload = import_response.json()
    assert payload["quotes_imported"] == 2
    assert payload["symbols"] == ["AAPL", "NVDA"]
    assert payload["snapshot"]["snapshot_type"] == "market_quotes"
    assert payload["snapshot"]["metadata_json"]["mode"] == "read_only"
    assert payload["quality_report"]["score"] == 1

    snapshots_response = client.get("/data-pipeline/snapshots?snapshot_type=market_quotes")
    assert snapshots_response.status_code == 200
    assert len(snapshots_response.json()) == 1

    quality_response = client.get("/data-pipeline/quality-reports?source=mock_market_data")
    assert quality_response.status_code == 200
    assert len(quality_response.json()) == 1

    catalog_response = client.get("/data-catalog/entries?dataset_type=market_quotes")
    assert catalog_response.status_code == 200
    catalog_entries = catalog_response.json()
    assert len(catalog_entries) == 1
    assert catalog_entries[0]["row_count"] == 2
    assert catalog_entries[0]["quality_status"] == "VALID"
    assert catalog_entries[0]["usable_for_trading"] is True

    assets = client.get("/assets").json()
    aapl = next(asset for asset in assets if asset["symbol"] == "AAPL")
    assert aapl["tradable"] is False
    assert aapl["manual_enabled"] is False
    assert aapl["auto_enabled"] is False

    audit_logs = client.get("/audit-logs").json()
    actions = {log["action"] for log in audit_logs}
    assert {
        "data_source_connection.created",
        "data_source_connection.health_checked",
        "data_source.asset_imported_read_only",
        "data_source.quote_imported",
        "data_snapshot.created_from_data_source",
        "data_catalog.entry_created",
    }.issubset(actions)

    explanation_response = client.get(f"/data-pipeline/quality-reports/{payload['quality_report']['id']}/explain")
    assert explanation_response.status_code == 200
    explanation = explanation_response.json()
    assert explanation["level"] == "good"
    assert explanation["blocks_trading_decisions"] is False


def test_mock_candle_import_creates_rows_snapshot_quality_report_and_audit(client: TestClient) -> None:
    connection = create_mock_connection(client)

    import_response = client.post(
        f"/data-sources/connections/{connection['id']}/import-candles",
        json={"symbols": ["AAPL"], "timeframe": "1d", "limit": 5, "asset_type": "stock", "market": "US", "currency": "USD"},
    )

    assert import_response.status_code == 201
    payload = import_response.json()
    assert payload["candles_imported"] == 5
    assert payload["symbols"] == ["AAPL"]
    assert payload["timeframe"] == "1d"
    assert payload["snapshot"]["snapshot_type"] == "market_candles"
    assert payload["quality_report"]["metric_type"] == "candle_import_completeness"
    assert payload["quality_report"]["score"] == 1

    assets = client.get("/assets").json()
    aapl = next(asset for asset in assets if asset["symbol"] == "AAPL")
    candles_response = client.get(f"/candles?asset_id={aapl['id']}&timeframe=1d&limit=10")
    assert candles_response.status_code == 200
    candles = candles_response.json()
    assert len(candles) == 5
    assert all(candle["timeframe"] == "1d" for candle in candles)

    snapshots_response = client.get("/data-pipeline/snapshots?snapshot_type=market_candles")
    assert snapshots_response.status_code == 200
    assert len(snapshots_response.json()) == 1

    catalog_response = client.get("/data-catalog/entries?dataset_type=market_candles")
    assert catalog_response.status_code == 200
    catalog_entries = catalog_response.json()
    assert len(catalog_entries) == 1
    assert catalog_entries[0]["row_count"] == 5
    assert catalog_entries[0]["usable_for_trading"] is True

    audit_logs = client.get("/audit-logs").json()
    actions = {log["action"] for log in audit_logs}
    assert {
        "data_source.candle_imported",
        "data_snapshot.candles_created_from_data_source",
        "data_catalog.entry_created",
    }.issubset(actions)


def test_reimporting_same_mock_candles_upserts_without_duplicates(client: TestClient) -> None:
    connection = create_mock_connection(client)

    first = client.post(
        f"/data-sources/connections/{connection['id']}/import-candles",
        json={"symbols": ["NVDA"], "timeframe": "1d", "limit": 3},
    )
    assert first.status_code == 201

    second = client.post(
        f"/data-sources/connections/{connection['id']}/import-candles",
        json={"symbols": ["NVDA"], "timeframe": "1d", "limit": 3},
    )
    assert second.status_code == 201
    assert second.json()["candles_imported"] == 3

    assets = client.get("/assets").json()
    nvda = next(asset for asset in assets if asset["symbol"] == "NVDA")
    candles = client.get(f"/candles?asset_id={nvda['id']}&timeframe=1d&limit=10").json()
    assert len(candles) == 3


def test_custom_http_connection_is_registered_but_fails_closed_until_configured(client: TestClient) -> None:
    create_response = client.post(
        "/data-sources/connections",
        json={"name": "Custom Placeholder", "provider": "custom_http_readonly", "mode": "read_only"},
    )
    assert create_response.status_code == 201
    connection = create_response.json()
    assert connection["status"] == "unconfigured"

    health_response = client.post(f"/data-sources/connections/{connection['id']}/health")
    assert health_response.status_code == 200
    assert health_response.json()["status"] == "unconfigured"

    import_response = client.post(
        f"/data-sources/connections/{connection['id']}/import-quotes",
        json={"symbols": ["AAPL"]},
    )
    assert import_response.status_code == 422
    assert "unconfigured" in import_response.json()["detail"]


def test_scheduled_quote_import_runs_manually_and_remains_read_only(client: TestClient) -> None:
    connection = create_mock_connection(client)

    create_response = client.post(
        "/scheduled-jobs",
        json={
            "name": "Refresh mock quotes",
            "job_type": "quote_import",
            "status": "active",
            "schedule_json": {"mode": "manual", "interval_minutes": 60},
            "target_json": {"connection_id": connection["id"], "symbols": ["AAPL", "NVDA"], "asset_type": "stock", "market": "US"},
        },
    )
    assert create_response.status_code == 201
    job = create_response.json()

    run_response = client.post(f"/scheduled-jobs/{job['id']}/run")
    assert run_response.status_code == 200
    payload = run_response.json()
    assert payload["execution_available"] is False
    assert payload["job"]["last_run_status"] == "succeeded"
    assert payload["result"]["quotes_imported"] == 2

    jobs_response = client.get("/scheduled-jobs?job_type=quote_import")
    assert jobs_response.status_code == 200
    assert jobs_response.json()[0]["id"] == job["id"]


def test_scheduled_candle_import_runs_manually_and_remains_read_only(client: TestClient) -> None:
    connection = create_mock_connection(client)

    create_response = client.post(
        "/scheduled-jobs",
        json={
            "name": "Refresh mock candles",
            "job_type": "candle_import",
            "status": "active",
            "schedule_json": {"mode": "manual", "interval_minutes": 60},
            "target_json": {
                "connection_id": connection["id"],
                "symbols": ["AAPL", "NVDA"],
                "timeframe": "1d",
                "limit": 4,
                "asset_type": "stock",
                "market": "US",
            },
        },
    )
    assert create_response.status_code == 201
    job = create_response.json()

    run_response = client.post(f"/scheduled-jobs/{job['id']}/run")
    assert run_response.status_code == 200
    payload = run_response.json()
    assert payload["execution_available"] is False
    assert payload["job"]["last_run_status"] == "succeeded"
    assert payload["result"]["candles_imported"] == 8
    assert payload["result"]["timeframe"] == "1d"

    jobs_response = client.get("/scheduled-jobs?job_type=candle_import")
    assert jobs_response.status_code == 200
    assert jobs_response.json()[0]["id"] == job["id"]


def test_scheduled_signal_generate_runs_from_stored_candles_and_remains_read_only(client: TestClient) -> None:
    connection = create_mock_connection(client)

    candle_response = client.post(
        f"/data-sources/connections/{connection['id']}/import-candles",
        json={"symbols": ["AAPL"], "timeframe": "1d", "limit": 6, "asset_type": "stock", "market": "US", "currency": "USD"},
    )
    assert candle_response.status_code == 201

    create_response = client.post(
        "/scheduled-jobs",
        json={
            "name": "Generate swing signals",
            "job_type": "signal_generate",
            "status": "active",
            "schedule_json": {"mode": "manual", "interval_minutes": 60},
            "target_json": {
                "symbols": ["AAPL"],
                "signal_types": ["rsi", "ma_cross"],
                "horizon": "swing",
            },
        },
    )
    assert create_response.status_code == 201
    job = create_response.json()

    run_response = client.post(f"/scheduled-jobs/{job['id']}/run")
    assert run_response.status_code == 200
    payload = run_response.json()
    assert payload["execution_available"] is False
    assert payload["job"]["last_run_status"] == "succeeded"
    assert payload["result"]["signals_generated"] == 2
    assert payload["result"]["symbols"] == ["AAPL"]
    assert payload["result"]["horizon"] == "swing"

    signals_response = client.get("/signals?limit=10")
    assert signals_response.status_code == 200
    signal_types = {signal["signal_type"] for signal in signals_response.json()}
    assert {"rsi", "ma_cross"}.issubset(signal_types)

    jobs_response = client.get("/scheduled-jobs?job_type=signal_generate")
    assert jobs_response.status_code == 200
    assert jobs_response.json()[0]["id"] == job["id"]
