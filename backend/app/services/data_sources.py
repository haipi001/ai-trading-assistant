from dataclasses import dataclass
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.market_data_readonly import AdapterHealth
from app.adapters.market_data_readonly import BinanceSpotReadOnlyAccountAdapter
from app.adapters.market_data_readonly import CustomHttpReadOnlyMarketDataAdapter
from app.adapters.market_data_readonly import IbkrClientPortalReadOnlyAccountAdapter
from app.adapters.market_data_readonly import MockReadOnlyMarketDataAdapter
from app.adapters.market_data_readonly import PlaceholderReadOnlyAccountAdapter
from app.adapters.market_data_readonly import ReadOnlyAccountSnapshot
from app.adapters.market_data_readonly import ReadOnlyMarketDataAdapter
from app.adapters.market_data_readonly import StooqPublicMarketDataAdapter
from app.adapters.market_data_readonly import YahooFinancePublicMarketDataAdapter
from app.adapters.mock import MOCK_ASSETS
from app.adapters.types import AdapterQuote
from app.api.domain import write_audit_log
from app.models import Account
from app.models import Asset
from app.models import AuditLog
from app.models import Candle
from app.models import DataCatalogEntry
from app.models import DataQualityReport
from app.models import DataSnapshot
from app.models import DataSourceConnection
from app.models import ExportArtifact
from app.models import OperationalEvent
from app.models import PortfolioSnapshot
from app.models import Position
from app.models import Quote
from app.models import ScheduledJob
from app.schemas.core import contains_secret_config_key
from app.schemas.core import looks_like_inline_secret_reference
from app.services.data_catalog import DataCatalogService
from app.services.mock_import import update_positions_from_quotes


class DataSourceError(ValueError):
    pass


class DataSourceNotFoundError(DataSourceError):
    pass


class DataSourceProviderError(DataSourceError):
    pass


@dataclass(frozen=True)
class DataSourceProviderSpec:
    provider: str
    display_name: str
    source_type: str
    mode: str
    capabilities: list[str]
    status: str
    requires_credentials: bool
    supports_custom_config: bool
    config_schema: dict[str, Any]
    notes: str


@dataclass(frozen=True)
class QuoteImportResult:
    connection: DataSourceConnection
    quotes_imported: int
    symbols: list[str]
    skipped: list[dict[str, str]]
    snapshot: DataSnapshot
    quality_report: DataQualityReport
    catalog_entry: DataCatalogEntry


@dataclass(frozen=True)
class CandleImportResult:
    connection: DataSourceConnection
    candles_imported: int
    symbols: list[str]
    timeframe: str
    skipped: list[dict[str, str]]
    snapshot: DataSnapshot
    quality_report: DataQualityReport
    catalog_entry: DataCatalogEntry


@dataclass(frozen=True)
class AccountSyncResult:
    connection: DataSourceConnection
    account: Account | None
    positions_synced: int
    balances_synced: int
    orders_seen: int
    snapshot: DataSnapshot
    quality_report: DataQualityReport
    portfolio_snapshot: PortfolioSnapshot | None
    catalog_entry: DataCatalogEntry
    ledger_sync: dict[str, Any]
    reconciliation: dict[str, Any]


@dataclass(frozen=True)
class ReadOnlySetupResult:
    connection: DataSourceConnection
    provider_status: str
    safety_checks: list[str]
    next_actions: list[str]


@dataclass(frozen=True)
class ReadOnlyPreflightResult:
    connection: DataSourceConnection
    provider: str
    status: str
    checked_at: datetime
    has_credentials_ref: bool
    requires_credentials: bool
    missing_requirements: list[str]
    blocking_reasons: list[str]
    safety_checks: list[str]
    next_actions: list[str]
    details: dict[str, Any]
    execution_available: bool = False
    order_routing_available: bool = False
    withdrawals_allowed: bool = False
    signing_available: bool = False


@dataclass(frozen=True)
class ReadOnlyCertificationResult:
    connection: DataSourceConnection
    provider: str
    status: str
    checked_at: datetime
    certification_level: str
    sample_sync_allowed: bool
    contract_version: str
    required_scopes: list[str]
    forbidden_scopes: list[str]
    blockers: list[str]
    warnings: list[str]
    next_actions: list[str]
    preflight: dict[str, Any]
    adapter_contract: dict[str, Any]
    execution_available: bool = False


ACCOUNT_PROVIDER_IDS = {"ibkr_readonly", "futu_readonly", "cex_readonly", "binance_spot_readonly", "wallet_readonly"}

FRESHNESS_POLICIES: dict[str, tuple[str, timedelta]] = {
    "market_quotes": ("Market quotes", timedelta(hours=24)),
    "market_candles": ("Market candles", timedelta(days=7)),
    "read_only_account": ("Read-only account snapshot", timedelta(hours=24)),
    "fx_rates": ("FX rates", timedelta(days=2)),
    "corporate_actions": ("Corporate actions", timedelta(days=14)),
    "csv_holdings": ("CSV holdings", timedelta(days=30)),
    "csv_crypto_holdings": ("CSV crypto holdings", timedelta(days=30)),
    "csv_wallet_balances": ("CSV wallet balances", timedelta(days=30)),
    "csv_trades": ("CSV trades", timedelta(days=30)),
}

DATASET_FALLBACK_PROVIDERS: dict[str, list[str]] = {
    "market_quotes": ["yfinance_public", "stooq_public_eod", "mock_market_data", "manual_review"],
    "market_candles": ["yfinance_public", "stooq_public_eod", "manual_review"],
    "read_only_account": ["binance_spot_readonly", "cex_readonly", "ibkr_readonly", "futu_readonly", "manual_csv"],
    "fx_rates": ["ecb_reference_rates", "manual_csv"],
    "corporate_actions": ["nasdaq_public_dividends", "manual_csv"],
    "csv_holdings": ["manual_csv"],
    "csv_crypto_holdings": ["manual_csv"],
    "csv_wallet_balances": ["manual_csv"],
    "csv_trades": ["manual_csv"],
}


PROVIDER_SPECS: dict[str, DataSourceProviderSpec] = {
    "mock_market_data": DataSourceProviderSpec(
        provider="mock_market_data",
        display_name="Mock Market Data",
        source_type="market_data",
        mode="read_only",
        capabilities=["quotes", "symbols", "offline_tests"],
        status="available",
        requires_credentials=False,
        supports_custom_config=False,
        config_schema={},
        notes="Deterministic local read-only data for tests and demos.",
    ),
    "stooq_public_eod": DataSourceProviderSpec(
        provider="stooq_public_eod",
        display_name="Stooq Public EOD",
        source_type="market_data",
        mode="read_only",
        capabilities=["quotes", "delayed_public_market_data", "no_credentials"],
        status="available",
        requires_credentials=False,
        supports_custom_config=True,
        config_schema={
            "default_suffix": ".us",
            "symbol_map": {"BRK.B": "brk-b.us"},
            "timeout_seconds": 5,
        },
        notes="Read-only public market data connector. Intended for delayed quote ingestion, not execution.",
    ),
    "yfinance_public": DataSourceProviderSpec(
        provider="yfinance_public",
        display_name="Yahoo Finance Public",
        source_type="market_data",
        mode="read_only",
        capabilities=["quotes", "candles", "hourly_intraday", "no_credentials"],
        status="available",
        requires_credentials=False,
        supports_custom_config=True,
        config_schema={
            "timeout_seconds": 5,
            "health_symbol": "AAPL",
            "symbol_map": {"BRK.B": "BRK-B"},
        },
        notes="Read-only Yahoo Finance chart connector for public quotes and daily/hourly candles. No order routing or live execution is available.",
    ),
    "custom_http_readonly": DataSourceProviderSpec(
        provider="custom_http_readonly",
        display_name="Custom HTTP Read-only",
        source_type="market_data",
        mode="read_only",
        capabilities=["quotes", "custom_http_json", "credentials_ref_ready"],
        status="interface_ready",
        requires_credentials=False,
        supports_custom_config=True,
        config_schema={
            "quote_url_template": "https://example.com/quote/{symbol}",
            "price_path": "data.price",
            "bid_path": "data.bid",
            "ask_path": "data.ask",
            "as_of_path": "data.as_of",
            "headers": {"User-Agent": "ai-trading-os-readonly"},
        },
        notes="Extension point for later custom providers. Store secret references in credentials_ref, never in config_json.",
    ),
    "ibkr_readonly": DataSourceProviderSpec(
        provider="ibkr_readonly",
        display_name="IBKR Read-only",
        source_type="broker_account",
        mode="read_only",
        capabilities=["authenticated_account_snapshot", "portfolio_accounts_read", "positions_read", "cash_balances_read", "gateway_session_required", "order_routing_forbidden"],
        status="adapter_ready_private_verification_required",
        requires_credentials=True,
        supports_custom_config=True,
        config_schema={"gateway_host": "127.0.0.1", "gateway_port": 5000, "account_id": "DUxxxx", "allow_insecure_localhost": True},
        notes="Authenticated IBKR Client Portal Gateway read-only adapter. It only calls portfolio account, position, and ledger GET endpoints; private verification is still required.",
    ),
    "futu_readonly": DataSourceProviderSpec(
        provider="futu_readonly",
        display_name="Futu Read-only",
        source_type="broker_account",
        mode="read_only",
        capabilities=["account_sync_placeholder", "positions_placeholder", "cash_balances_placeholder", "quotes_placeholder"],
        status="interface_ready",
        requires_credentials=True,
        supports_custom_config=True,
        config_schema={"host": "127.0.0.1", "port": 11111, "market": "US"},
        notes="Read-only Futu account integration placeholder. It is fail-closed until credentials_ref/local gateway config is provided.",
    ),
    "cex_readonly": DataSourceProviderSpec(
        provider="cex_readonly",
        display_name="CEX Read-only",
        source_type="exchange_account",
        mode="read_only",
        capabilities=["balances_placeholder", "positions_placeholder", "quotes_placeholder", "withdrawals_forbidden"],
        status="interface_ready",
        requires_credentials=True,
        supports_custom_config=True,
        config_schema={"exchange": "binance|coinbase|okx", "account_label": "main"},
        notes="Read-only centralized exchange integration placeholder. API keys must be read-only and withdrawal-disabled.",
    ),
    "binance_spot_readonly": DataSourceProviderSpec(
        provider="binance_spot_readonly",
        display_name="Binance Spot Read-only",
        source_type="exchange_account",
        mode="read_only",
        capabilities=[
            "authenticated_account_snapshot",
            "balances_read",
            "positions_from_balances",
            "withdrawals_forbidden",
            "order_routing_forbidden",
        ],
        status="interface_ready",
        requires_credentials=True,
        supports_custom_config=True,
        config_schema={
            "account_label": "main",
            "base_currency": "USD",
            "timeout_seconds": 8,
            "recv_window_ms": 5000,
            "omit_zero_balances": True,
        },
        notes="Authenticated Binance Spot account adapter. credentials_ref must point to env JSON with api_key and api_secret; no orders, withdrawals, or trading endpoints are exposed.",
    ),
    "wallet_readonly": DataSourceProviderSpec(
        provider="wallet_readonly",
        display_name="Wallet Read-only",
        source_type="wallet_account",
        mode="read_only",
        capabilities=["balances_placeholder", "positions_placeholder", "onchain_history_placeholder", "signing_forbidden"],
        status="interface_ready",
        requires_credentials=False,
        supports_custom_config=True,
        config_schema={"chain_id": "1", "public_address": "0x...", "account_label": "cold-wallet"},
        notes="Read-only public wallet integration placeholder. It can ingest public balances/positions only and never signs transactions.",
    ),
}


DEFAULT_CONNECTIONS = [
    {
        "name": "Mock Market Data Read-only",
        "provider": "mock_market_data",
        "source_type": "market_data",
        "mode": "read_only",
        "status": "configured",
        "capabilities_json": PROVIDER_SPECS["mock_market_data"].capabilities,
        "config_json": {},
    },
    {
        "name": "Stooq Public EOD Read-only",
        "provider": "stooq_public_eod",
        "source_type": "market_data",
        "mode": "read_only",
        "status": "configured",
        "capabilities_json": PROVIDER_SPECS["stooq_public_eod"].capabilities,
        "config_json": {"default_suffix": ".us", "timeout_seconds": 5},
    },
    {
        "name": "Yahoo Finance Public Read-only",
        "provider": "yfinance_public",
        "source_type": "market_data",
        "mode": "read_only",
        "status": "configured",
        "capabilities_json": PROVIDER_SPECS["yfinance_public"].capabilities,
        "config_json": {"timeout_seconds": 12, "health_symbol": "AAPL"},
    },
]

READONLY_ACCOUNT_CONNECTIONS = [
    {
        "name": "IBKR Read-only Placeholder",
        "provider": "ibkr_readonly",
        "source_type": "broker_account",
        "mode": "read_only",
        "status": "unconfigured",
        "capabilities_json": PROVIDER_SPECS["ibkr_readonly"].capabilities,
        "config_json": {"execution_available": False, "order_routing_available": False},
    },
    {
        "name": "Futu Read-only Placeholder",
        "provider": "futu_readonly",
        "source_type": "broker_account",
        "mode": "read_only",
        "status": "unconfigured",
        "capabilities_json": PROVIDER_SPECS["futu_readonly"].capabilities,
        "config_json": {"execution_available": False, "order_routing_available": False},
    },
    {
        "name": "CEX Read-only Placeholder",
        "provider": "cex_readonly",
        "source_type": "exchange_account",
        "mode": "read_only",
        "status": "unconfigured",
        "capabilities_json": PROVIDER_SPECS["cex_readonly"].capabilities,
        "config_json": {"execution_available": False, "withdrawals_allowed": False, "order_routing_available": False},
    },
    {
        "name": "Binance Spot Read-only",
        "provider": "binance_spot_readonly",
        "source_type": "exchange_account",
        "mode": "read_only",
        "status": "unconfigured",
        "capabilities_json": PROVIDER_SPECS["binance_spot_readonly"].capabilities,
        "config_json": {"execution_available": False, "withdrawals_allowed": False, "order_routing_available": False},
    },
    {
        "name": "Wallet Read-only Placeholder",
        "provider": "wallet_readonly",
        "source_type": "wallet_account",
        "mode": "read_only",
        "status": "unconfigured",
        "capabilities_json": PROVIDER_SPECS["wallet_readonly"].capabilities,
        "config_json": {"execution_available": False, "signing_available": False, "withdrawals_allowed": False},
    },
]


class DataSourceService:
    def __init__(self, db: Session):
        self.db = db

    def list_providers(self) -> list[DataSourceProviderSpec]:
        return list(PROVIDER_SPECS.values())

    def list_connections(self) -> list[DataSourceConnection]:
        return list(
            self.db.scalars(
                select(DataSourceConnection).order_by(DataSourceConnection.created_at.desc(), DataSourceConnection.id.desc())
            ).all()
        )

    def ensure_default_connections(self) -> list[DataSourceConnection]:
        return self._ensure_connections(DEFAULT_CONNECTIONS, action="data_source_connection.default_created")

    def ensure_readonly_account_placeholders(self) -> list[DataSourceConnection]:
        return self._ensure_connections(READONLY_ACCOUNT_CONNECTIONS, action="data_source_connection.readonly_account_placeholder_created")

    def setup_readonly_connection(
        self,
        *,
        provider: str,
        name: str | None = None,
        account_label: str | None = None,
        credentials_ref: str | None = None,
        config_json: dict[str, Any] | None = None,
    ) -> ReadOnlySetupResult:
        if provider not in ACCOUNT_PROVIDER_IDS:
            raise DataSourceProviderError(f"unsupported read-only account provider: {provider}")
        config = dict(config_json or {})
        if contains_secret_config_key(config):
            raise DataSourceProviderError("config_json must not contain inline secrets; use credentials_ref instead")
        if provider == "ibkr_readonly":
            gateway_host = str(config.get("gateway_host") or "127.0.0.1").strip().lower()
            if config.get("allow_insecure_localhost") is True and gateway_host not in {"127.0.0.1", "localhost", "::1"}:
                raise DataSourceProviderError("IBKR insecure TLS is allowed only for a loopback Client Portal Gateway")
        clean_credentials_ref = (credentials_ref or "").strip() or None
        if clean_credentials_ref and looks_like_inline_secret_reference(clean_credentials_ref):
            raise DataSourceProviderError("credentials_ref must point to a stored reference, not an inline secret")
        if clean_credentials_ref and len(clean_credentials_ref) > 255:
            raise DataSourceProviderError("credentials_ref is too long")

        spec = PROVIDER_SPECS[provider]
        label = str(account_label or config.get("account_label") or config.get("exchange") or config.get("public_address") or "primary").strip()
        if not label:
            label = "primary"
        effective_name = (name or f"{spec.display_name} · {label}").strip()
        safe_config = {
            **config,
            "account_label": label,
            "execution_available": False,
            "order_routing_available": False,
            "withdrawals_allowed": False,
            "signing_available": False,
            "inline_credentials_allowed": False,
        }
        provider_status = (
            "configured_pending_sync"
            if clean_credentials_ref or safe_config.get("sample_snapshot") or (provider == "wallet_readonly" and safe_config.get("public_address"))
            else "unconfigured"
        )

        connection = self.db.scalar(
            select(DataSourceConnection)
            .where(DataSourceConnection.provider == provider, DataSourceConnection.name == effective_name)
            .limit(1)
        )
        if connection is None:
            connection = self.db.scalar(
                select(DataSourceConnection)
                .where(DataSourceConnection.provider == provider, DataSourceConnection.status == "unconfigured")
                .order_by(DataSourceConnection.created_at.asc(), DataSourceConnection.id.asc())
                .limit(1)
            )

        action = "data_source_connection.readonly_setup_updated"
        if connection is None:
            connection = DataSourceConnection(
                name=effective_name,
                provider=provider,
                source_type=spec.source_type,
                mode="read_only",
                status=provider_status,
                credentials_ref=clean_credentials_ref,
                config_json=safe_config,
                capabilities_json=spec.capabilities,
            )
            self.db.add(connection)
            action = "data_source_connection.readonly_setup_created"
        else:
            connection.name = effective_name
            connection.provider = provider
            connection.source_type = spec.source_type
            connection.mode = "read_only"
            connection.status = provider_status
            connection.credentials_ref = clean_credentials_ref
            connection.config_json = safe_config
            connection.capabilities_json = spec.capabilities
            connection.last_error = None

        self.db.flush()
        self._audit(
            action=action,
            connection=connection,
            payload={
                "provider": provider,
                "source_type": connection.source_type,
                "has_credentials_ref": bool(clean_credentials_ref),
                "status": provider_status,
                "execution_available": False,
                "order_routing_available": False,
                "withdrawals_allowed": False,
                "signing_available": False,
            },
        )
        self.db.commit()
        self.db.refresh(connection)

        next_actions = (
            ["Run an authenticated read-only account sync and inspect the quality report before using it in daily review."]
            if provider in {"binance_spot_readonly", "ibkr_readonly"}
            else ["Run a read-only account sync with a sample snapshot to validate mapping before using it in daily review."]
        )
        if clean_credentials_ref:
            next_actions.append("Register the matching metadata-only SecretReference in Beta settings if it is not already listed.")
        elif spec.requires_credentials:
            next_actions.insert(0, "Attach a credentials_ref from env:, secretref:, vault:, keychain:, or local-secret: storage.")
        if provider == "wallet_readonly" and safe_config.get("public_address"):
            next_actions.append("Verify public chain balance ingestion against the read-only wallet address.")

        return ReadOnlySetupResult(
            connection=connection,
            provider_status=provider_status,
            safety_checks=[
                "Connection mode is read_only.",
                "No inline secrets are accepted in config_json.",
                "Execution, order routing, withdrawals, and signing remain unavailable.",
                "Only credential references are stored.",
            ],
            next_actions=next_actions,
        )

    def read_only_preflight(self, connection_id: str) -> ReadOnlyPreflightResult:
        connection = self._get_connection(connection_id)
        if connection.provider not in ACCOUNT_PROVIDER_IDS:
            raise DataSourceProviderError("read-only preflight is only available for broker/exchange/wallet account providers")

        spec = PROVIDER_SPECS[connection.provider]
        config = dict(connection.config_json or {})
        checked_at = datetime.now(timezone.utc)
        credentials_ref = (connection.credentials_ref or "").strip()
        has_credentials_ref = bool(credentials_ref)
        missing_requirements: list[str] = []
        blocking_reasons: list[str] = []

        if contains_secret_config_key(config):
            blocking_reasons.append("config_json_contains_inline_secret")
        if has_credentials_ref and looks_like_inline_secret_reference(credentials_ref):
            blocking_reasons.append("credentials_ref_looks_like_inline_secret")
        if spec.requires_credentials and not has_credentials_ref:
            missing_requirements.append("credentials_ref")

        required_config_keys = self._readonly_preflight_required_config_keys(connection.provider)
        for key in required_config_keys:
            if config.get(key) in (None, ""):
                missing_requirements.append(key)

        forbidden_truthy_flags = [
            "execution_available",
            "order_routing_available",
            "withdrawals_allowed",
            "signing_available",
            "trading_enabled",
            "live_trading_enabled",
            "auto_execute_enabled",
            "dex_swap_enabled",
        ]
        for flag in forbidden_truthy_flags:
            if config.get(flag) is True:
                blocking_reasons.append(f"{flag}_must_be_false")

        sample_snapshot = config.get("sample_snapshot")
        has_sample_snapshot = isinstance(sample_snapshot, dict) and bool(sample_snapshot)
        if blocking_reasons or missing_requirements:
            status = "blocked"
        elif has_sample_snapshot:
            status = "sample_sync_available"
        else:
            status = "ready_for_sample_sync"

        next_actions = self._readonly_preflight_next_actions(
            provider=connection.provider,
            status=status,
            missing_requirements=missing_requirements,
            has_credentials_ref=has_credentials_ref,
            has_sample_snapshot=has_sample_snapshot,
        )
        safety_checks = [
            "Connection mode is read_only.",
            "Inline secrets are rejected; only metadata and credential references may be stored.",
            "Execution, order routing, withdrawals, DEX swaps, and wallet signing remain unavailable.",
            "Preflight result is audited before account sync is attempted.",
        ]
        details = {
            "source_type": connection.source_type,
            "provider_status": connection.status,
            "required_config_keys": required_config_keys,
            "present_config_keys": sorted(config.keys()),
            "has_sample_snapshot": has_sample_snapshot,
            "authenticated_sync_available": connection.provider in {"binance_spot_readonly", "ibkr_readonly"} and has_credentials_ref and not blocking_reasons and not missing_requirements,
            "capabilities": connection.capabilities_json or spec.capabilities,
            "safe_to_sync_sample_only": status in {"ready_for_sample_sync", "sample_sync_available"},
        }

        self._audit(
            action="data_source_connection.readonly_preflight_checked",
            connection=connection,
            payload={
                "provider": connection.provider,
                "status": status,
                "has_credentials_ref": has_credentials_ref,
                "requires_credentials": spec.requires_credentials,
                "missing_requirements": missing_requirements,
                "blocking_reasons": blocking_reasons,
                "execution_available": False,
                "order_routing_available": False,
                "withdrawals_allowed": False,
                "signing_available": False,
            },
        )
        self.db.commit()
        self.db.refresh(connection)
        return ReadOnlyPreflightResult(
            connection=connection,
            provider=connection.provider,
            status=status,
            checked_at=checked_at,
            has_credentials_ref=has_credentials_ref,
            requires_credentials=spec.requires_credentials,
            missing_requirements=missing_requirements,
            blocking_reasons=blocking_reasons,
            safety_checks=safety_checks,
            next_actions=next_actions,
            details=details,
        )

    def binance_readonly_evidence_preflight(
        self,
        *,
        user_id: str = "default-user",
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = dict(payload or {})
        if contains_secret_config_key(payload):
            raise DataSourceProviderError("evidence packet must contain references only, never credentials")

        allowed_keys = {
            "account_label",
            "credentials_ref",
            "permission_screenshot_ref",
            "withdrawal_disabled_proof_ref",
            "operator_note",
            "verification_environment",
        }
        unknown_keys = sorted(set(payload) - allowed_keys)
        if unknown_keys:
            raise DataSourceProviderError(f"unsupported Binance evidence field(s): {', '.join(unknown_keys)}")

        credentials_ref = str(payload.get("credentials_ref") or "").strip()
        if credentials_ref and looks_like_inline_secret_reference(credentials_ref):
            raise DataSourceProviderError("credentials_ref must point to a stored reference, not an inline secret")

        permission_ref = str(payload.get("permission_screenshot_ref") or "").strip()
        withdrawal_ref = str(payload.get("withdrawal_disabled_proof_ref") or "").strip()
        account_label = str(payload.get("account_label") or "main").strip() or "main"
        connection = None
        if credentials_ref:
            setup = self.setup_readonly_connection(
                provider="binance_spot_readonly",
                account_label=account_label,
                credentials_ref=credentials_ref,
                config_json={
                    "account_label": account_label,
                    "base_currency": "USD",
                    "timeout_seconds": 8,
                    "recv_window_ms": 5000,
                    "omit_zero_balances": True,
                },
            )
            connection = setup.connection
        else:
            connection = self.db.scalar(
                select(DataSourceConnection)
                .where(DataSourceConnection.provider == "binance_spot_readonly")
                .order_by(DataSourceConnection.created_at.desc(), DataSourceConnection.id.desc())
                .limit(1)
            )

        generated_at = datetime.now(timezone.utc)
        blockers: list[str] = []
        if connection is None:
            blockers.append("binance_spot_readonly_connection_missing")
        if not credentials_ref and not (connection and connection.credentials_ref):
            blockers.append("credentials_ref_required")
        if not permission_ref:
            blockers.append("permission_screenshot_ref_required")
        if not withdrawal_ref:
            blockers.append("withdrawal_disabled_proof_ref_required")

        preflight_payload: dict[str, Any] | None = None
        certification_payload: dict[str, Any] | None = None
        if connection is not None:
            preflight = self.read_only_preflight(connection.id)
            certification = self.read_only_certification(connection.id)
            preflight_payload = {
                "status": preflight.status,
                "has_credentials_ref": preflight.has_credentials_ref,
                "missing_requirements": preflight.missing_requirements,
                "blocking_reasons": preflight.blocking_reasons,
                "authenticated_sync_available": preflight.details.get("authenticated_sync_available", False),
            }
            certification_payload = {
                "status": certification.status,
                "certification_level": certification.certification_level,
                "required_scopes": certification.required_scopes,
                "forbidden_scopes": certification.forbidden_scopes,
                "blockers": certification.blockers,
                "warnings": certification.warnings,
            }
            blockers.extend(preflight.blocking_reasons)
            blockers.extend(f"missing_requirement:{item}" for item in preflight.missing_requirements)
            blockers.extend(certification.blockers)

        blockers = dedupe(blockers)
        proof_checks = {
            "secret_reference_recorded": bool(credentials_ref or (connection and connection.credentials_ref)),
            "permission_screenshot_recorded": bool(permission_ref),
            "withdrawal_disabled_proof_recorded": bool(withdrawal_ref),
            "snapshot_contract_ready": connection is not None and not blockers,
            "quality_report_contract_ready": connection is not None and not blockers,
            "audit_packet_ready": True,
        }
        status = "preflight_ready" if not blockers else "needs_evidence"
        required_evidence = [
            {
                "key": "secret_reference",
                "label": "Secret Reference",
                "status": "recorded" if proof_checks["secret_reference_recorded"] else "missing",
                "description": "Reference to the private Binance read-only credential bundle; never paste api_key or api_secret.",
            },
            {
                "key": "permission_screenshot",
                "label": "Redacted permission screenshot",
                "status": "recorded" if permission_ref else "missing",
                "description": "Screenshot showing read-only/account permissions and no trade or withdrawal permissions.",
            },
            {
                "key": "withdrawal_disabled_proof",
                "label": "Withdrawal-disabled proof",
                "status": "recorded" if withdrawal_ref else "missing",
                "description": "Screenshot or exported proof that withdrawals are disabled for the key.",
            },
            {
                "key": "account_snapshot",
                "label": "Authenticated read-only account snapshot",
                "status": "pending_private_run",
                "description": "Created only after a private sync-account run with the referenced key.",
            },
            {
                "key": "quality_report",
                "label": "Snapshot quality report",
                "status": "pending_private_run",
                "description": "Generated from the private snapshot and reviewed before ledger promotion.",
            },
        ]
        runbook_steps = [
            "Create or verify a Binance Spot API key with read-only/account permissions only.",
            "Confirm trading, margin/futures, transfers, and withdrawals are disabled for that key.",
            "Store the key bundle in env, Vault, AWS Secrets Manager, GCP Secret Manager, keychain, or local secret storage.",
            "Paste only the Secret Reference into this app and keep screenshots as redacted evidence references.",
            "Run the private read-only account sync from the data source connection; do not enable order routing or withdrawals.",
            "Review the generated snapshot and quality report, then save them with this audit packet.",
            "Run the phase private verification packet and keep the result with the evidence bundle.",
        ]
        packet = {
            "user_id": user_id,
            "generated_at": generated_at.isoformat(),
            "status": status,
            "provider": "binance_spot_readonly",
            "connection_id": connection.id if connection else None,
            "evidence_refs": {
                "credentials_ref": "redacted" if credentials_ref or (connection and connection.credentials_ref) else None,
                "permission_screenshot_ref": permission_ref or None,
                "withdrawal_disabled_proof_ref": withdrawal_ref or None,
                "operator_note": str(payload.get("operator_note") or "").strip() or None,
                "verification_environment": str(payload.get("verification_environment") or "private_local").strip() or "private_local",
            },
            "proof_checks": proof_checks,
            "blockers": blockers,
            "preflight": preflight_payload,
            "certification": certification_payload,
            "required_evidence": required_evidence,
            "private_verification_runbook": runbook_steps,
            "private_verification_endpoints": {
                "sync_account": f"/data-sources/connections/{connection.id}/sync-account" if connection else None,
                "phase_private_verify": "/phase-development/real-readonly-data-proof/binance-private-verify",
            },
            "next_actions": [
                "Run the private Binance read-only sync only after the key is confirmed read-only and withdrawal-disabled.",
                "Save the real account snapshot, quality report, and this audit packet together.",
                "Keep the key in a Secret Manager or env reference; never paste the key or secret into the app.",
            ],
            "external_api_called": False,
            "snapshot_created": False,
            "quality_report_created": False,
            "execution_available": False,
            "order_routing_available": False,
            "withdrawals_allowed": False,
            "signing_available": False,
            "production_capability": False,
        }
        artifact = ExportArtifact(
            user_id=user_id,
            export_type="binance_readonly_evidence_preflight",
            format="json",
            status="ready" if status == "preflight_ready" else "blocked",
            payload_json=packet,
            summary_json={
                "provider": "binance_spot_readonly",
                "status": status,
                "contains_credentials": False,
                "external_api_called": False,
                "execution_available": False,
            },
            file_path=None,
        )
        self.db.add(artifact)
        self.db.flush()
        packet["audit_packet_artifact_id"] = artifact.id
        self.db.add(
            OperationalEvent(
                user_id=user_id,
                event_type="binance_readonly.evidence_preflight",
                severity="info" if status == "preflight_ready" else "warning",
                source="data-sources",
                message="Binance read-only evidence preflight completed.",
                status="closed",
                payload_json=packet,
            )
        )
        if connection is not None:
            self._audit(
                action="data_source_connection.binance_readonly_evidence_preflight",
                connection=connection,
                payload={
                    "provider": "binance_spot_readonly",
                    "status": status,
                    "blockers": blockers,
                    "external_api_called": False,
                    "execution_available": False,
                },
            )
        self.db.commit()
        return packet

    def read_only_certification(self, connection_id: str) -> ReadOnlyCertificationResult:
        preflight = self.read_only_preflight(connection_id)
        connection = preflight.connection
        spec = PROVIDER_SPECS[connection.provider]
        checked_at = datetime.now(timezone.utc)
        config = dict(connection.config_json or {})
        blockers = list(preflight.blocking_reasons) + [f"missing_requirement:{item}" for item in preflight.missing_requirements]
        warnings: list[str] = []
        if connection.status == "unconfigured":
            warnings.append("connection_status_unconfigured")
        authenticated_sync_provider = connection.provider in {"binance_spot_readonly", "ibkr_readonly"}
        if not preflight.details.get("has_sample_snapshot") and connection.provider in ACCOUNT_PROVIDER_IDS and not authenticated_sync_provider:
            warnings.append("sample_snapshot_not_recorded")

        required_scopes = required_readonly_scopes(connection.provider)
        forbidden_scopes = [
            "orders:write",
            "trades:execute",
            "withdrawals:write",
            "wallet:sign",
            "dex:swap",
            "margin:borrow",
        ]
        adapter_contract = {
            "contract_version": "readonly_adapter_v1",
            "provider": connection.provider,
            "source_type": connection.source_type,
            "mode": connection.mode,
            "required_config_keys": self._readonly_preflight_required_config_keys(connection.provider),
            "required_scopes": required_scopes,
            "forbidden_scopes": forbidden_scopes,
            "secret_reference_only": True,
            "inline_secrets_allowed": False,
            "network_order_submission_allowed": False,
            "execution_available": False,
            "order_routing_available": False,
            "withdrawals_allowed": False,
            "signing_available": False,
            "sample_snapshot_schema": sample_snapshot_schema(connection.provider),
        }
        if connection.mode != "read_only":
            blockers.append("connection_mode_must_be_read_only")
        if spec.mode != "read_only":
            blockers.append("provider_mode_must_be_read_only")
        if config.get("permissions"):
            declared = {str(item).lower() for item in as_list(config.get("permissions"))}
            forbidden_declared = sorted(declared & {scope.lower() for scope in forbidden_scopes})
            blockers.extend(f"forbidden_scope_declared:{scope}" for scope in forbidden_declared)

        blockers = dedupe(blockers)
        warnings = dedupe(warnings)
        sample_sync_allowed = not blockers and (
            preflight.status in {"ready_for_sample_sync", "sample_sync_available"} or authenticated_sync_provider
        )
        if blockers:
            status = "blocked"
            certification_level = "not_certified"
        elif authenticated_sync_provider and not warnings:
            status = "certified_authenticated_readonly_sync"
            certification_level = "authenticated_read_only"
        elif warnings:
            status = "review_required"
            certification_level = "sample_sync_only"
        else:
            status = "certified_sample_sync"
            certification_level = "sample_sync_only"
        next_actions = list(preflight.next_actions)
        if status == "certified_authenticated_readonly_sync":
            next_actions.append("Run /data-sources/connections/{connection_id}/sync-account to pull an authenticated read-only account snapshot.")
        elif status == "certified_sample_sync":
            next_actions.append("Run /data-sources/connections/{connection_id}/sync-account with a sample snapshot before ledger usage.")
        elif warnings:
            next_actions.append("Record a sample snapshot and rerun certification before promoting this source into daily review.")

        response_preflight = {
            "status": preflight.status,
            "missing_requirements": preflight.missing_requirements,
            "blocking_reasons": preflight.blocking_reasons,
            "has_credentials_ref": preflight.has_credentials_ref,
            "requires_credentials": preflight.requires_credentials,
            "safe_to_sync_sample_only": preflight.details.get("safe_to_sync_sample_only", False),
            "authenticated_sync_available": preflight.details.get("authenticated_sync_available", False),
        }
        self._audit(
            action="data_source_connection.readonly_certification_checked",
            connection=connection,
            payload={
                "provider": connection.provider,
                "status": status,
                "certification_level": certification_level,
                "sample_sync_allowed": sample_sync_allowed,
                "blockers": blockers,
                "warnings": warnings,
                "execution_available": False,
            },
        )
        self.db.commit()
        self.db.refresh(connection)
        return ReadOnlyCertificationResult(
            connection=connection,
            provider=connection.provider,
            status=status,
            checked_at=checked_at,
            certification_level=certification_level,
            sample_sync_allowed=sample_sync_allowed,
            contract_version="readonly_adapter_v1",
            required_scopes=required_scopes,
            forbidden_scopes=forbidden_scopes,
            blockers=blockers,
            warnings=warnings,
            next_actions=dedupe(next_actions),
            preflight=response_preflight,
            adapter_contract=adapter_contract,
        )

    def certified_sync_plan(self, connection_id: str) -> dict[str, Any]:
        certification = self.read_only_certification(connection_id)
        connection = certification.connection
        config = dict(connection.config_json or {})
        blockers = list(certification.blockers)
        warnings = list(certification.warnings)
        has_sample_snapshot = isinstance(config.get("sample_snapshot"), dict) and bool(config.get("sample_snapshot"))
        authenticated_sync_provider = connection.provider in {"binance_spot_readonly", "ibkr_readonly"}
        if not certification.sample_sync_allowed:
            blockers.append("read_only_certification_not_ready")
        if not has_sample_snapshot and not authenticated_sync_provider:
            warnings.append("sample_snapshot_required_before_first_sync")

        stages = [
            {
                "key": "certification",
                "label": "Read-only certification",
                "status": "block" if certification.blockers else "warn" if certification.warnings else "ok",
                "evidence": {
                    "certification_status": certification.status,
                    "certification_level": certification.certification_level,
                    "contract_version": certification.contract_version,
                },
            },
            {
                "key": "sample_mapping",
                "label": "Sample/authenticated snapshot mapping",
                "status": "ok" if has_sample_snapshot or authenticated_sync_provider else "warn",
                "evidence": {
                    "has_sample_snapshot": has_sample_snapshot,
                    "authenticated_sync_available": authenticated_sync_provider,
                    "sample_snapshot_schema": certification.adapter_contract["sample_snapshot_schema"],
                },
            },
            {
                "key": "ledger_handoff",
                "label": "Ledger handoff",
                "status": "warn" if has_sample_snapshot else "block",
                "evidence": {
                    "target_endpoint": f"/data-sources/connections/{connection.id}/sync-account",
                    "requires_manual_payload_review": True,
                    "can_unlock_order_approval": False,
                },
            },
            {
                "key": "safety_boundary",
                "label": "Safety boundary",
                "status": "ok",
                "evidence": {
                    "execution_available": False,
                    "order_routing_available": False,
                    "withdrawals_allowed": False,
                    "signing_available": False,
                    "real_broker_call_allowed": False,
                },
            },
        ]
        blockers = dedupe(blockers)
        warnings = dedupe(warnings)
        if blockers:
            status = "blocked"
        elif authenticated_sync_provider and not warnings:
            status = "ready_for_authenticated_readonly_sync"
        elif warnings:
            status = "sample_sync_review_required"
        else:
            status = "ready_for_sample_sync"
        response = {
            "connection_id": connection.id,
            "provider": connection.provider,
            "status": status,
            "sample_sync_allowed": certification.sample_sync_allowed and not blockers,
            "sample_only": not authenticated_sync_provider,
            "authenticated_readonly_sync": authenticated_sync_provider,
            "blockers": blockers,
            "warnings": warnings,
            "next_actions": dedupe(
                list(certification.next_actions)
                + [
                    "Review the sample snapshot mapping before account sync.",
                    "Run ledger sync and reconciliation after the sample account snapshot is imported.",
                ]
            ),
            "certification": {
                "status": certification.status,
                "certification_level": certification.certification_level,
                "required_scopes": certification.required_scopes,
                "forbidden_scopes": certification.forbidden_scopes,
            },
            "stages": stages,
            "execution_available": False,
            "real_broker_call_allowed": False,
        }
        self._audit(
            action="data_source_connection.certified_sync_plan_created",
            connection=connection,
            payload=response,
        )
        self.db.commit()
        return response

    def freshness_overview(self) -> dict[str, Any]:
        checked_at = datetime.now(timezone.utc)
        entries = list(
            self.db.scalars(
                select(DataCatalogEntry)
                .order_by(DataCatalogEntry.created_at.desc(), DataCatalogEntry.id.desc())
                .limit(500)
            ).all()
        )
        snapshots = list(
            self.db.scalars(
                select(DataSnapshot)
                .order_by(DataSnapshot.as_of.desc(), DataSnapshot.created_at.desc(), DataSnapshot.id.desc())
                .limit(500)
            ).all()
        )
        latest_entry_by_dataset: dict[str, DataCatalogEntry] = {}
        for entry in entries:
            latest_entry_by_dataset.setdefault(entry.dataset_type, entry)

        latest_snapshot_by_type: dict[str, DataSnapshot] = {}
        for snapshot in snapshots:
            latest_snapshot_by_type.setdefault(snapshot.snapshot_type, snapshot)

        policies = dict(FRESHNESS_POLICIES)
        for dataset_type in latest_entry_by_dataset:
            policies.setdefault(dataset_type, (dataset_type.replace("_", " ").title(), timedelta(days=30)))
        for dataset_type in latest_snapshot_by_type:
            policies.setdefault(dataset_type, (dataset_type.replace("_", " ").title(), timedelta(days=30)))

        items = [
            self._freshness_item(
                dataset_type=dataset_type,
                label=label,
                threshold=threshold,
                checked_at=checked_at,
                entry=latest_entry_by_dataset.get(dataset_type),
                snapshot=latest_snapshot_by_type.get(dataset_type),
            )
            for dataset_type, (label, threshold) in policies.items()
        ]
        stale_count = sum(1 for item in items if item["status"] == "stale")
        missing_count = sum(1 for item in items if item["status"] == "missing")
        blocked_count = sum(1 for item in items if item["status"] == "blocked")
        if blocked_count:
            overall_status = "block"
        elif stale_count or missing_count:
            overall_status = "warn"
        else:
            overall_status = "ok"
        return {
            "checked_at": checked_at,
            "overall_status": overall_status,
            "stale_count": stale_count,
            "missing_count": missing_count,
            "blocked_count": blocked_count,
            "execution_available": False,
            "items": items,
        }

    def fallback_policy(self) -> dict[str, Any]:
        checked_at = datetime.now(timezone.utc)
        freshness = self.freshness_overview()
        connections = self.list_connections()
        connection_providers = {connection.provider for connection in connections}
        configured_external_sources = {
            str(entry.source)
            for entry in self.db.scalars(select(DataCatalogEntry).order_by(DataCatalogEntry.created_at.desc()).limit(500)).all()
        }

        items = [
            self._fallback_item(
                freshness_item=item,
                connection_providers=connection_providers,
                configured_external_sources=configured_external_sources,
            )
            for item in freshness["items"]
        ]
        fail_closed_count = sum(1 for item in items if item["status"] == "fail_closed")
        fallback_ready_count = sum(1 for item in items if item["status"] in {"primary_fresh", "fallback_available", "manual_review_available"})
        needs_review_count = sum(1 for item in items if item["status"] in {"fallback_required", "fail_closed"})
        overall_status = "fail_closed" if fail_closed_count else "review_required" if needs_review_count else "ready"
        return {
            "checked_at": checked_at,
            "overall_status": overall_status,
            "fallback_ready_count": fallback_ready_count,
            "needs_review_count": needs_review_count,
            "fail_closed_count": fail_closed_count,
            "items": items,
            "next_actions": dedupe([
                action
                for item in items
                for action in item["next_actions"]
            ]) or ["Fallback policy is ready; keep monitoring freshness and provenance."],
            "can_unlock_order_approval": False,
            "execution_available": False,
        }

    def _ensure_connections(self, payloads: list[dict[str, Any]], *, action: str) -> list[DataSourceConnection]:
        created: list[DataSourceConnection] = []
        for payload in payloads:
            existing = self.db.scalar(
                select(DataSourceConnection).where(DataSourceConnection.provider == payload["provider"]).limit(1)
            )
            if existing:
                continue
            connection = DataSourceConnection(**payload)
            self.db.add(connection)
            self.db.flush()
            self._audit(
                action=action,
                connection=connection,
                payload={"provider": connection.provider, "read_only": True},
            )
            created.append(connection)
        self.db.commit()
        for connection in created:
            self.db.refresh(connection)
        return self.list_connections()

    def create_connection(
        self,
        *,
        name: str,
        provider: str,
        source_type: str = "market_data",
        mode: str = "read_only",
        base_url: str | None = None,
        credentials_ref: str | None = None,
        config_json: dict[str, Any] | None = None,
        capabilities_json: list[str] | None = None,
    ) -> DataSourceConnection:
        if provider not in PROVIDER_SPECS:
            raise DataSourceProviderError(f"unsupported read-only data source provider: {provider}")
        if mode != "read_only":
            raise DataSourceProviderError("data source connections must remain read_only")
        if contains_secret_config_key(config_json or {}):
            raise DataSourceProviderError("config_json must not contain inline secrets; use credentials_ref instead")
        clean_credentials_ref = (credentials_ref or "").strip() or None
        if clean_credentials_ref and looks_like_inline_secret_reference(clean_credentials_ref):
            raise DataSourceProviderError("credentials_ref must point to a stored reference, not an inline secret")
        if clean_credentials_ref and len(clean_credentials_ref) > 255:
            raise DataSourceProviderError("credentials_ref is too long")

        spec = PROVIDER_SPECS[provider]
        effective_source_type = spec.source_type if source_type == "market_data" and spec.source_type != "market_data" else source_type
        connection = DataSourceConnection(
            name=name,
            provider=provider,
            source_type=effective_source_type,
            mode="read_only",
            status=self._initial_status(provider, config_json or {}, base_url),
            base_url=base_url,
            credentials_ref=clean_credentials_ref,
            config_json=config_json or {},
            capabilities_json=capabilities_json or spec.capabilities,
        )
        self.db.add(connection)
        self.db.flush()
        self._audit(
            action="data_source_connection.created",
            connection=connection,
            payload={
                "provider": provider,
                "source_type": effective_source_type,
                "mode": "read_only",
                "has_credentials_ref": bool(clean_credentials_ref),
                "capabilities": connection.capabilities_json,
            },
        )
        self.db.commit()
        self.db.refresh(connection)
        return connection

    def check_health(self, connection_id: str) -> AdapterHealth:
        connection = self._get_connection(connection_id)
        adapter = self._adapter_for(connection)
        health = adapter.health_check()
        connection.last_health_status = health.status
        connection.last_health_checked_at = health.checked_at
        connection.last_error = None if health.status == "ok" else health.message
        connection.status = "healthy" if health.status == "ok" else health.status
        self._audit(
            action="data_source_connection.health_checked",
            connection=connection,
            payload={
                "provider": connection.provider,
                "status": health.status,
                "latency_ms": health.latency_ms,
                "message": health.message,
            },
        )
        self.db.commit()
        self.db.refresh(connection)
        return health

    def import_quotes(
        self,
        connection_id: str,
        *,
        symbols: list[str],
        asset_type: str = "stock",
        market: str = "US",
        venue: str | None = None,
        currency: str = "USD",
    ) -> QuoteImportResult:
        connection = self._get_connection(connection_id)
        adapter = self._adapter_for(connection)
        health = adapter.health_check()
        connection.last_health_status = health.status
        connection.last_health_checked_at = health.checked_at
        connection.last_error = None if health.status == "ok" else health.message
        connection.status = "healthy" if health.status == "ok" else health.status
        if health.status != "ok":
            self.db.commit()
            raise DataSourceProviderError(f"data source is not importable ({health.status}): {health.message}")

        normalized_symbols = self._normalize_symbols(symbols)
        imported_quotes: list[Quote] = []
        imported_payload: list[dict[str, Any]] = []
        prices_by_symbol: dict[str, float] = {}
        skipped: list[dict[str, str]] = []

        for symbol in normalized_symbols:
            try:
                adapter_quote = adapter.get_quote(symbol)
                asset = self._get_or_create_read_only_asset(
                    adapter_quote=adapter_quote,
                    asset_type=asset_type,
                    market=market,
                    venue=venue or connection.provider,
                    currency=currency,
                )
                quote = self._create_quote(asset, adapter_quote, connection)
            except Exception as exc:
                skipped.append({"symbol": symbol, "error": str(exc)})
                continue

            self.db.add(quote)
            self.db.flush()
            prices_by_symbol[asset.symbol] = float(quote.price)
            imported_quotes.append(quote)
            imported_payload.append(
                {
                    "symbol": asset.symbol,
                    "price": float(quote.price),
                    "bid": float(quote.bid) if quote.bid is not None else None,
                    "ask": float(quote.ask) if quote.ask is not None else None,
                    "source": quote.source,
                    "as_of": quote.as_of.isoformat(),
                }
            )
            write_audit_log(
                self.db,
                action="data_source.quote_imported",
                entity_type="Quote",
                entity_id=quote.id,
                payload_json={
                    "connection_id": connection.id,
                    "provider": connection.provider,
                    "symbol": asset.symbol,
                    "price": float(quote.price),
                    "read_only": True,
                },
                actor_id="p1-data-source-service",
            )

        if not imported_quotes:
            connection.last_error = skipped[0]["error"] if skipped else "no quotes imported"
            self.db.commit()
            raise DataSourceProviderError(f"no quotes imported: {connection.last_error}")

        update_positions_from_quotes(self.db, prices_by_symbol)
        snapshot_as_of = max((quote.as_of for quote in imported_quotes), default=datetime.now(timezone.utc))
        snapshot = DataSnapshot(
            snapshot_type="market_quotes",
            as_of=snapshot_as_of,
            data_json={
                "connection_id": connection.id,
                "provider": connection.provider,
                "quotes": imported_payload,
                "skipped": skipped,
            },
            metadata_json={
                "mode": "read_only",
                "source_type": connection.source_type,
                "custom_adapter_ready": connection.provider == "custom_http_readonly",
                "symbols_requested": normalized_symbols,
            },
        )
        self.db.add(snapshot)
        self.db.flush()

        quality_score = len(imported_quotes) / max(len(normalized_symbols), 1)
        quality_report = DataQualityReport(
            data_snapshot_id=snapshot.id,
            source=connection.provider,
            metric_type="quote_import_completeness",
            score=quality_score,
            details_json={
                "requested": len(normalized_symbols),
                "imported": len(imported_quotes),
                "skipped": skipped,
                "read_only": True,
            },
        )
        self.db.add(quality_report)
        self.db.flush()

        catalog_entry = DataCatalogService(self.db).create_entry(
            dataset_type="market_quotes",
            source=connection.provider,
            source_ref=connection.name,
            row_count=len(imported_quotes),
            snapshot=snapshot,
            quality_report=quality_report,
            usable_for_trading=quality_score >= 0.999,
            lineage_json={
                "connection_id": connection.id,
                "provider": connection.provider,
                "symbols_requested": normalized_symbols,
                "symbols_imported": [quote_payload["symbol"] for quote_payload in imported_payload],
            },
            contract_json={
                "mode": "read_only",
                "source_type": connection.source_type,
                "execution_available": False,
                "quality_policy": "valid_only_for_trading_decisions",
            },
        )

        self._audit(
            action="data_snapshot.created_from_data_source",
            connection=connection,
            payload={
                "snapshot_id": snapshot.id,
                "quality_report_id": quality_report.id,
                "catalog_entry_id": catalog_entry.id,
                "symbols": [quote_payload["symbol"] for quote_payload in imported_payload],
                "skipped": skipped,
            },
        )
        self.db.commit()
        self.db.refresh(connection)
        self.db.refresh(snapshot)
        self.db.refresh(quality_report)
        return QuoteImportResult(
            connection=connection,
            quotes_imported=len(imported_quotes),
            symbols=[quote_payload["symbol"] for quote_payload in imported_payload],
            skipped=skipped,
            snapshot=snapshot,
            quality_report=quality_report,
            catalog_entry=catalog_entry,
        )

    def import_candles(
        self,
        connection_id: str,
        *,
        symbols: list[str],
        timeframe: str = "1d",
        limit: int = 30,
        asset_type: str = "stock",
        market: str = "US",
        venue: str | None = None,
        currency: str = "USD",
    ) -> CandleImportResult:
        connection = self._get_connection(connection_id)
        adapter = self._adapter_for(connection)
        health = adapter.health_check()
        connection.last_health_status = health.status
        connection.last_health_checked_at = health.checked_at
        connection.last_error = None if health.status == "ok" else health.message
        connection.status = "healthy" if health.status == "ok" else health.status
        if health.status != "ok":
            self.db.commit()
            raise DataSourceProviderError(f"data source is not importable ({health.status}): {health.message}")

        normalized_symbols = self._normalize_symbols(symbols)
        if timeframe not in {"1d", "1h"}:
            raise DataSourceProviderError(f"unsupported candle timeframe: {timeframe}")
        if limit <= 0 or limit > 365:
            raise DataSourceProviderError("candle limit must be between 1 and 365")

        imported_count = 0
        imported_payload: list[dict[str, Any]] = []
        skipped: list[dict[str, str]] = []
        latest_as_of = datetime.now(timezone.utc)

        for symbol in normalized_symbols:
            try:
                adapter_candles = adapter.get_candles(symbol, timeframe, limit)
                if not adapter_candles:
                    raise ValueError("no candles returned")
                asset = self._get_or_create_read_only_asset_from_symbol(
                    symbol=symbol,
                    source=connection.provider,
                    asset_type=asset_type,
                    market=market,
                    venue=venue or connection.provider,
                    currency=currency,
                )
            except Exception as exc:
                skipped.append({"symbol": symbol, "error": str(exc)})
                continue

            rows_imported = 0
            symbol_latest_as_of = latest_as_of
            for adapter_candle in adapter_candles:
                candle, created = self._upsert_candle(asset, adapter_candle, connection)
                self.db.flush()
                imported_count += 1
                rows_imported += 1
                candle_timestamp = self._normalize_dt(candle.timestamp)
                latest_as_of = max(latest_as_of, candle_timestamp)
                symbol_latest_as_of = max(symbol_latest_as_of, candle_timestamp)
                write_audit_log(
                    self.db,
                    action="data_source.candle_imported",
                    entity_type="Candle",
                    entity_id=candle.id,
                    payload_json={
                        "connection_id": connection.id,
                        "provider": connection.provider,
                        "symbol": asset.symbol,
                        "timeframe": candle.timeframe,
                        "timestamp": candle.timestamp.isoformat(),
                        "read_only": True,
                        "upserted": not created,
                    },
                    actor_id="p1-data-source-service",
                )

            imported_payload.append(
                {
                    "symbol": asset.symbol,
                    "timeframe": timeframe,
                    "candles_imported": rows_imported,
                    "latest_timestamp": symbol_latest_as_of.isoformat(),
                }
            )

        if not imported_payload:
            connection.last_error = skipped[0]["error"] if skipped else "no candles imported"
            self.db.commit()
            raise DataSourceProviderError(f"no candles imported: {connection.last_error}")

        snapshot = DataSnapshot(
            snapshot_type="market_candles",
            as_of=latest_as_of,
            data_json={
                "connection_id": connection.id,
                "provider": connection.provider,
                "timeframe": timeframe,
                "symbols": imported_payload,
                "skipped": skipped,
            },
            metadata_json={
                "mode": "read_only",
                "source_type": connection.source_type,
                "timeframe": timeframe,
                "limit": limit,
                "symbols_requested": normalized_symbols,
            },
        )
        self.db.add(snapshot)
        self.db.flush()

        quality_score = len(imported_payload) / max(len(normalized_symbols), 1)
        quality_report = DataQualityReport(
            data_snapshot_id=snapshot.id,
            source=connection.provider,
            metric_type="candle_import_completeness",
            score=quality_score,
            details_json={
                "requested": len(normalized_symbols),
                "imported": len(imported_payload),
                "candles_imported": imported_count,
                "timeframe": timeframe,
                "skipped": skipped,
                "read_only": True,
            },
        )
        self.db.add(quality_report)
        self.db.flush()

        catalog_entry = DataCatalogService(self.db).create_entry(
            dataset_type="market_candles",
            source=connection.provider,
            source_ref=connection.name,
            row_count=imported_count,
            snapshot=snapshot,
            quality_report=quality_report,
            usable_for_trading=quality_score >= 0.999,
            lineage_json={
                "connection_id": connection.id,
                "provider": connection.provider,
                "timeframe": timeframe,
                "symbols_requested": normalized_symbols,
                "symbols_imported": [row["symbol"] for row in imported_payload],
            },
            contract_json={
                "mode": "read_only",
                "source_type": connection.source_type,
                "execution_available": False,
                "quality_policy": "valid_only_for_research_signals_and_trading_decisions",
            },
        )

        self._audit(
            action="data_snapshot.candles_created_from_data_source",
            connection=connection,
            payload={
                "snapshot_id": snapshot.id,
                "quality_report_id": quality_report.id,
                "catalog_entry_id": catalog_entry.id,
                "timeframe": timeframe,
                "symbols": [row["symbol"] for row in imported_payload],
                "candles_imported": imported_count,
                "skipped": skipped,
            },
        )
        self.db.commit()
        self.db.refresh(connection)
        self.db.refresh(snapshot)
        self.db.refresh(quality_report)
        return CandleImportResult(
            connection=connection,
            candles_imported=imported_count,
            symbols=[row["symbol"] for row in imported_payload],
            timeframe=timeframe,
            skipped=skipped,
            snapshot=snapshot,
            quality_report=quality_report,
            catalog_entry=catalog_entry,
        )

    def sync_account_snapshot(
        self,
        connection_id: str,
        *,
        sample_payload: dict[str, Any] | None = None,
        persist_positions: bool = True,
        user_id: str = "default-user",
        trigger: str = "manual",
    ) -> AccountSyncResult:
        connection = self._get_connection(connection_id)
        if connection.provider not in ACCOUNT_PROVIDER_IDS:
            raise DataSourceProviderError("account sync is only available for read-only account providers")
        if contains_secret_config_key(sample_payload or {}):
            raise DataSourceProviderError("sample_payload must not contain inline secrets")

        adapter = self._readonly_account_adapter_for(connection, sample_payload=sample_payload)
        health = adapter.health_check()
        connection.last_health_status = health.status
        connection.last_health_checked_at = health.checked_at
        connection.last_error = None if health.status == "ok" else health.message
        connection.status = "healthy" if health.status == "ok" else health.status
        if health.status != "ok":
            self.db.commit()
            raise DataSourceProviderError(f"read-only account source is not syncable ({health.status}): {health.message}")

        try:
            account_snapshot = adapter.get_account_snapshot()
        except Exception as exc:
            error_code = type(exc).__name__
            connection.status = "error"
            connection.last_error = f"read_only_account_sync_failed:{error_code}"
            self._audit(
                action="data_snapshot.account_sync_failed",
                connection=connection,
                payload={
                    "error_code": error_code,
                    "error_message": "Read-only provider unavailable or rejected the sync.",
                    "read_only": True,
                    "execution_available": False,
                },
            )
            if trigger != "scheduler":
                self.db.add(OperationalEvent(
                    user_id=user_id,
                    event_type="data_source.account_sync_failed",
                    severity="warning",
                    source="data-source-service",
                    message="Read-only account sync failed closed.",
                    status="closed",
                    payload_json={
                        "connection_id": connection.id,
                        "error_code": error_code,
                        "retry_scheduled": False,
                        "execution_available": False,
                    },
                ))
            self.db.commit()
            raise DataSourceProviderError(
                f"read-only account sync failed closed ({error_code}); provider details were redacted"
            ) from exc
        account: Account | None = None
        portfolio_snapshot: PortfolioSnapshot | None = None
        positions_synced = 0
        balances_synced = len(account_snapshot.balances)

        if persist_positions:
            account, portfolio_snapshot, positions_synced = self._persist_readonly_account_snapshot(connection, account_snapshot)

        snapshot = DataSnapshot(
            snapshot_type="read_only_account",
            as_of=account_snapshot.as_of,
            data_json={
                "connection_id": connection.id,
                "provider": connection.provider,
                "account": account_snapshot.account,
                "balances": account_snapshot.balances,
                "positions": account_snapshot.positions,
                "orders": account_snapshot.orders,
                "warnings": account_snapshot.warnings,
            },
            metadata_json={
                "mode": "read_only",
                "data_origin": "sample_payload" if sample_payload is not None else "authenticated_provider",
                "real_external_evidence": sample_payload is None,
                "source_type": connection.source_type,
                "execution_available": False,
                "order_routing_available": False,
                "withdrawals_allowed": False,
                "signing_available": False,
                "persist_positions": persist_positions,
                "account_id": account.id if account else None,
                "portfolio_snapshot_id": portfolio_snapshot.id if portfolio_snapshot else None,
            },
        )
        self.db.add(snapshot)
        self.db.flush()

        quality_score, quality_details = self._account_quality(account_snapshot, persist_positions=persist_positions)
        quality_report = DataQualityReport(
            data_snapshot_id=snapshot.id,
            source=connection.provider,
            metric_type="account_sync_completeness",
            score=quality_score,
            details_json=quality_details,
        )
        self.db.add(quality_report)
        self.db.flush()

        catalog_entry = DataCatalogService(self.db).create_entry(
            dataset_type="read_only_account",
            source=connection.provider,
            source_ref=connection.name,
            row_count=positions_synced + balances_synced + len(account_snapshot.orders),
            snapshot=snapshot,
            quality_report=quality_report,
            usable_for_trading=False,
            lineage_json={
                "connection_id": connection.id,
                "provider": connection.provider,
                "data_origin": "sample_payload" if sample_payload is not None else "authenticated_provider",
                "account_id": account.id if account else None,
                "portfolio_snapshot_id": portfolio_snapshot.id if portfolio_snapshot else None,
            },
            contract_json={
                "mode": "read_only",
                "source_type": connection.source_type,
                "execution_available": False,
                "order_routing_available": False,
                "withdrawals_allowed": False,
                "signing_available": False,
                "quality_policy": "review_only_until_reconciled",
                "real_external_evidence": sample_payload is None,
            },
        )

        self._audit(
            action="data_snapshot.account_created_from_data_source",
            connection=connection,
            payload={
                "snapshot_id": snapshot.id,
                "quality_report_id": quality_report.id,
                "catalog_entry_id": catalog_entry.id,
                "account_id": account.id if account else None,
                "positions_synced": positions_synced,
                "balances_synced": balances_synced,
                "orders_seen": len(account_snapshot.orders),
                "read_only": True,
                "execution_available": False,
            },
        )
        self.db.commit()
        self.db.refresh(connection)
        self.db.refresh(snapshot)
        self.db.refresh(quality_report)
        if account:
            self.db.refresh(account)
        if portfolio_snapshot:
            self.db.refresh(portfolio_snapshot)

        # Every successful account sync must produce the same evidence chain,
        # regardless of whether it was triggered from the API or a phase check.
        # Import locally to avoid a module cycle: ledger imports catalog models.
        from app.services.ledger import InvestmentLedgerService

        ledger_service = InvestmentLedgerService(self.db)
        ledger_result = ledger_service.sync(user_id=user_id)
        reconciliation_result = ledger_service.reconcile(user_id=user_id)
        reconciliation_run = reconciliation_result["run"]
        ledger_sync = {
            "entries_created": ledger_result["entries_created"],
            "entries_existing": ledger_result["entries_existing"],
            "data_trust_status": ledger_result["data_trust_status"],
        }
        reconciliation = {
            "run_id": reconciliation_run.id,
            "status": reconciliation_run.status,
            "breaks_count": reconciliation_run.breaks_count,
        }

        self._audit(
            action="data_snapshot.account_evidence_chain_completed",
            connection=connection,
            payload={
                "snapshot_id": snapshot.id,
                "quality_report_id": quality_report.id,
                "catalog_entry_id": catalog_entry.id,
                "ledger_entries_created": ledger_sync["entries_created"],
                "reconciliation_run_id": reconciliation["run_id"],
                "reconciliation_status": reconciliation["status"],
                "read_only": True,
                "execution_available": False,
            },
        )
        self.db.commit()

        return AccountSyncResult(
            connection=connection,
            account=account,
            positions_synced=positions_synced,
            balances_synced=balances_synced,
            orders_seen=len(account_snapshot.orders),
            snapshot=snapshot,
            quality_report=quality_report,
            portfolio_snapshot=portfolio_snapshot,
            catalog_entry=catalog_entry,
            ledger_sync=ledger_sync,
            reconciliation=reconciliation,
        )

    def configure_account_auto_refresh(
        self,
        connection_id: str,
        *,
        user_id: str = "default-user",
        enabled: bool = True,
        interval_minutes: int = 15,
    ) -> dict[str, Any]:
        connection = self._get_connection(connection_id)
        if connection.provider not in ACCOUNT_PROVIDER_IDS:
            raise DataSourceProviderError("automatic account refresh is only available for read-only account providers")
        if interval_minutes < 5 or interval_minutes > 1440:
            raise DataSourceProviderError("interval_minutes must be between 5 and 1440")
        job = self.db.scalar(
            select(ScheduledJob)
            .where(
                ScheduledJob.job_type == "account_readonly_sync",
                ScheduledJob.target_json["connection_id"].as_string() == connection.id,
            )
            .order_by(ScheduledJob.created_at.asc(), ScheduledJob.id.asc())
            .limit(1)
        )
        schedule = {
            "mode": "interval",
            "timezone": "Asia/Shanghai",
            "interval_minutes": interval_minutes,
            "minimum_interval_seconds": 30,
            "retry_policy": {"base_seconds": 30, "max_seconds": 1800},
        }
        target = {"connection_id": connection.id, "user_id": user_id, "read_only": True}
        if job is None:
            job = ScheduledJob(
                name=f"Read-only account refresh: {connection.name}",
                job_type="account_readonly_sync",
                status="active" if enabled else "paused",
                schedule_json=schedule,
                target_json=target,
                last_run_summary={},
            )
            self.db.add(job)
        else:
            job.status = "active" if enabled else "paused"
            job.schedule_json = schedule
            job.target_json = target
        self.db.flush()
        self._audit(
            action="data_source.account_auto_refresh_configured",
            connection=connection,
            payload={
                "job_id": job.id,
                "status": job.status,
                "interval_minutes": interval_minutes,
                "retry_policy": schedule["retry_policy"],
                "execution_available": False,
            },
        )
        self.db.commit()
        self.db.refresh(job)
        return {
            "job_id": job.id,
            "connection_id": connection.id,
            "status": job.status,
            "schedule": job.schedule_json,
            "last_run_at": job.last_run_at,
            "last_run_status": job.last_run_status,
            "last_run_summary": job.last_run_summary,
            "execution_available": False,
        }

    def account_sync_history(
        self,
        connection_id: str,
        *,
        user_id: str = "default-user",
        limit: int = 50,
    ) -> dict[str, Any]:
        connection = self._get_connection(connection_id)
        bounded_limit = max(1, min(limit, 200))
        job = self.db.scalar(
            select(ScheduledJob)
            .where(
                ScheduledJob.job_type == "account_readonly_sync",
                ScheduledJob.target_json["connection_id"].as_string() == connection.id,
            )
            .order_by(ScheduledJob.created_at.asc(), ScheduledJob.id.asc())
            .limit(1)
        )
        events = list(self.db.scalars(
            select(OperationalEvent)
            .where(
                OperationalEvent.user_id == user_id,
                OperationalEvent.event_type == "data_source.account_sync_failed",
            )
            .order_by(OperationalEvent.created_at.desc(), OperationalEvent.id.desc())
            .limit(500)
        ).all())
        matching = [event for event in events if (event.payload_json or {}).get("connection_id") == connection.id][:bounded_limit]
        audits = list(self.db.scalars(
            select(AuditLog)
            .where(
                AuditLog.entity_type == "DataSourceConnection",
                AuditLog.entity_id == connection.id,
                AuditLog.action == "data_snapshot.account_evidence_chain_completed",
            )
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .limit(bounded_limit)
        ).all())
        history = [
            {
                "id": event.id,
                "status": "retry_scheduled" if (event.payload_json or {}).get("next_retry_at") else "failed",
                "severity": event.severity,
                "message": event.message,
                "created_at": event.created_at,
                "details": event.payload_json,
            }
            for event in matching
        ] + [
            {
                "id": audit.id,
                "status": "succeeded",
                "severity": "info",
                "message": "Read-only account sync completed.",
                "created_at": audit.created_at,
                "details": audit.payload_json,
            }
            for audit in audits
        ]
        history.sort(key=lambda item: (self._normalize_dt(item["created_at"]), item["id"]), reverse=True)
        return {
            "connection_id": connection.id,
            "provider": connection.provider,
            "job": None if job is None else {
                "job_id": job.id,
                "status": job.status,
                "schedule": job.schedule_json,
                "last_run_at": job.last_run_at,
                "last_run_status": job.last_run_status,
                "last_run_summary": job.last_run_summary,
            },
            "history": history[:bounded_limit],
            "execution_available": False,
        }

    def list_snapshots(self, snapshot_type: str | None = None, limit: int = 50) -> list[DataSnapshot]:
        query = select(DataSnapshot).order_by(DataSnapshot.created_at.desc(), DataSnapshot.id.desc()).limit(limit)
        if snapshot_type:
            query = (
                select(DataSnapshot)
                .where(DataSnapshot.snapshot_type == snapshot_type)
                .order_by(DataSnapshot.created_at.desc(), DataSnapshot.id.desc())
                .limit(limit)
            )
        query = query.where(DataSnapshot.snapshot_type.notin_(["research_chat_news_context","research_chat_market_context"]))
        return list(self.db.scalars(query).all())

    def list_quality_reports(self, source: str | None = None, limit: int = 10) -> list[DataQualityReport]:
        query = select(DataQualityReport).order_by(DataQualityReport.created_at.desc(), DataQualityReport.id.desc()).limit(limit)
        if source:
            query = (
                select(DataQualityReport)
                .where(DataQualityReport.source == source)
                .order_by(DataQualityReport.created_at.desc(), DataQualityReport.id.desc())
                .limit(limit)
            )
        return list(self.db.scalars(query).all())

    def explain_quality_report(self, report_id: str) -> dict[str, Any]:
        report = self.db.get(DataQualityReport, report_id)
        if not report:
            raise DataSourceNotFoundError(f"data quality report not found: {report_id}")

        score = float(report.score)
        details = report.details_json or {}
        skipped = details.get("skipped", [])
        requested = int(details.get("requested", 0) or 0)
        imported = int(details.get("imported", 0) or 0)

        if score >= 0.8:
            level = "good"
        elif score >= 0.5:
            level = "warning"
        else:
            level = "bad"

        if report.metric_type == "account_sync_completeness":
            explanations = [
                f"{details.get('positions', 0)} positions, {details.get('balances', 0)} balances, and {details.get('orders', 0)} orders were observed.",
                "The account source is read-only and cannot execute trades, route orders, withdraw assets, or sign transactions.",
            ]
        else:
            explanations = [
                f"{imported} of {requested} requested symbols were imported.",
                "The data source is read-only and cannot execute trades.",
            ]
        if skipped:
            explanations.append(f"{len(skipped)} symbols were skipped: {skipped}.")
        if report.metric_type in {"quote_import_completeness", "candle_import_completeness"} and score < 1:
            explanations.append("Some market data is missing, so AI research and gates should treat the snapshot as incomplete.")
        if report.metric_type == "account_sync_completeness" and score < 0.8:
            explanations.append("The account snapshot is incomplete, so sizing, exposure, and approval checks should fail closed.")

        recommended_actions = []
        if report.metric_type == "account_sync_completeness" and score < 1:
            recommended_actions.extend(
                [
                    "Refresh the read-only account snapshot.",
                    "Check that balances, positions, and account identifiers are present.",
                    "Use the snapshot for review only until quality is good.",
                ]
            )
        elif score < 1:
            recommended_actions.extend(
                [
                    "Refresh the same connection again.",
                    "Check skipped symbols and provider symbol mappings.",
                    "Use a fallback read-only source before approving related drafts.",
                ]
            )
        else:
            recommended_actions.append("Use this snapshot for research and risk checks if timestamps are still fresh.")

        return {
            "report": report,
            "level": level,
            "summary": f"{report.source} {report.metric_type} scored {score:.0%}.",
            "explanations": explanations,
            "recommended_actions": recommended_actions,
            "blocks_trading_decisions": score < 0.8,
        }

    def _get_connection(self, connection_id: str) -> DataSourceConnection:
        connection = self.db.get(DataSourceConnection, connection_id)
        if not connection:
            raise DataSourceNotFoundError(f"data source connection not found: {connection_id}")
        if connection.mode != "read_only":
            raise DataSourceProviderError("data source connection must be read_only")
        return connection

    def _adapter_for(self, connection: DataSourceConnection) -> ReadOnlyMarketDataAdapter:
        if connection.provider == "mock_market_data":
            return MockReadOnlyMarketDataAdapter()
        if connection.provider == "stooq_public_eod":
            return StooqPublicMarketDataAdapter(connection.config_json)
        if connection.provider == "yfinance_public":
            return YahooFinancePublicMarketDataAdapter(connection.config_json)
        if connection.provider == "custom_http_readonly":
            return CustomHttpReadOnlyMarketDataAdapter(connection.config_json, connection.base_url)
        if connection.provider in ACCOUNT_PROVIDER_IDS:
            return self._readonly_account_adapter_for(connection)
        raise DataSourceProviderError(f"unsupported read-only data source provider: {connection.provider}")

    def _readonly_account_adapter_for(
        self,
        connection: DataSourceConnection,
        *,
        sample_payload: dict[str, Any] | None = None,
    ) -> ReadOnlyMarketDataAdapter:
        spec = PROVIDER_SPECS[connection.provider]
        if sample_payload is not None:
            return PlaceholderReadOnlyAccountAdapter(
                connection.provider,
                f"{spec.display_name} explicit sample mapping",
                config={},
                credentials_ref=connection.credentials_ref,
                sample_payload=sample_payload,
            )
        if connection.provider == "binance_spot_readonly":
            return BinanceSpotReadOnlyAccountAdapter(
                config=connection.config_json,
                credentials_ref=connection.credentials_ref,
            )
        if connection.provider == "ibkr_readonly":
            return IbkrClientPortalReadOnlyAccountAdapter(
                config=connection.config_json,
                credentials_ref=connection.credentials_ref,
            )
        return PlaceholderReadOnlyAccountAdapter(
            connection.provider,
            spec.display_name,
            config=connection.config_json,
            credentials_ref=connection.credentials_ref,
            sample_payload=sample_payload,
        )

    def _initial_status(self, provider: str, config: dict[str, Any], base_url: str | None) -> str:
        if provider in ACCOUNT_PROVIDER_IDS:
            return "configured" if config.get("sample_snapshot") else "unconfigured"
        if provider != "custom_http_readonly":
            return "configured"
        if config.get("quote_url_template") or base_url:
            return "configured"
        return "unconfigured"

    def _readonly_preflight_required_config_keys(self, provider: str) -> list[str]:
        if provider == "ibkr_readonly":
            return ["gateway_host", "gateway_port"]
        if provider == "futu_readonly":
            return ["host", "port"]
        if provider == "cex_readonly":
            return ["exchange"]
        if provider == "binance_spot_readonly":
            return []
        if provider == "wallet_readonly":
            return ["public_address"]
        return []

    def _readonly_preflight_next_actions(
        self,
        *,
        provider: str,
        status: str,
        missing_requirements: list[str],
        has_credentials_ref: bool,
        has_sample_snapshot: bool,
    ) -> list[str]:
        next_actions: list[str] = []
        if "credentials_ref" in missing_requirements:
            next_actions.append("Attach a read-only credentials_ref from env:, secretref:, vault:, keychain:, or local-secret: storage.")
        config_missing = [item for item in missing_requirements if item != "credentials_ref"]
        if config_missing:
            next_actions.append(f"Configure non-sensitive adapter metadata: {', '.join(config_missing)}.")
        if status == "blocked":
            next_actions.append("Resolve every missing requirement and blocking reason before running account sync.")
        elif provider in {"binance_spot_readonly", "ibkr_readonly"}:
            next_actions.append(f"Run sync-account to pull the authenticated read-only {provider} account snapshot.")
        elif has_sample_snapshot:
            next_actions.append("Run sync-account using the stored sample_snapshot and inspect the quality report.")
        else:
            next_actions.append("Run sync-account with a sample_payload to validate mapping before enabling scheduled read-only refresh.")
        if provider == "wallet_readonly":
            next_actions.append("Use only a public wallet address; never provide a seed phrase, private key, signer, or wallet password.")
        elif provider in {"cex_readonly", "binance_spot_readonly"}:
            next_actions.append("Confirm the exchange API key is read-only and withdrawal-disabled outside this app.")
        elif has_credentials_ref:
            next_actions.append("Verify the referenced credentials are read-only in the broker or gateway console.")
        return next_actions

    def _normalize_symbols(self, symbols: list[str]) -> list[str]:
        normalized: list[str] = []
        for symbol in symbols:
            cleaned = symbol.strip().upper()
            if cleaned and cleaned not in normalized:
                normalized.append(cleaned)
        if not normalized:
            raise DataSourceProviderError("at least one symbol is required")
        return normalized

    def _get_or_create_read_only_asset(
        self,
        *,
        adapter_quote: AdapterQuote,
        asset_type: str,
        market: str,
        venue: str,
        currency: str,
    ) -> Asset:
        symbol = adapter_quote.symbol.upper()
        asset = self.db.scalar(select(Asset).where(Asset.symbol == symbol).limit(1))
        if asset:
            return asset

        mock_asset = MOCK_ASSETS.get(symbol)
        asset = Asset(
            symbol=symbol,
            name=mock_asset.name if mock_asset else symbol,
            asset_type=mock_asset.asset_type if mock_asset else asset_type,
            market=mock_asset.market if mock_asset else market,
            venue=mock_asset.venue if mock_asset else venue,
            currency=mock_asset.currency if mock_asset else currency,
            chain_id=mock_asset.chain_id if mock_asset else None,
            contract_address=mock_asset.contract_address if mock_asset else None,
            tradable=False,
            manual_enabled=False,
            auto_enabled=False,
            risk_level=mock_asset.risk_level if mock_asset else "medium",
        )
        self.db.add(asset)
        self.db.flush()
        write_audit_log(
            self.db,
            action="data_source.asset_imported_read_only",
            entity_type="Asset",
            entity_id=asset.id,
            payload_json={"symbol": asset.symbol, "provider": adapter_quote.source, "read_only": True},
            actor_id="p1-data-source-service",
        )
        return asset

    def _get_or_create_read_only_asset_from_symbol(
        self,
        *,
        symbol: str,
        source: str,
        asset_type: str,
        market: str,
        venue: str,
        currency: str,
    ) -> Asset:
        adapter_quote = AdapterQuote(symbol=symbol.upper(), price=0, source=source, as_of=datetime.now(timezone.utc))
        return self._get_or_create_read_only_asset(
            adapter_quote=adapter_quote,
            asset_type=asset_type,
            market=market,
            venue=venue,
            currency=currency,
        )

    def _persist_readonly_account_snapshot(
        self,
        connection: DataSourceConnection,
        account_snapshot: ReadOnlyAccountSnapshot,
    ) -> tuple[Account, PortfolioSnapshot, int]:
        account = self._get_or_create_read_only_account(connection, account_snapshot.account)
        synced_positions: list[Position] = []

        for row in account_snapshot.positions:
            symbol = str(row.get("symbol") or row.get("asset") or "").strip().upper()
            if not symbol:
                continue
            asset = self._get_or_create_read_only_asset_from_position(
                symbol=symbol,
                source=connection.provider,
                row=row,
            )
            quantity = self._float(row.get("quantity") or row.get("qty") or row.get("amount"))
            average_cost = self._float(row.get("average_cost") or row.get("avg_cost") or row.get("cost_basis"))
            market_price = self._float(row.get("market_price") or row.get("price") or row.get("last_price"))
            market_value = self._float(row.get("market_value"))
            if market_value == 0 and market_price != 0:
                market_value = quantity * market_price
            unrealized_pnl = self._float(row.get("unrealized_pnl") or row.get("pnl"))
            if unrealized_pnl == 0 and market_price != 0 and average_cost != 0:
                unrealized_pnl = (market_price - average_cost) * quantity

            position = self.db.scalar(select(Position).where(Position.account_id == account.id, Position.asset_id == asset.id).limit(1))
            if not position:
                position = Position(account_id=account.id, asset_id=asset.id, realized_pnl=0)
                self.db.add(position)
            position.quantity = quantity
            position.average_cost = average_cost
            position.market_price = market_price
            position.market_value = market_value
            position.unrealized_pnl = unrealized_pnl
            synced_positions.append(position)
            self.db.flush()

        total_position_value = sum(float(position.market_value) for position in synced_positions)
        for position in synced_positions:
            position.weight = float(position.market_value) / total_position_value if total_position_value else 0

        cash_value = self._cash_value(account_snapshot.balances, account.base_currency)
        portfolio_snapshot = PortfolioSnapshot(
            account_id=account.id,
            total_value=cash_value + total_position_value,
            cash_value=cash_value,
            positions_value=total_position_value,
            currency=account.base_currency,
            snapshot_json={
                "source": connection.provider,
                "connection_id": connection.id,
                "mode": "read_only",
                "execution_available": False,
                "balances": account_snapshot.balances,
                "positions": account_snapshot.positions,
                "orders": account_snapshot.orders,
                "warnings": account_snapshot.warnings,
            },
        )
        self.db.add(portfolio_snapshot)
        self.db.flush()

        write_audit_log(
            self.db,
            action="data_source.account_synced_read_only",
            entity_type="Account",
            entity_id=account.id,
            payload_json={
                "connection_id": connection.id,
                "provider": connection.provider,
                "positions_synced": len(synced_positions),
                "balances_synced": len(account_snapshot.balances),
                "portfolio_snapshot_id": portfolio_snapshot.id,
                "live_trading_enabled": False,
            },
            actor_id="p2-readonly-account-sync",
        )
        return account, portfolio_snapshot, len(synced_positions)

    def _get_or_create_read_only_account(self, connection: DataSourceConnection, account_payload: dict[str, Any]) -> Account:
        upstream_id = str(account_payload.get("account_id") or account_payload.get("id") or connection.id)
        label = str(account_payload.get("label") or account_payload.get("name") or connection.name)
        account_name = f"{connection.provider}:{label}:{upstream_id}"
        account = self.db.scalar(
            select(Account).where(Account.name == account_name, Account.broker == connection.provider).limit(1)
        )
        if not account:
            account = Account(
                name=account_name,
                account_type=str(account_payload.get("account_type") or connection.source_type),
                broker=connection.provider,
                base_currency=str(account_payload.get("base_currency") or "USD").upper(),
                mode="read_only",
                live_trading_enabled=False,
            )
            self.db.add(account)
            self.db.flush()
        else:
            account.account_type = str(account_payload.get("account_type") or connection.source_type)
            account.base_currency = str(account_payload.get("base_currency") or account.base_currency or "USD").upper()
            account.mode = "read_only"
            account.live_trading_enabled = False
        return account

    def _get_or_create_read_only_asset_from_position(self, *, symbol: str, source: str, row: dict[str, Any]) -> Asset:
        asset_type = str(row.get("asset_type") or row.get("type") or ("crypto" if source in {"cex_readonly", "wallet_readonly"} else "stock"))
        market = str(row.get("market") or ("CRYPTO" if asset_type == "crypto" else "US"))
        venue = str(row.get("venue") or row.get("exchange") or source)
        currency = str(row.get("currency") or row.get("quote_currency") or "USD").upper()
        asset = self._get_or_create_read_only_asset_from_symbol(
            symbol=symbol,
            source=source,
            asset_type=asset_type,
            market=market,
            venue=venue,
            currency=currency,
        )
        if row.get("name"):
            asset.name = str(row["name"])
        if row.get("chain_id"):
            asset.chain_id = str(row["chain_id"])
        if row.get("contract_address"):
            asset.contract_address = str(row["contract_address"])
        asset.tradable = False
        asset.manual_enabled = False
        asset.auto_enabled = False
        return asset

    def _account_quality(
        self,
        account_snapshot: ReadOnlyAccountSnapshot,
        *,
        persist_positions: bool,
    ) -> tuple[float, dict[str, Any]]:
        penalties = 0.0
        warnings = list(account_snapshot.warnings)
        if not account_snapshot.account.get("account_id") and not account_snapshot.account.get("id"):
            penalties += 0.15
            warnings.append("missing external account id")
        if not account_snapshot.balances:
            penalties += 0.25
        if not account_snapshot.positions:
            penalties += 0.25
        if persist_positions is False:
            penalties += 0.1
            warnings.append("positions were not persisted")
        if any(str(item).startswith("market_value_unpriced:") for item in warnings):
            penalties += 0.25
        if "balances_missing_or_invalid" in warnings:
            penalties += 0.25

        score = max(0.0, min(1.0, 1.0 - penalties))
        return score, {
            "account_present": bool(account_snapshot.account),
            "balances": len(account_snapshot.balances),
            "positions": len(account_snapshot.positions),
            "orders": len(account_snapshot.orders),
            "warnings": warnings,
            "read_only": True,
            "execution_available": False,
            "withdrawals_allowed": False,
            "persist_positions": persist_positions,
        }

    def _cash_value(self, balances: list[dict[str, Any]], base_currency: str) -> float:
        total = 0.0
        for row in balances:
            currency = str(row.get("currency") or row.get("asset") or "").upper()
            amount = self._float(row.get("cash_value") or row.get("value") or row.get("total") or row.get("quantity") or row.get("amount"))
            if currency == base_currency.upper() or row.get("cash_value") is not None or row.get("value") is not None:
                total += amount
        return total

    def _float(self, value: Any) -> float:
        if value in (None, ""):
            return 0.0
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _create_quote(self, asset: Asset, adapter_quote: AdapterQuote, connection: DataSourceConnection) -> Quote:
        return Quote(
            asset_id=asset.id,
            price=adapter_quote.price,
            bid=adapter_quote.bid,
            ask=adapter_quote.ask,
            source=f"{connection.provider}:{adapter_quote.source}",
            as_of=adapter_quote.as_of or datetime.now(timezone.utc),
        )

    def _upsert_candle(self, asset: Asset, adapter_candle, connection: DataSourceConnection) -> tuple[Candle, bool]:
        existing = self.db.scalar(
            select(Candle).where(
                Candle.asset_id == asset.id,
                Candle.timeframe == adapter_candle.timeframe,
                Candle.timestamp == adapter_candle.timestamp,
            )
        )
        if existing:
            existing.open = adapter_candle.open
            existing.high = adapter_candle.high
            existing.low = adapter_candle.low
            existing.close = adapter_candle.close
            existing.volume = adapter_candle.volume
            existing.source = f"{connection.provider}:{adapter_candle.source}"
            return existing, False

        candle = Candle(
            asset_id=asset.id,
            timeframe=adapter_candle.timeframe,
            timestamp=adapter_candle.timestamp,
            open=adapter_candle.open,
            high=adapter_candle.high,
            low=adapter_candle.low,
            close=adapter_candle.close,
            volume=adapter_candle.volume,
            source=f"{connection.provider}:{adapter_candle.source}",
        )
        self.db.add(candle)
        return candle, True

    def _audit(self, *, action: str, connection: DataSourceConnection, payload: dict[str, Any]) -> None:
        write_audit_log(
            self.db,
            action=action,
            entity_type="DataSourceConnection",
            entity_id=connection.id,
            payload_json=payload,
            actor_id="p1-data-source-service",
        )

    def _normalize_dt(self, value: datetime) -> datetime:
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    def _freshness_item(
        self,
        *,
        dataset_type: str,
        label: str,
        threshold: timedelta,
        checked_at: datetime,
        entry: DataCatalogEntry | None,
        snapshot: DataSnapshot | None,
    ) -> dict[str, Any]:
        effective_snapshot = snapshot
        if effective_snapshot is None and entry and entry.data_snapshot_id:
            effective_snapshot = self.db.get(DataSnapshot, entry.data_snapshot_id)

        report = None
        if entry and entry.quality_report_id:
            report = self.db.get(DataQualityReport, entry.quality_report_id)
        if report is None and effective_snapshot is not None:
            report = self.db.scalar(
                select(DataQualityReport)
                .where(DataQualityReport.data_snapshot_id == effective_snapshot.id)
                .order_by(DataQualityReport.created_at.desc(), DataQualityReport.id.desc())
                .limit(1)
            )

        latest_as_of = self._normalize_dt(effective_snapshot.as_of) if effective_snapshot else None
        age_seconds = int((checked_at - latest_as_of).total_seconds()) if latest_as_of else None
        threshold_seconds = int(threshold.total_seconds())
        quality_score = float(report.score) if report else None
        quality_status = entry.quality_status if entry else None

        if effective_snapshot is None and entry is None:
            status = "missing"
        elif quality_status == "FAILED" or (quality_score is not None and quality_score < 0.8):
            status = "blocked"
        elif age_seconds is not None and age_seconds > threshold_seconds:
            status = "stale"
        else:
            status = "fresh"

        return {
            "dataset_type": dataset_type,
            "label": label,
            "status": status,
            "source": entry.source if entry else (effective_snapshot.data_json.get("source") if effective_snapshot else None),
            "source_ref": entry.source_ref if entry else None,
            "snapshot_id": effective_snapshot.id if effective_snapshot else None,
            "quality_report_id": report.id if report else None,
            "latest_as_of": latest_as_of,
            "age_seconds": age_seconds,
            "threshold_seconds": threshold_seconds,
            "quality_status": quality_status,
            "quality_score": quality_score,
            "row_count": entry.row_count if entry else 0,
            "usable_for_trading": bool(entry.usable_for_trading) if entry else False,
            "execution_available": False,
            "next_action": freshness_next_action(status, dataset_type),
        }

    def _fallback_item(
        self,
        *,
        freshness_item: dict[str, Any],
        connection_providers: set[str],
        configured_external_sources: set[str],
    ) -> dict[str, Any]:
        dataset_type = str(freshness_item["dataset_type"])
        provider_order = DATASET_FALLBACK_PROVIDERS.get(dataset_type, ["manual_review"])
        source = str(freshness_item.get("source") or "")
        primary_provider = provider_order[0]
        fallback_providers = provider_order[1:]
        available_providers = [
            provider
            for provider in provider_order
            if provider in connection_providers
            or provider in configured_external_sources
            or provider in {"manual_review", "manual_csv"}
            or (provider == "ecb_reference_rates" and "ecb_reference_rates" in configured_external_sources)
            or (provider == "nasdaq_public_dividends" and "nasdaq_public_dividends" in configured_external_sources)
        ]
        active_provider = source if source else None
        freshness_status = str(freshness_item["status"])

        blockers: list[str] = []
        warnings: list[str] = []
        next_actions: list[str] = []
        if freshness_status == "fresh":
            status = "primary_fresh" if active_provider == primary_provider else "fallback_available"
            next_actions.append(f"{dataset_type} is fresh; keep fallback order documented and monitor freshness.")
        elif any(provider not in {primary_provider, "manual_review", "manual_csv"} for provider in available_providers):
            status = "fallback_required"
            warnings.append(f"{dataset_type} is {freshness_status}; use a configured fallback provider before downstream decisions.")
            next_actions.append(f"Refresh {dataset_type} from fallback provider: {next((provider for provider in available_providers if provider not in {primary_provider, 'manual_review', 'manual_csv'}), available_providers[0])}.")
        elif any(provider in {"manual_review", "manual_csv"} for provider in available_providers):
            status = "manual_review_available"
            warnings.append(f"{dataset_type} is {freshness_status}; no automated fallback is ready.")
            next_actions.append(f"Use manual CSV/review for {dataset_type}, then inspect quality report before downstream decisions.")
        else:
            status = "fail_closed"
            blockers.append(f"No fallback provider is configured for {dataset_type}.")
            next_actions.append(f"Configure a read-only fallback provider or manual import path for {dataset_type}.")

        if freshness_status == "blocked":
            blockers.append(f"{dataset_type} has a blocking quality issue; fallback must stay fail-closed for approval and execution.")
        if freshness_status in {"missing", "stale", "blocked"}:
            next_actions.append(str(freshness_item["next_action"]))

        return {
            "dataset_type": dataset_type,
            "label": freshness_item["label"],
            "freshness_status": freshness_status,
            "status": status,
            "primary_provider": primary_provider,
            "fallback_providers": fallback_providers,
            "available_providers": available_providers,
            "active_provider": active_provider,
            "snapshot_id": freshness_item.get("snapshot_id"),
            "quality_report_id": freshness_item.get("quality_report_id"),
            "blockers": dedupe(blockers),
            "warnings": dedupe(warnings),
            "next_actions": dedupe(next_actions),
            "route": "/?module=settings&tab=data",
            "fail_closed": bool(blockers),
            "can_unlock_order_approval": False,
            "execution_available": False,
        }


def freshness_next_action(status: str, dataset_type: str) -> str:
    if status == "missing":
        return f"Import or sync {dataset_type} from a read-only source."
    if status == "blocked":
        return f"Review the latest {dataset_type} quality report and refresh before using it in decisions."
    if status == "stale":
        return f"Refresh {dataset_type}; the latest snapshot is older than the freshness policy."
    return "No action required while the snapshot remains fresh."


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, (tuple, set)):
        return list(value)
    return [value]


def dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            result.append(item)
            seen.add(item)
    return result


def required_readonly_scopes(provider: str) -> list[str]:
    if provider in {"ibkr_readonly", "futu_readonly"}:
        return ["account:read", "positions:read", "balances:read", "orders:read_optional"]
    if provider in {"cex_readonly", "binance_spot_readonly"}:
        return ["account:read", "balances:read", "positions:read", "withdrawals:disabled", "trading:disabled"]
    if provider == "wallet_readonly":
        return ["public_address:read", "balances:read", "transactions:read"]
    return ["data:read"]


def sample_snapshot_schema(provider: str) -> dict[str, Any]:
    common = {
        "positions": [{"symbol": "AAPL", "quantity": "1", "market_value": "100"}],
        "balances": [{"currency": "USD", "cash_value": "100"}],
        "orders": [],
    }
    if provider == "wallet_readonly":
        return common | {"chain_id": "1", "public_address": "0x...", "signing_available": False}
    if provider == "binance_spot_readonly":
        return common | {"exchange": "binance_spot", "withdrawals_allowed": False, "trading_enabled": False, "authenticated_account_snapshot": True}
    if provider == "cex_readonly":
        return common | {"exchange": "binance", "withdrawals_allowed": False, "trading_enabled": False}
    return common
