from datetime import datetime
from datetime import date
from typing import Any
from typing import Literal

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import field_validator
from pydantic import model_validator


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


SECRET_CONFIG_KEY_FRAGMENTS = {
    "api_key",
    "apikey",
    "authorization",
    "bearer",
    "client_secret",
    "mnemonic",
    "password",
    "private_key",
    "secret",
    "seed",
    "token",
}


def contains_secret_config_key(value: Any) -> bool:
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = str(key).lower().replace("-", "_")
            safe_negative_marker = normalized in {"contains_secret", "contains_secrets"} and nested is False
            if any(fragment in normalized for fragment in SECRET_CONFIG_KEY_FRAGMENTS) and not safe_negative_marker:
                return True
            if contains_secret_config_key(nested):
                return True
    if isinstance(value, list):
        return any(contains_secret_config_key(item) for item in value)
    return False


SECRET_REFERENCE_PREFIXES = ("env:", "secretref:", "vault:", "keychain:", "local-secret:")
INLINE_SECRET_MARKERS = (
    "-----begin",
    "api_key=",
    "apikey=",
    "authorization:",
    "bearer ",
    "client_secret=",
    "password=",
    "private_key=",
    "secret=",
    "token=",
)
INLINE_SECRET_PREFIXES = ("akia", "ghp_", "gho_", "ghu_", "github_pat_", "sk-", "xoxb-", "xoxp-")


def looks_like_inline_secret_reference(value: str) -> bool:
    stripped = value.strip()
    lowered = stripped.lower()
    if not stripped:
        return False
    if lowered.startswith(SECRET_REFERENCE_PREFIXES):
        return False
    if any(lowered.startswith(prefix) for prefix in INLINE_SECRET_PREFIXES):
        return True
    if any(marker in lowered for marker in INLINE_SECRET_MARKERS):
        return True
    return len(stripped) > 96 and not any(separator in stripped for separator in (":", "/", "."))


class AssetCreate(BaseModel):
    symbol: str
    name: str
    asset_type: str
    market: str
    venue: str
    currency: str
    chain_id: str | None = None
    contract_address: str | None = None
    tradable: bool = False
    manual_enabled: bool = False
    auto_enabled: bool = False
    risk_level: str = "medium"
    sector: str | None = None
    industry: str | None = None
    themes_json: list[str] = Field(default_factory=list)
    factor_tags_json: list[str] = Field(default_factory=list)
    classification_source: str | None = None
    classification_snapshot_id: str | None = None


class AssetClassificationUpdate(BaseModel):
    sector: str | None = None
    industry: str | None = None
    themes_json: list[str] = Field(default_factory=list)
    factor_tags_json: list[str] = Field(default_factory=list)
    classification_source: str
    classification_snapshot_id: str | None = None


class AssetRead(AssetCreate, ORMModel):
    id: str
    created_at: datetime
    updated_at: datetime


class AccountCreate(BaseModel):
    name: str
    account_type: str
    broker: str
    base_currency: str
    mode: str = "read_only"
    live_trading_enabled: bool = False


class AccountRead(AccountCreate, ORMModel):
    id: str
    created_at: datetime
    updated_at: datetime


class PositionCreate(BaseModel):
    account_id: str
    asset_id: str
    quantity: float
    average_cost: float = 0
    market_price: float = 0
    market_value: float = 0
    unrealized_pnl: float = 0
    realized_pnl: float = 0
    weight: float = 0


class PositionRead(PositionCreate, ORMModel):
    id: str
    updated_at: datetime


class PortfolioSnapshotCreate(BaseModel):
    account_id: str | None = None
    total_value: float = 0
    cash_value: float = 0
    positions_value: float = 0
    currency: str = "USD"
    snapshot_json: dict = Field(default_factory=dict)


class PortfolioSnapshotRead(PortfolioSnapshotCreate, ORMModel):
    id: str
    created_at: datetime


class PortfolioCurrentRead(BaseModel):
    total_equity: float
    cash: float
    allocation: dict[str, float]
    positions: list[dict]


class PortfolioDailySummaryRead(BaseModel):
    total_equity: float
    cash: float
    allocation: dict[str, float]
    daily_pnl: float = 0
    top_winners: list[dict]
    top_losers: list[dict]
    concentration_risks: list[dict]
    suggested_attention: list[str]


class DataSnapshotRead(ORMModel):
    id: str
    snapshot_type: str
    as_of: datetime
    data_json: dict[str, Any]
    metadata_json: dict[str, Any]
    created_at: datetime


class DataQualityReportRead(ORMModel):
    id: str
    data_snapshot_id: str | None
    source: str
    metric_type: str
    score: float
    details_json: dict[str, Any]
    created_at: datetime


class DataCatalogEntryRead(ORMModel):
    id: str
    dataset_type: str
    source: str
    source_ref: str | None
    data_snapshot_id: str | None
    quality_report_id: str | None
    row_count: int
    quality_status: str
    usable_for_trading: bool
    lineage_json: dict[str, Any]
    contract_json: dict[str, Any]
    created_at: datetime


class DataCatalogOverviewRead(BaseModel):
    total_entries: int
    usable_for_trading_count: int
    blocked_count: int
    quality_counts: dict[str, int]
    latest_entries: list[DataCatalogEntryRead]
    blockers: list[DataCatalogEntryRead]


class DataCatalogEntryDetailRead(BaseModel):
    entry: DataCatalogEntryRead
    snapshot: DataSnapshotRead | None = None
    quality_report: DataQualityReportRead | None = None
    contract_status: Literal["usable", "review_only", "blocked"]
    blockers: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    related_action: dict[str, Any] = Field(default_factory=dict)
    execution_available: bool = False


class DataTrustItemRead(BaseModel):
    dataset_type: str
    required: bool = True
    requires_trading_usable: bool = False
    status: Literal["trusted", "review_only", "missing", "stale", "invalid", "blocked"]
    entry: DataCatalogEntryRead | None = None
    snapshot_id: str | None = None
    quality_report_id: str | None = None
    quality_status: str | None = None
    quality_score: float | None = None
    age_seconds: int | None = None
    threshold_seconds: int
    blockers: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)


class DataTrustReportRead(BaseModel):
    decision_scope: Literal["research", "order_draft", "ledger", "daily_review"]
    overall_status: Literal["trusted", "review_only", "blocked"]
    checked_at: datetime
    trusted_count: int
    review_only_count: int
    blocked_count: int
    items: list[DataTrustItemRead] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    execution_available: bool = False


class InvestmentLedgerEntryRead(ORMModel):
    id: str
    user_id: str
    account_id: str | None
    asset_id: str | None
    source_type: str
    source_id: str | None
    entry_type: str
    side: str | None
    quantity_delta: float
    cash_delta: float
    price: float | None
    fee_amount: float
    realized_pnl: float
    currency: str
    occurred_at: datetime
    status: str
    metadata_json: dict[str, Any]
    created_at: datetime


class LedgerSyncResponse(BaseModel):
    user_id: str
    synced_at: datetime
    entries_created: int
    entries_existing: int
    position_entries_created: int
    paper_entries_created: int
    data_trust_status: str = "unknown"
    data_trust_report: DataTrustReportRead | None = None
    execution_available: bool = False
    entries: list[InvestmentLedgerEntryRead] = Field(default_factory=list)


class ReconciliationBreakRead(ORMModel):
    id: str
    reconciliation_run_id: str
    account_id: str | None
    asset_id: str | None
    break_type: str
    severity: str
    expected_quantity: float
    observed_quantity: float
    delta_quantity: float
    expected_cash: float
    observed_cash: float
    delta_cash: float
    detail: str
    metadata_json: dict[str, Any]
    created_at: datetime


class ReconciliationRunRead(ORMModel):
    id: str
    user_id: str
    scope: str
    status: str
    source_snapshot_id: str | None
    checked_at: datetime
    positions_checked: int
    ledger_entries_checked: int
    breaks_count: int
    summary_json: dict[str, Any]
    execution_available: bool = False


class LedgerReconciliationReportRead(BaseModel):
    run: ReconciliationRunRead
    breaks: list[ReconciliationBreakRead] = Field(default_factory=list)
    data_trust_status: str = "unknown"
    data_trust_report: DataTrustReportRead | None = None
    execution_available: bool = False


class LedgerPreflightCheckRead(BaseModel):
    key: str
    label: str
    status: Literal["ok", "warn", "block"]
    summary: str
    details: dict[str, Any] = Field(default_factory=dict)


class LedgerPreflightRead(BaseModel):
    user_id: str
    status: Literal["ok", "warn", "block"]
    checked_at: datetime
    can_sync: bool
    can_reconcile: bool
    ledger_entries_count: int
    positions_count: int
    paper_executions_count: int
    data_trust_status: str
    data_trust_report: DataTrustReportRead
    latest_reconciliation: LedgerReconciliationReportRead | None = None
    checks: list[LedgerPreflightCheckRead] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    local_next_steps: list[dict[str, Any]] = Field(default_factory=list)
    promotion_gate: dict[str, Any] = Field(default_factory=dict)
    execution_available: bool = False


class StatementImportBatchRead(ORMModel):
    id: str
    user_id: str
    provider: str
    account_label: str | None
    statement_type: str
    source_ref: str | None
    raw_payload_hash: str
    row_count: int
    imported_count: int
    skipped_count: int
    status: str
    summary_json: dict[str, Any]
    execution_available: bool = False
    created_at: datetime


class StatementImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = "default-user"
    provider: str = "manual_statement"
    account_label: str | None = None
    statement_type: Literal["broker_statement", "cex_statement", "wallet_statement", "bank_statement"] = "broker_statement"
    source_ref: str | None = None
    default_currency: str = "USD"
    csv_text: str = Field(min_length=1)

    @model_validator(mode="after")
    def reject_inline_secrets(self) -> "StatementImportRequest":
        metadata = {
            "provider": self.provider,
            "account_label": self.account_label or "",
            "statement_type": self.statement_type,
            "source_ref": self.source_ref or "",
        }
        if contains_secret_config_key(metadata):
            raise ValueError("statement metadata must not contain secret-like keys")
        if looks_like_inline_secret_reference(self.provider) or looks_like_inline_secret_reference(self.source_ref or ""):
            raise ValueError("statement metadata must not contain inline secrets")
        return self


class StatementImportResponse(BaseModel):
    batch: StatementImportBatchRead
    snapshot: DataSnapshotRead
    quality_report: DataQualityReportRead
    catalog_entry: DataCatalogEntryRead
    ledger_entries: list[InvestmentLedgerEntryRead] = Field(default_factory=list)
    skipped: list[dict[str, Any]] = Field(default_factory=list)
    execution_available: bool = False


class CsvImportRequest(BaseModel):
    import_type: Literal["holdings", "trades", "crypto_holdings", "wallet_balances"] = "holdings"
    csv_text: str = Field(min_length=1)
    source_name: str = "manual_csv"
    source_ref: str | None = None
    default_account_name: str = "CSV Import Account"
    default_account_type: str = "manual"
    default_currency: str = "USD"
    persist_positions: bool = True
    can_be_used_for_trading: bool = False

    @model_validator(mode="after")
    def reject_inline_secrets(self) -> "CsvImportRequest":
        if contains_secret_config_key({"source_name": self.source_name, "source_ref": self.source_ref or ""}):
            raise ValueError("CSV import metadata must not contain secret-like keys")
        if looks_like_inline_secret_reference(self.source_name) or looks_like_inline_secret_reference(self.source_ref or ""):
            raise ValueError("CSV import metadata must not contain inline secrets")
        return self


class CsvImportResponse(BaseModel):
    import_type: str
    rows_received: int
    rows_imported: int
    rows_skipped: int
    accounts_created: int
    assets_created: int
    positions_upserted: int
    snapshot: DataSnapshotRead
    quality_report: DataQualityReportRead
    catalog_entry: DataCatalogEntryRead
    skipped: list[dict[str, Any]] = Field(default_factory=list)
    execution_available: bool = False


class CandleRead(ORMModel):
    id: str
    asset_id: str
    timeframe: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    source: str


class DataQualityExplanationRead(BaseModel):
    report: DataQualityReportRead
    level: Literal["good", "warning", "bad"]
    summary: str
    explanations: list[str]
    recommended_actions: list[str]
    blocks_trading_decisions: bool


class DemoStepStatusRead(BaseModel):
    key: str
    module: str
    label: str
    status: str
    detail: str
    action_label: str
    action_detail: str
    blockers: list[str] = Field(default_factory=list)


class DemoStatusRead(BaseModel):
    seeded: bool
    last_data_update_at: datetime | None = None
    data_quality_status: str
    global_risk_status: str
    automation_level: str
    current_workflow_stage: str
    next_workflow_stage: str | None = None
    counts: dict[str, int]
    steps: list[DemoStepStatusRead]


class DemoSeedResponse(BaseModel):
    status: DemoStatusRead


class DataSourceProviderRead(BaseModel):
    provider: str
    display_name: str
    source_type: str
    mode: Literal["read_only"]
    capabilities: list[str]
    status: str
    requires_credentials: bool = False
    supports_custom_config: bool = False
    config_schema: dict[str, Any] = Field(default_factory=dict)
    notes: str


class DataSourceConnectionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    provider: str
    source_type: str = "market_data"
    mode: Literal["read_only"] = "read_only"
    base_url: str | None = None
    credentials_ref: str | None = None
    config_json: dict[str, Any] = Field(default_factory=dict)
    capabilities_json: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def reject_inline_secrets(self) -> "DataSourceConnectionCreate":
        if contains_secret_config_key(self.config_json):
            raise ValueError("config_json must not contain inline secrets; use credentials_ref instead")
        return self


class DataSourceConnectionRead(DataSourceConnectionCreate, ORMModel):
    id: str
    status: str
    last_health_status: str | None
    last_health_checked_at: datetime | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime


class DataSourceHealthRead(BaseModel):
    connection_id: str | None = None
    provider: str
    status: str
    checked_at: datetime
    latency_ms: float | None = None
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class DataSourceQuoteImportRequest(BaseModel):
    symbols: list[str] = Field(min_length=1, max_length=50)
    asset_type: str = "stock"
    market: str = "US"
    venue: str | None = None
    currency: str = "USD"


class DataSourceQuoteImportResponse(BaseModel):
    connection: DataSourceConnectionRead
    quotes_imported: int
    symbols: list[str]
    skipped: list[dict[str, str]] = Field(default_factory=list)
    snapshot: DataSnapshotRead
    quality_report: DataQualityReportRead
    catalog_entry: DataCatalogEntryRead


class DataSourceCandleImportRequest(BaseModel):
    symbols: list[str] = Field(min_length=1, max_length=50)
    timeframe: Literal["1d", "1h"] = "1d"
    limit: int = Field(default=30, ge=1, le=365)
    asset_type: str = "stock"
    market: str = "US"
    venue: str | None = None
    currency: str = "USD"


class DataSourceCandleImportResponse(BaseModel):
    connection: DataSourceConnectionRead
    candles_imported: int
    symbols: list[str]
    timeframe: str
    skipped: list[dict[str, str]] = Field(default_factory=list)
    snapshot: DataSnapshotRead
    quality_report: DataQualityReportRead
    catalog_entry: DataCatalogEntryRead


class DataSourceAccountSyncRequest(BaseModel):
    sample_payload: dict[str, Any] | None = None
    persist_positions: bool = True
    user_id: str = "default-user"

    @model_validator(mode="after")
    def reject_inline_secrets(self) -> "DataSourceAccountSyncRequest":
        if contains_secret_config_key(self.sample_payload or {}):
            raise ValueError("sample_payload must not contain inline secrets")
        return self


class DataSourceAccountSyncResponse(BaseModel):
    connection: DataSourceConnectionRead
    account: AccountRead | None = None
    positions_synced: int
    balances_synced: int
    orders_seen: int
    snapshot: DataSnapshotRead
    quality_report: DataQualityReportRead
    portfolio_snapshot: PortfolioSnapshotRead | None = None
    catalog_entry: DataCatalogEntryRead
    ledger_sync: dict[str, Any]
    reconciliation: dict[str, Any]


class DataSourceAccountAutoRefreshRequest(BaseModel):
    user_id: str = "default-user"
    enabled: bool = True
    interval_minutes: int = Field(default=15, ge=5, le=1440)


class DataSourceReadOnlySetupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Literal["ibkr_readonly", "futu_readonly", "cex_readonly", "binance_spot_readonly", "wallet_readonly"]
    name: str | None = None
    account_label: str | None = None
    credentials_ref: str | None = None
    config_json: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def reject_inline_secrets(self) -> "DataSourceReadOnlySetupRequest":
        if contains_secret_config_key(self.config_json):
            raise ValueError("config_json must not contain inline secrets; store only non-sensitive adapter settings")
        if self.credentials_ref and looks_like_inline_secret_reference(self.credentials_ref):
            raise ValueError("credentials_ref must point to a stored reference, not an inline secret")
        return self


class DataSourceReadOnlySetupResponse(BaseModel):
    connection: DataSourceConnectionRead
    provider_status: str
    safety_checks: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    execution_available: bool = False


class DataSourceReadOnlyPreflightResponse(BaseModel):
    connection: DataSourceConnectionRead
    provider: str
    status: Literal["blocked", "ready_for_sample_sync", "sample_sync_available"]
    checked_at: datetime
    has_credentials_ref: bool
    requires_credentials: bool
    missing_requirements: list[str] = Field(default_factory=list)
    blocking_reasons: list[str] = Field(default_factory=list)
    safety_checks: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)
    execution_available: bool = False
    order_routing_available: bool = False
    withdrawals_allowed: bool = False
    signing_available: bool = False


class DataFreshnessItemRead(BaseModel):
    dataset_type: str
    label: str
    status: Literal["fresh", "stale", "missing", "blocked"]
    source: str | None = None
    source_ref: str | None = None
    snapshot_id: str | None = None
    quality_report_id: str | None = None
    latest_as_of: datetime | None = None
    age_seconds: int | None = None
    threshold_seconds: int
    quality_status: str | None = None
    quality_score: float | None = None
    row_count: int = 0
    usable_for_trading: bool = False
    execution_available: bool = False
    next_action: str


class DataFreshnessOverviewRead(BaseModel):
    checked_at: datetime
    overall_status: Literal["ok", "warn", "block"]
    stale_count: int
    missing_count: int
    blocked_count: int
    execution_available: bool = False
    items: list[DataFreshnessItemRead] = Field(default_factory=list)


class ScheduledJobCreate(BaseModel):
    name: str
    job_type: Literal["quote_import", "candle_import", "signal_generate"] = "quote_import"
    status: Literal["active", "paused"] = "paused"
    schedule_json: dict[str, Any] = Field(default_factory=lambda: {"mode": "manual"})
    target_json: dict[str, Any]


class ScheduledJobRead(ScheduledJobCreate, ORMModel):
    job_type: str
    id: str
    last_run_at: datetime | None
    last_run_status: str | None
    last_run_summary: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class ScheduledJobRunResponse(BaseModel):
    job: ScheduledJobRead
    result: dict[str, Any]
    execution_available: bool = False


class WatchlistItemCreate(BaseModel):
    user_id: str = "default-user"
    symbol: str
    asset_id: str | None = None
    investment_thesis_id: str | None = None
    name: str | None = None
    asset_type: str = "stock"
    market: str = "US"
    priority: Literal["low", "normal", "high"] = "normal"
    alert_rules_json: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = None

    @model_validator(mode="after")
    def reject_inline_secrets(self) -> "WatchlistItemCreate":
        if contains_secret_config_key(self.alert_rules_json):
            raise ValueError("alert_rules_json must not contain inline secrets")
        return self


class WatchlistItemUpdate(BaseModel):
    investment_thesis_id: str | None = None
    name: str | None = None
    priority: Literal["low", "normal", "high"] | None = None
    alert_rules_json: dict[str, Any] | None = None
    notes: str | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def reject_inline_secrets(self) -> "WatchlistItemUpdate":
        if contains_secret_config_key(self.alert_rules_json or {}):
            raise ValueError("alert_rules_json must not contain inline secrets")
        return self


class WatchlistItemRead(ORMModel):
    id: str
    user_id: str
    asset_id: str | None
    investment_thesis_id: str | None
    symbol: str
    name: str | None
    asset_type: str
    market: str
    priority: str
    alert_rules_json: dict[str, Any]
    notes: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ReminderCreate(BaseModel):
    user_id: str = "default-user"
    title: str
    reminder_type: Literal["manual", "thesis_review", "data_refresh", "post_trade_review", "export_backup"] = "manual"
    related_entity_type: str | None = None
    related_entity_id: str | None = None
    due_at: datetime | None = None
    recurrence_json: dict[str, Any] = Field(default_factory=dict)
    priority: Literal["low", "normal", "high"] = "normal"
    payload_json: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def reject_inline_secrets(self) -> "ReminderCreate":
        if contains_secret_config_key(self.recurrence_json) or contains_secret_config_key(self.payload_json):
            raise ValueError("reminder payload must not contain inline secrets")
        return self


class ReminderUpdate(BaseModel):
    title: str | None = None
    due_at: datetime | None = None
    recurrence_json: dict[str, Any] | None = None
    priority: Literal["low", "normal", "high"] | None = None
    status: Literal["pending", "snoozed", "done", "dismissed"] | None = None
    payload_json: dict[str, Any] | None = None

    @model_validator(mode="after")
    def reject_inline_secrets(self) -> "ReminderUpdate":
        if contains_secret_config_key(self.recurrence_json or {}) or contains_secret_config_key(self.payload_json or {}):
            raise ValueError("reminder payload must not contain inline secrets")
        return self


class ReminderRead(ORMModel):
    id: str
    user_id: str
    title: str
    reminder_type: str
    related_entity_type: str | None
    related_entity_id: str | None
    due_at: datetime | None
    recurrence_json: dict[str, Any]
    priority: str
    status: str
    payload_json: dict[str, Any]
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class LocalUserConfigUpsert(BaseModel):
    user_id: str = "default-user"
    value_json: dict[str, Any] = Field(default_factory=dict)
    description: str | None = None

    @model_validator(mode="after")
    def reject_inline_secrets(self) -> "LocalUserConfigUpsert":
        if contains_secret_config_key(self.value_json):
            raise ValueError("local config must not contain inline secrets")
        return self


class LocalUserConfigRead(ORMModel):
    id: str
    user_id: str
    config_key: str
    value_json: dict[str, Any]
    description: str | None
    created_at: datetime
    updated_at: datetime


class DailyExportRequest(BaseModel):
    user_id: str = "default-user"
    export_type: Literal["daily_snapshot", "watchlist", "reviews", "local_backup_manifest"] = "daily_snapshot"
    include_sections: list[str] = Field(default_factory=list)


class ExportArtifactRead(ORMModel):
    id: str
    user_id: str
    export_type: str
    format: str
    status: str
    payload_json: dict[str, Any]
    summary_json: dict[str, Any]
    file_path: str | None
    created_at: datetime


class DailyUseOverviewRead(BaseModel):
    user_id: str
    watchlist_count: int
    active_reminders_count: int
    due_reminders_count: int
    scheduled_jobs_count: int
    last_export: ExportArtifactRead | None = None
    backup_recommended: bool = False
    execution_available: bool = False


class DailyActionItemRead(BaseModel):
    id: str
    action_type: str
    priority: Literal["low", "normal", "high"]
    title: str
    detail: str
    status: Literal["open"] = "open"
    source: str
    related_entity_type: str | None = None
    related_entity_id: str | None = None
    due_at: datetime | None = None
    created_at: datetime | None = None
    next_action: str
    action_label: str
    route: str
    guidance_steps: list[str] = Field(default_factory=list)
    evidence_status: dict[str, Any] | None = None
    execution_available: bool = False


class DailyActionQueueRead(BaseModel):
    user_id: str
    generated_at: datetime
    total_actions: int
    due_count: int
    high_priority_count: int
    execution_available: bool = False
    actions: list[DailyActionItemRead] = Field(default_factory=list)


class WorkflowDeepReviewItemRead(BaseModel):
    id: str
    item_type: str
    priority: Literal["low", "normal", "high"]
    title: str
    detail: str
    stage: str
    source: str
    related_entity_type: str
    related_entity_id: str
    asset_id: str | None = None
    asset_symbol: str | None = None
    thesis_id: str | None = None
    order_intent_id: str | None = None
    order_draft_id: str | None = None
    review_id: str | None = None
    next_action: str
    blockers: list[str] = Field(default_factory=list)
    task_id: str | None = None
    assignment_status: str = "unassigned"
    assignee_id: str | None = None
    due_at: datetime | None = None
    execution_available: bool = False


class WorkflowDeepReviewQueueRead(BaseModel):
    user_id: str
    generated_at: datetime
    total_items: int
    high_priority_count: int
    blocked_count: int
    execution_available: bool = False
    items: list[WorkflowDeepReviewItemRead] = Field(default_factory=list)


class StageReadinessCheckRead(BaseModel):
    stage_number: int
    stage_key: str
    label: str
    status: Literal["ok", "warn", "block"]
    detail: str
    blockers: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    related_entity_type: str | None = None
    related_entity_id: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)


class StageReadinessItemRead(BaseModel):
    id: str
    subject_type: Literal["order_intent", "order_draft"]
    readiness: Literal["ready_for_human_review", "review_required", "blocked"]
    title: str
    detail: str
    asset_id: str | None = None
    asset_symbol: str | None = None
    order_intent_id: str
    order_draft_id: str | None = None
    strategy_playbook_id: str | None = None
    thesis_id: str | None = None
    current_workflow_state: str | None = None
    blockers: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    checks: list[StageReadinessCheckRead] = Field(default_factory=list)
    created_at: datetime
    execution_available: bool = False


class StageReadinessQueueRead(BaseModel):
    user_id: str
    generated_at: datetime
    total_items: int
    ready_count: int
    review_required_count: int
    blocked_count: int
    execution_available: bool = False
    items: list[StageReadinessItemRead] = Field(default_factory=list)


class OrderClosureCheckRead(BaseModel):
    stage_key: str
    label: str
    status: Literal["ok", "warn", "block"]
    detail: str
    blockers: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    related_entity_type: str | None = None
    related_entity_id: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)


class OrderClosureItemRead(BaseModel):
    id: str
    status: Literal["closed", "review_required", "blocked"]
    title: str
    detail: str
    asset_id: str | None = None
    asset_symbol: str | None = None
    order_intent_id: str | None = None
    order_draft_id: str
    thesis_id: str | None = None
    execution_id: str | None = None
    post_trade_review_id: str | None = None
    blockers: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    checks: list[OrderClosureCheckRead] = Field(default_factory=list)
    created_at: datetime
    execution_available: bool = False


class OrderClosureReportRead(BaseModel):
    user_id: str
    generated_at: datetime
    total_items: int
    closed_count: int
    review_required_count: int
    blocked_count: int
    execution_available: bool = False
    items: list[OrderClosureItemRead] = Field(default_factory=list)


class WorkflowReviewTaskCreate(BaseModel):
    user_id: str = "default-user"
    queue_item_id: str
    item_type: str
    title: str
    detail: str
    priority: Literal["low", "normal", "high"] = "normal"
    assignee_id: str | None = None
    due_at: datetime | None = None
    related_entity_type: str
    related_entity_id: str
    payload_json: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def reject_inline_secrets(self) -> "WorkflowReviewTaskCreate":
        if contains_secret_config_key(self.payload_json):
            raise ValueError("workflow task payload must not contain inline secrets")
        return self


class WorkflowReviewTaskRead(ORMModel):
    id: str
    user_id: str
    queue_item_id: str
    item_type: str
    title: str
    detail: str
    priority: str
    status: str
    assignee_id: str | None
    due_at: datetime | None
    related_entity_type: str
    related_entity_id: str
    payload_json: dict[str, Any]
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class UserAccountCreate(BaseModel):
    user_id: str = "default-user"
    display_name: str = "Default User"
    role: Literal["owner", "admin", "operator", "viewer"] = "owner"
    status: Literal["active", "disabled", "invited"] = "active"
    permissions_json: list[str] = Field(default_factory=list)
    onboarding_state_json: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def reject_inline_secrets(self) -> "UserAccountCreate":
        if contains_secret_config_key(self.onboarding_state_json):
            raise ValueError("onboarding_state_json must not contain inline secrets")
        return self


class UserAccountRead(UserAccountCreate, ORMModel):
    id: str
    last_seen_at: datetime | None
    created_at: datetime
    updated_at: datetime


class SecretReferenceCreate(BaseModel):
    user_id: str = "default-user"
    reference_key: str
    provider: str
    scope: str = "read_only"
    storage_backend: str = "env_or_local_secret_store"
    status: Literal["active", "disabled", "rotating", "invalid"] = "active"
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def reject_inline_secrets(self) -> "SecretReferenceCreate":
        if contains_secret_config_key(self.metadata_json):
            raise ValueError("metadata_json must not contain inline secrets; store only references and non-sensitive hints")
        return self


class SecretReferenceRead(SecretReferenceCreate, ORMModel):
    id: str
    last_verified_at: datetime | None
    created_at: datetime
    updated_at: datetime


class OperationalEventCreate(BaseModel):
    user_id: str | None = None
    event_type: str
    severity: Literal["info", "warning", "error", "critical"] = "info"
    source: str
    message: str
    status: Literal["open", "acknowledged", "resolved", "closed"] = "open"
    request_id: str | None = None
    payload_json: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def reject_inline_secrets(self) -> "OperationalEventCreate":
        if contains_secret_config_key(self.payload_json):
            raise ValueError("payload_json must not contain inline secrets")
        return self


class OperationalEventRead(OperationalEventCreate, ORMModel):
    id: str
    created_at: datetime


class LiveExecutionConfigCreate(BaseModel):
    user_id: str = "default-user"
    exchange_type: str
    api_key_ref: str
    label: str

    @model_validator(mode="after")
    def reject_inline_secret_reference(self) -> "LiveExecutionConfigCreate":
        if not self.exchange_type.strip():
            raise ValueError("exchange_type is required")
        if not self.label.strip():
            raise ValueError("label is required")
        if not self.api_key_ref.strip():
            raise ValueError("api_key_ref must point to a stored secret reference")
        if looks_like_inline_secret_reference(self.api_key_ref):
            raise ValueError("api_key_ref must be a reference, not an inline secret")
        return self


class LiveExecutionConfigRead(ORMModel):
    id: str
    user_id: str
    exchange_type: str
    api_key_ref: str
    label: str
    is_active: bool
    created_at: datetime


class BrokerConnectionCreate(BaseModel):
    broker_type: str
    label: str
    api_key_ref: str

    @model_validator(mode="after")
    def reject_inline_secret_reference(self) -> "BrokerConnectionCreate":
        if not self.broker_type.strip():
            raise ValueError("broker_type is required")
        if not self.label.strip():
            raise ValueError("label is required")
        if not self.api_key_ref.strip():
            raise ValueError("api_key_ref must point to a stored secret reference")
        if looks_like_inline_secret_reference(self.api_key_ref):
            raise ValueError("api_key_ref must be a reference, not an inline secret")
        return self


class BrokerConnectionRead(BaseModel):
    id: str
    broker_type: str
    label: str
    api_key_ref: str
    status: str
    created_at: datetime


class BrokerHealthResponse(BaseModel):
    connected: bool
    latency_ms: int
    error: str | None = None


class LiveExecutionPrepareRequest(BaseModel):
    order_draft_id: str


class LiveExecutionPrepareResponse(BaseModel):
    order_draft_id: str
    order_intent_id: str
    asset_id: str
    draft_approval_status: str
    draft_execution_status: str
    passed: bool
    blocking_reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class LiveExecutionApprovalRequest(BaseModel):
    order_draft_id: str
    approver_id: str
    decision_reason: str | None = None


class LiveExecutionApprovalResponse(BaseModel):
    approved: bool
    details: dict[str, Any] = Field(default_factory=dict)


class LiveExecutionExecuteRequest(BaseModel):
    order_draft_id: str
    approver_id: str
    decision_reason: str | None = None
    force_fill_price: str | None = None


class LiveExecutionExecuteResponse(BaseModel):
    order_draft_id: str
    execution_id: str
    status: str
    filled_quantity: str
    fill_price: str
    blocking_reasons: list[str] = Field(default_factory=list)
    rollback_plan: dict[str, Any] = Field(default_factory=dict)


class LiveExecutionSandboxRequest(BaseModel):
    order_draft_id: str
    approver_id: str = "sandbox-user"
    decision_reason: str | None = None
    force_fill_price: str | None = None
    scenario_label: str = "controlled_live_sandbox"


class LiveExecutionSandboxResponse(BaseModel):
    order_draft_id: str
    order_intent_id: str
    status: Literal["ready_for_dry_run", "blocked"]
    sandbox_only: bool = True
    execution_available: bool = False
    real_broker_call_performed: bool = False
    blocking_reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    readiness: dict[str, Any] = Field(default_factory=dict)
    requested_order: dict[str, Any] = Field(default_factory=dict)
    broker_submission: dict[str, Any] = Field(default_factory=dict)
    rollback_plan: dict[str, Any] = Field(default_factory=dict)


class LiveExecutionSmallPilotReadinessRequest(BaseModel):
    order_draft_id: str
    approver_id: str = "pilot-reviewer"
    max_notional: str = "100"
    force_fill_price: str | None = None


class LiveExecutionSmallPilotCheckRead(BaseModel):
    key: str
    label: str
    status: Literal["ok", "warn", "block"]
    detail: str
    blockers: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)


class LiveExecutionSmallPilotReadinessResponse(BaseModel):
    order_draft_id: str
    order_intent_id: str
    pilot_status: Literal["ready_for_manual_approval", "review_required", "blocked"]
    max_notional: str
    estimated_notional: str
    execution_available: bool = False
    real_broker_call_allowed: bool = False
    blockers: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    readiness: dict[str, Any] = Field(default_factory=dict)
    rollback_plan: dict[str, Any] = Field(default_factory=dict)
    checks: list[LiveExecutionSmallPilotCheckRead] = Field(default_factory=list)


class LiveExecutionHistoryEntry(BaseModel):
    id: str
    order_draft_id: str
    asset_id: str
    quantity: str
    price: str
    status: str
    created_at: datetime


class ControlledAutoEvaluateRequest(BaseModel):
    asset_id: str
    account_id: str
    target_quantity: str | None = None
    max_price: str | None = None
    target_pct: str | None = None
    current_pct: str | None = None
    stop_price: str | None = None
    current_price: str | None = None
    target_price: str | None = None
    strategy_playbook_id: str | None = None


class ControlledAutoEvaluationResponse(BaseModel):
    passed: bool
    blocking_reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class ControlledAutoExecuteResponse(BaseModel):
    order_intent_id: str
    status: str
    details: dict[str, Any] = Field(default_factory=dict)


class ModuleInfoRead(BaseModel):
    module_type: str
    name: str


class ModuleHealthStatusRead(BaseModel):
    module_type: str
    name: str
    available: bool
    registered: bool
    last_check: datetime
    details: str


class ModuleGateComplianceRead(BaseModel):
    module_type: str
    registered: bool
    gate_compliant: bool
    message: str


class SidecarPolicyEvaluateRequest(BaseModel):
    name: str
    sidecar_type: str
    capabilities: list[str] = Field(default_factory=list)
    control_pattern: str = "local_self_logic_to_sidecar_callback"
    creates_orders: bool = False
    executes_trades: bool = False
    post_approval_only: bool = False
    stores_secrets: bool = False
    mutates_core_state: bool = False
    source_of_truth_for: list[str] = Field(default_factory=list)
    requires_external_calls: bool = False


class SidecarPolicyEvaluateResponse(BaseModel):
    name: str
    sidecar_type: str
    status: Literal["approved", "review_required", "blocked"]
    allowed: bool
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    required_controls: list[str] = Field(default_factory=list)
    execution_available: bool = False
    real_broker_call_allowed: bool = False
    audit_required: bool = True


class KillSwitchEngageRequest(BaseModel):
    reason: str
    account_id: str | None = None
    asset_id: str | None = None
    engaged_by: str = "user"


class KillSwitchDisengageRequest(BaseModel):
    account_id: str | None = None
    asset_id: str | None = None
    reason: str | None = None
    disengaged_by: str = "user"


class KillSwitchEntry(ORMModel):
    id: str
    reason: str
    account_id: str | None
    asset_id: str | None
    engaged_by: str
    engaged_at: datetime
    disengaged_at: datetime | None


class KillSwitchCheckResponse(BaseModel):
    blocked: bool
    reason: str | None = None


class BetaReadinessCheckRead(BaseModel):
    key: str
    label: str
    status: Literal["ok", "warn", "block"]
    detail: str
    blockers: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)


class BetaReadinessRead(BaseModel):
    environment: str
    deployment_target: str
    checked_at: datetime
    beta_ready: bool
    execution_available: bool = False
    blockers: list[str] = Field(default_factory=list)
    checklist: list[BetaReadinessCheckRead]


class ExternalBetaLaunchCheckRead(BaseModel):
    key: str
    label: str
    status: Literal["ok", "warn", "block"]
    detail: str
    blockers: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)


class ExternalBetaLaunchReportRead(BaseModel):
    environment: str
    deployment_target: str
    checked_at: datetime
    launch_status: Literal["ready", "conditional", "blocked"]
    beta_ready: bool
    ops_status: Literal["ok", "warn", "block"]
    data_trust_status: Literal["trusted", "review_only", "blocked"]
    ledger_status: Literal["ok", "warn", "block"]
    execution_available: bool = False
    live_execution_available: bool = False
    blockers: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    release_controls: dict[str, Any] = Field(default_factory=dict)
    required_manual_steps: list[str] = Field(default_factory=list)
    checks: list[ExternalBetaLaunchCheckRead] = Field(default_factory=list)


class OpsReadinessCheckRead(BaseModel):
    key: str
    label: str
    status: Literal["ok", "warn", "block"]
    detail: str
    blockers: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)


class OpsStabilityReportRead(BaseModel):
    environment: str
    deployment_target: str
    checked_at: datetime
    overall_status: Literal["ok", "warn", "block"]
    execution_available: bool = False
    blockers: list[str] = Field(default_factory=list)
    commands: list[str] = Field(default_factory=list)
    checks: list[OpsReadinessCheckRead] = Field(default_factory=list)


class OpsRestoreDrillReportRead(BaseModel):
    user_id: str
    generated_at: datetime
    status: Literal["ok", "warn", "block"]
    latest_backup_artifact_id: str | None = None
    latest_backup_created_at: datetime | None = None
    operational_event: OperationalEventRead
    restore_steps: list[dict[str, Any]] = Field(default_factory=list)
    execution_available: bool = False


class ProductionReadinessTargetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = "default-user"
    target_type: Literal["error_reporting", "backup_target", "secret_manager", "deployment", "monitoring"] = "error_reporting"
    provider: str = "manual"
    label: str
    reference_key: str | None = None
    status: Literal["planned", "configured", "verified", "disabled"] = "configured"
    required: bool = True
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def reject_inline_secrets(self) -> "ProductionReadinessTargetCreate":
        if contains_secret_config_key(self.metadata_json):
            raise ValueError("production target metadata must not contain inline secrets")
        if self.reference_key and looks_like_inline_secret_reference(self.reference_key):
            raise ValueError("reference_key must point to a stored reference, not an inline secret")
        return self


class ProductionReadinessTargetRead(ProductionReadinessTargetCreate, ORMModel):
    id: str
    last_verified_at: datetime | None
    created_at: datetime
    updated_at: datetime


class BetaWhoAmIRead(BaseModel):
    user_id: str
    role: str
    permissions: list[str]
    auth_required: bool
    token_configured: bool
    execution_available: bool = False


class BetaAccessCheckRead(BaseModel):
    permission: str
    allowed: bool
    user_id: str
    role: str
    reason: str


ReportType = Literal[
    "portfolio_daily_review",
    "single_asset_research",
    "technical_signal_explanation",
    "crypto_market_research",
    "rebalance_suggestion",
]


class ReportGenerateRequest(BaseModel):
    report_type: ReportType
    data_snapshot_id: str
    input_facts: dict[str, Any] = Field(default_factory=dict)
    provider: Literal["mock", "openai", "deepseek", "configured"] = "mock"
    agent_name: str = "mock_research_agent"


class AIProviderStatusRead(BaseModel):
    default_provider: str
    external_calls_enabled: bool
    openai_configured: bool
    openai_model: str
    deepseek_configured: bool
    deepseek_model: str
    safe_mode: str
    limitations: list[str]


class ResearchReportRead(ORMModel):
    id: str
    report_id: str
    report_type: str
    agent_name: str
    data_snapshot_id: str
    asset_id: str | None
    input_facts: dict[str, Any]
    summary: str
    bullish_case: str | None
    bearish_case: str | None
    key_risks: dict[str, Any]
    suggested_action: str
    confidence: float
    evidence: dict[str, Any]
    limitations: str | None
    created_at: datetime


LEGACY_AUTOMATION_LEVEL_ALIASES = {
    "L0_READ_ONLY": "A0_READ_ONLY",
    "L1_RESEARCH": "A1_RESEARCH",
    "L2_ORDER_DRAFT": "A3_ORDER_DRAFT",
    "L3_HUMAN_APPROVAL": "A4_APPROVAL_EXECUTION",
}


AutomationLevel = Literal[
    "A0_READ_ONLY",
    "A1_RESEARCH",
    "A2_ALERT",
    "A3_ORDER_DRAFT",
    "A4_APPROVAL_EXECUTION",
    "A5_CONTROLLED_AUTO",
]


def normalize_automation_level(value: Any) -> Any:
    if isinstance(value, str):
        return LEGACY_AUTOMATION_LEVEL_ALIASES.get(value, value)
    return value


class AgentResearchRequest(BaseModel):
    data_snapshot_id: str
    asset_id: str | None = None
    portfolio_snapshot_id: str | None = None
    market_facts: dict[str, Any] = Field(default_factory=dict)
    positions: list[dict[str, Any]] = Field(default_factory=list)
    signals: list[dict[str, Any]] = Field(default_factory=list)
    prior_reports: list[dict[str, Any]] = Field(default_factory=list)
    automation_level: AutomationLevel = "A0_READ_ONLY"
    provider: Literal["mock"] = "mock"

    @field_validator("automation_level", mode="before")
    @classmethod
    def normalize_legacy_level(cls, value: Any) -> Any:
        return normalize_automation_level(value)


class AgentRunRead(ORMModel):
    id: str
    agent_name: str
    run_type: str
    status: str
    input_snapshot_id: str | None
    output_json: dict[str, Any]
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None


class AgentResearchResponse(BaseModel):
    final_report: ResearchReportRead
    agent_runs: list[AgentRunRead]
    order_intent_id: str | None = None


SignalDirection = Literal["bullish", "bearish", "neutral"]
SignalHorizon = Literal["intraday", "swing", "long_term"]
SignalSuggestedAction = Literal["watch", "hold", "reduce", "draft_buy", "draft_sell"]
SignalReviewStatus = Literal["needs_thesis_review", "ready_for_draft_review", "intent_created", "draft_in_progress"]


class CandleInput(BaseModel):
    close: float
    high: float | None = None
    low: float | None = None
    volume: float | None = None


class SignalGenerateRequest(BaseModel):
    asset_id: str
    candles: list[CandleInput] = Field(default_factory=list)
    signal_types: list[str] = Field(default_factory=lambda: ["rsi", "ma_cross"])
    horizon: SignalHorizon = "swing"
    market_facts: dict[str, Any] = Field(default_factory=dict)
    onchain_facts: dict[str, Any] = Field(default_factory=dict)


class SignalRead(ORMModel):
    id: str
    asset_id: str
    signal_type: str
    direction: SignalDirection
    strength: float = Field(ge=0, le=100)
    horizon: SignalHorizon
    evidence: dict[str, Any]
    invalidation_condition: str
    suggested_action: SignalSuggestedAction
    confidence: float = Field(ge=0, le=1)
    created_at: datetime


class SignalReviewQueueItemRead(BaseModel):
    signal_id: str
    asset_id: str
    asset_symbol: str
    asset_name: str
    signal_type: str
    direction: SignalDirection
    strength: float = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    suggested_action: SignalSuggestedAction
    horizon: SignalHorizon
    review_status: SignalReviewStatus
    priority: Literal["high", "medium", "low"]
    queue_reason: str
    next_action: str
    input_source: str | None = None
    input_timeframe: str | None = None
    input_candle_count: int = 0
    has_active_thesis: bool = False
    latest_thesis_id: str | None = None
    has_order_intent: bool = False
    latest_order_intent_id: str | None = None
    has_order_draft: bool = False
    latest_order_draft_id: str | None = None
    created_at: datetime


class SignalCreateOrderIntentRequest(BaseModel):
    account_id: str
    automation_level: AutomationLevel = "A0_READ_ONLY"
    signal_order_intents_enabled: bool = False
    quantity: float | None = None
    notional: float | None = None

    @field_validator("automation_level", mode="before")
    @classmethod
    def normalize_legacy_level(cls, value: Any) -> Any:
        return normalize_automation_level(value)


OrderMode = Literal["manual", "auto"]


class RiskCheckOrderRequest(BaseModel):
    model_config = {"allow_inf_nan": False}
    order_intent_id: str
    order_mode: OrderMode = "manual"
    max_order_notional: float = 10_000
    max_position_pct: float = 0.25
    total_equity: float = 100_000
    current_position_value: float = 0
    account_daily_loss: float = 0
    max_daily_loss: float = 1_000
    current_leverage: float = 0
    max_leverage: float = 1
    liquidity_passed: bool = True
    volatility: float = 0
    max_volatility: float = 1
    kill_switch: bool = False

    def risk_context(self) -> dict[str, Any]:
        return self.model_dump(exclude={"order_intent_id"})


class RiskCheckRead(ORMModel):
    id: str
    order_intent_id: str | None
    status: str
    hard_rule_passed: bool
    rules_json: dict[str, Any]
    reason: str | None
    created_at: datetime


GateType = Literal["RESEARCH_GATE", "THESIS_GATE", "RISK_GATE", "BEHAVIOR_GATE", "EXECUTION_GATE"]
GateStatus = Literal["PASSED", "WARNING", "HARD_CONFIRM_REQUIRED", "BLOCKED"]
InterventionLevel = Literal["SILENT_RECORD", "SOFT_WARNING", "HARD_CONFIRM", "BLOCK"]
V3AutomationLevel = Literal[
    "A0_READ_ONLY",
    "A1_RESEARCH",
    "A2_ALERT",
    "A3_ORDER_DRAFT",
    "A4_APPROVAL_EXECUTION",
    "A5_CONTROLLED_AUTO",
    "A6_ADAPTIVE_AUTO_FUTURE",
]
WorkflowLifecycleState = Literal[
    "IDEA_CREATED",
    "DATA_COLLECTED",
    "RESEARCH_GENERATED",
    "THESIS_CREATED_OR_MATCHED",
    "SIGNAL_DETECTED",
    "ORDER_INTENT_CREATED",
    "RESEARCH_GATE_PASSED",
    "THESIS_GATE_PASSED",
    "RISK_GATE_PASSED",
    "BEHAVIOR_GATE_PASSED",
    "EXECUTION_GATE_PASSED",
    "ORDER_DRAFT_CREATED",
    "USER_APPROVAL_REQUIRED",
    "APPROVED",
    "REJECTED",
    "MODIFIED",
    "PAPER_EXECUTED",
    "LIVE_EXECUTED",
    "EXECUTION_CONFIRMED",
    "JOURNAL_WRITTEN",
    "REVIEW_SCHEDULED",
    "POST_TRADE_REVIEWED",
    "PLAYBOOK_UPDATED",
    "BLOCKED",
]


class InvestmentConstitutionCreate(BaseModel):
    user_id: str
    version: str
    name: str
    investment_style: str
    allowed_markets: list[str] = Field(default_factory=list)
    forbidden_assets: list[str] = Field(default_factory=list)
    forbidden_actions: list[str] = Field(default_factory=list)
    max_single_position_pct: float
    max_asset_class_pct: float
    max_crypto_pct: float
    max_single_exchange_pct: float
    max_daily_loss_pct: float
    max_monthly_drawdown_pct: float
    leverage_allowed: bool = False
    derivatives_allowed: bool = False
    auto_execution_allowed: bool = False
    human_approval_required: bool = True
    cooldown_rules_json: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True


class InvestmentConstitutionRead(InvestmentConstitutionCreate, ORMModel):
    id: str
    created_at: datetime
    updated_at: datetime


class RiskBudgetCreate(BaseModel):
    user_id: str
    constitution_id: str
    account_id: str | None = None
    asset_class: str
    max_allocation_pct: float
    max_loss_pct: float
    max_order_notional: float
    max_leverage: float
    rebalance_threshold_pct: float


class RiskBudgetRead(RiskBudgetCreate, ORMModel):
    id: str
    created_at: datetime
    updated_at: datetime


class StrategyPlaybookCreate(BaseModel):
    user_id: str
    name: str
    strategy_type: str
    applicable_markets: list[str] = Field(default_factory=list)
    applicable_assets: list[str] = Field(default_factory=list)
    entry_conditions_json: dict[str, Any] = Field(default_factory=dict)
    exit_conditions_json: dict[str, Any] = Field(default_factory=dict)
    risk_rules_json: dict[str, Any] = Field(default_factory=dict)
    automation_level: V3AutomationLevel = "A1_RESEARCH"
    requires_human_approval: bool = True
    is_active: bool = True


class StrategyPlaybookRead(StrategyPlaybookCreate, ORMModel):
    id: str
    created_at: datetime
    updated_at: datetime


class StrategyRuleCreate(BaseModel):
    strategy_playbook_id: str
    rule_type: str
    priority: int = Field(default=5, ge=0, le=100)
    description: str
    conditions_json: dict[str, Any] = Field(default_factory=dict)
    actions_json: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def reject_inline_secrets(self) -> "StrategyRuleCreate":
        if contains_secret_config_key(self.conditions_json) or contains_secret_config_key(self.actions_json):
            raise ValueError("strategy rule payload must not contain inline secrets")
        return self


class StrategyRuleUpdate(BaseModel):
    rule_type: str | None = None
    priority: int | None = Field(default=None, ge=0, le=100)
    description: str | None = None
    conditions_json: dict[str, Any] | None = None
    actions_json: dict[str, Any] | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def reject_inline_secrets(self) -> "StrategyRuleUpdate":
        if contains_secret_config_key(self.conditions_json or {}) or contains_secret_config_key(self.actions_json or {}):
            raise ValueError("strategy rule payload must not contain inline secrets")
        return self


class StrategyRuleRead(ORMModel):
    id: str
    strategy_playbook_id: str
    rule_type: str
    priority: int
    description: str
    conditions_json: dict[str, Any]
    actions_json: dict[str, Any]
    is_active: bool
    created_at: datetime
    updated_at: datetime


class BacktestRunCreate(BaseModel):
    user_id: str = "default-user"
    strategy_playbook_id: str
    name: str
    date_from: date
    date_to: date
    initial_capital: float = Field(gt=0)
    parameters_json: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_backtest_request(self) -> "BacktestRunCreate":
        if self.date_to < self.date_from:
            raise ValueError("date_to must be greater than or equal to date_from")
        if contains_secret_config_key(self.parameters_json):
            raise ValueError("parameters_json must not contain inline secrets")
        return self


class BacktestRunRead(ORMModel):
    id: str
    user_id: str
    strategy_playbook_id: str
    name: str
    date_from: date
    date_to: date
    initial_capital: float
    status: str
    parameters_json: dict[str, Any]
    results_json: dict[str, Any]
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class InvestmentThesisCreate(BaseModel):
    user_id: str
    asset_id: str
    account_id: str | None = None
    position_id: str | None = None
    strategy_playbook_id: str | None = None
    data_snapshot_id: str | None = None
    entry_reason: str
    key_drivers_json: dict[str, Any] = Field(default_factory=dict)
    invalidation_conditions_json: dict[str, Any] = Field(default_factory=dict)
    expected_horizon: str
    target_condition: str
    max_loss_tolerance_pct: float
    position_plan_json: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(ge=0, le=1)
    source: str
    status: str = "active"


class InvestmentThesisRead(InvestmentThesisCreate, ORMModel):
    id: str
    created_at: datetime
    updated_at: datetime


class ThesisCheckpointCreate(BaseModel):
    thesis_id: str
    data_snapshot_id: str | None = None
    checkpoint_type: str
    observed_facts_json: dict[str, Any] = Field(default_factory=dict)
    supports_thesis: bool = False
    weakens_thesis: bool = False
    invalidates_thesis: bool = False
    ai_summary: str | None = None
    confidence: float = Field(default=0, ge=0, le=1)


class ThesisCheckpointRead(ThesisCheckpointCreate, ORMModel):
    id: str
    created_at: datetime


class ThesisViolationCreate(BaseModel):
    thesis_id: str
    user_id: str
    related_order_intent_id: str | None = None
    violation_type: str
    prior_user_statement: str
    current_action: str
    explanation: str
    intervention_level: InterventionLevel
    resolved_status: str = "open"


class ThesisViolationRead(ThesisViolationCreate, ORMModel):
    id: str
    created_at: datetime


class ThesisEventCreate(BaseModel):
    thesis_id: str
    event_type: str
    title: str
    description: str = ""
    source: str = "manual_workspace"
    event_time: datetime | None = None
    impact_json: dict[str, Any] = Field(default_factory=dict)


class ThesisEventRead(ThesisEventCreate):
    id: str
    event_time: datetime


class ThesisContextPositionRead(BaseModel):
    id: str
    account_id: str
    asset_id: str
    quantity: float
    market_value: float
    unrealized_pnl: float


class ThesisContextIntentRead(BaseModel):
    id: str
    side: str
    status: str
    created_at: datetime


class ThesisContextDraftRead(BaseModel):
    id: str
    order_intent_id: str
    approval_status: str
    execution_status: str
    created_at: datetime


class ThesisContextReviewRead(BaseModel):
    id: str
    order_draft_id: str
    status: str
    created_at: datetime
    updated_at: datetime


class ThesisContextProposalRead(BaseModel):
    id: str
    strategy_playbook_id: str | None = None
    status: str
    rationale: str
    reviewed_at: datetime | None = None
    created_at: datetime


class ThesisContextRead(BaseModel):
    thesis_id: str
    health_status: Literal["healthy", "needs_review", "violated", "invalidated"]
    summary: str
    latest_checkpoint: ThesisCheckpointRead | None = None
    open_violation_count: int = 0
    linked_positions: list[ThesisContextPositionRead] = Field(default_factory=list)
    linked_order_intents: list[ThesisContextIntentRead] = Field(default_factory=list)
    linked_order_drafts: list[ThesisContextDraftRead] = Field(default_factory=list)
    linked_post_trade_reviews: list[ThesisContextReviewRead] = Field(default_factory=list)
    linked_playbook_proposals: list[ThesisContextProposalRead] = Field(default_factory=list)
    recent_events: list[ThesisEventRead] = Field(default_factory=list)


ThesisAIProvider = Literal["mock", "openai", "deepseek", "configured"]
ThesisCheckpointStatus = Literal["SUPPORTS_THESIS", "WEAKENS_THESIS", "INVALIDATES_THESIS", "DATA_INSUFFICIENT"]


class ThesisCaptureRequest(BaseModel):
    user_id: str
    asset_id: str
    account_id: str | None = None
    position_id: str | None = None
    strategy_playbook_id: str | None = None
    data_snapshot_id: str
    user_rationale: str
    intended_action: str
    current_position: dict[str, Any] = Field(default_factory=dict)
    market_context: dict[str, Any] = Field(default_factory=dict)
    provider: ThesisAIProvider = "mock"


class ThesisMonitorRequest(BaseModel):
    data_snapshot_id: str
    new_facts: dict[str, Any] = Field(default_factory=dict)
    news: list[dict[str, Any]] = Field(default_factory=list)
    price_movement: dict[str, Any] = Field(default_factory=dict)
    earnings_data: dict[str, Any] = Field(default_factory=dict)
    technical_signals: list[dict[str, Any]] = Field(default_factory=list)
    onchain_signals: list[dict[str, Any]] = Field(default_factory=list)
    provider: ThesisAIProvider = "mock"


class ThesisViolationMessageRequest(BaseModel):
    user_id: str
    current_action: str
    related_order_intent_id: str | None = None
    prior_user_statement: str | None = None
    intervention_level: InterventionLevel = "HARD_CONFIRM"
    provider: ThesisAIProvider = "mock"


class ThesisViolationMessageResponse(BaseModel):
    violation: ThesisViolationRead
    message: str
    intervention_level: InterventionLevel


class DecisionGateCreate(BaseModel):
    order_intent_id: str | None = None
    gate_type: GateType
    status: GateStatus
    score: float | None = Field(default=None, ge=0, le=1)
    blocking_reasons_json: list[str] = Field(default_factory=list)
    warnings_json: list[str] = Field(default_factory=list)
    evidence_json: dict[str, Any] = Field(default_factory=dict)
    recommended_intervention_level: InterventionLevel = "SILENT_RECORD"
    evaluator: str


class DecisionGateRead(DecisionGateCreate, ORMModel):
    id: str
    created_at: datetime


class DecisionGateEvaluateRequest(BaseModel):
    model_config = {"allow_inf_nan": False}
    order_intent_id: str
    user_id: str | None = None
    data_snapshot_id: str | None = None
    data_quality_status: str = "acceptable"
    quality_report_required: bool = True
    min_data_quality_score: float = Field(default=0.75, ge=0, le=1)
    research_report_required: bool = True
    min_research_confidence: float = Field(default=0.5, ge=0, le=1)
    hallucination_flags: list[str] = Field(default_factory=list)
    thesis_conflict: bool = False
    thesis_invalidation_triggered: bool = False
    prior_user_statement: str | None = None
    current_action: str | None = None
    thesis_conflict_explanation: str | None = None
    max_single_position_pct: float | None = None
    max_asset_class_pct: float | None = None
    max_crypto_pct: float | None = None
    max_single_exchange_pct: float | None = None
    max_daily_loss_pct: float | None = None
    max_monthly_drawdown_pct: float | None = None
    current_position_pct: float = 0
    order_position_pct: float = 0
    asset_class_pct: float = 0
    crypto_pct: float = 0
    exchange_pct: float = 0
    daily_loss_pct: float = 0
    monthly_drawdown_pct: float = 0
    current_leverage: float = 0
    behavior_flags: list[str] = Field(default_factory=list)
    latest_quote_required: bool = True
    max_quote_age_seconds: int = 900
    source_timestamp_valid: bool = True
    broker_status: str = "healthy"
    exchange_status: str = "healthy"
    expected_slippage_pct: float = 0
    max_slippage_pct: float = 0.01
    order_size_executable: bool = True
    execution_mode: str = "paper"
    action: str = "CREATE_ORDER_DRAFT"


class DecisionGateEvaluateResponse(BaseModel):
    order_intent_id: str
    gates: list[DecisionGateRead]
    all_passed: bool


class BehaviorPatternCreate(BaseModel):
    user_id: str
    pattern_type: str
    asset_id: str | None = None
    description: str
    evidence_json: dict[str, Any] = Field(default_factory=dict)
    estimated_cost: float = 0
    frequency: int = 0
    severity: str


class BehaviorPatternRead(BehaviorPatternCreate, ORMModel):
    id: str
    created_at: datetime
    updated_at: datetime


class BehaviorInterventionCreate(BaseModel):
    user_id: str
    pattern_id: str | None = None
    order_intent_id: str | None = None
    intervention_level: InterventionLevel
    message: str
    user_response: str | None = None
    bypassed: bool = False


class BehaviorInterventionRead(BehaviorInterventionCreate, ORMModel):
    id: str
    created_at: datetime


BehaviorPatternType = Literal[
    "FOMO_BUYING",
    "PANIC_SELLING",
    "OVERTRADING",
    "REVENGE_TRADING",
    "AVERAGING_DOWN_AFTER_LOSSES",
    "SELLING_WINNERS_TOO_EARLY",
    "HOLDING_LOSERS_TOO_LONG",
    "CONCENTRATION_DRIFT",
    "THESIS_CONFLICT_TRADE",
    "SOCIAL_MEDIA_TRIGGERED_TRADE",
]


class BehaviorEvaluateOrderRequest(BaseModel):
    order_intent_id: str
    user_id: str | None = None
    trade_history: list[dict[str, Any]] = Field(default_factory=list)
    position_history: dict[str, Any] = Field(default_factory=dict)
    market_move: dict[str, Any] = Field(default_factory=dict)
    recent_losses: dict[str, Any] = Field(default_factory=dict)
    prior_behavior_patterns: list[dict[str, Any]] = Field(default_factory=list)
    behavior_flags: list[BehaviorPatternType] = Field(default_factory=list)
    projected_position_pct: float = 0
    order_position_pct: float = 0
    max_single_position_pct: float | None = None
    thesis_conflict: bool = False
    thesis_invalidation_triggered: bool = False
    prior_user_statement: str | None = None
    current_action: str | None = None
    thesis_conflict_explanation: str | None = None
    trigger_source: str | None = None


class BehaviorInterventionDetailRead(BehaviorInterventionRead):
    evidence: dict[str, Any] = Field(default_factory=dict)
    required_user_action: str
    bypass_allowed: bool


class BehaviorProfileRead(BaseModel):
    user_id: str
    total_patterns: int
    total_interventions: int
    bypassed_interventions: int
    block_interventions: int
    top_patterns: list[dict[str, Any]] = Field(default_factory=list)
    recurring_patterns: list[dict[str, Any]] = Field(default_factory=list)
    repeat_offenders: list[dict[str, Any]] = Field(default_factory=list)
    current_baseline: dict[str, Any] = Field(default_factory=dict)
    summary: str


class BehaviorEvaluateOrderResponse(BaseModel):
    order_intent_id: str
    level: InterventionLevel
    message: str
    evidence: dict[str, Any]
    required_user_action: str
    bypass_allowed: bool
    intervention: BehaviorInterventionRead
    patterns: list[BehaviorPatternRead]
    thesis_violation: ThesisViolationRead | None = None


class BehaviorInterventionRespondRequest(BaseModel):
    user_response: str
    bypassed: bool = False


class AutomationPolicyCreate(BaseModel):
    user_id: str
    account_id: str | None = None
    asset_id: str | None = None
    strategy_playbook_id: str | None = None
    automation_level: V3AutomationLevel = "A0_READ_ONLY"
    max_notional_per_order: float = 0
    max_orders_per_day: int = 0
    requires_approval: bool = True
    allowed_actions: list[str] = Field(default_factory=list)
    forbidden_actions: list[str] = Field(default_factory=list)
    is_active: bool = True


class AutomationPolicyRead(AutomationPolicyCreate, ORMModel):
    id: str
    created_at: datetime
    updated_at: datetime


class AutomationPolicyEffectiveRequest(BaseModel):
    user_id: str
    account_id: str | None = None
    asset_id: str | None = None
    strategy_playbook_id: str | None = None


class AutomationPolicyEffectiveRead(BaseModel):
    id: str | None = None
    user_id: str
    account_id: str | None = None
    asset_id: str | None = None
    strategy_playbook_id: str | None = None
    automation_level: str
    max_notional_per_order: float = 0
    max_orders_per_day: int = 0
    requires_approval: bool = True
    allowed_actions: list[str] = Field(default_factory=list)
    forbidden_actions: list[str] = Field(default_factory=list)
    is_active: bool = True
    source: str


class AutomationPolicyEvaluateRequest(AutomationPolicyEffectiveRequest):
    action: str = "CREATE_ORDER_INTENT"
    order_notional: float = 0
    gates_passed: bool = False
    risk_budget_passed: bool = False
    human_approved: bool = False
    live_trading_enabled: bool = False


class AutomationPolicyEvaluateResponse(BaseModel):
    policy: AutomationPolicyEffectiveRead
    action: str
    can_create_order_intent: bool
    can_create_order_draft: bool
    requires_human_approval: bool
    can_execute_paper: bool
    can_execute_live: bool
    can_execute_controlled_auto: bool
    blocking_reasons: list[str] = Field(default_factory=list)


CommandIntent = Literal[
    "portfolio_summary",
    "position_lookup",
    "risk_exposure",
    "thesis_review",
    "thesis_capture",
    "market_news_summary",
    "signal_lookup",
    "behavior_pattern_review",
    "monthly_decision_review",
    "order_draft_lookup",
    "scenario_analysis",
    "rejected_execution_request",
]


class CommandRunRequest(BaseModel):
    user_id: str
    raw_query: str
    data_snapshot_id: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)
    allow_order_intent: bool = False
    account_id: str | None = None
    asset_id: str | None = None
    strategy_playbook_id: str | None = None
    side: str | None = None
    quantity: float | None = None
    notional: float | None = None
    user_rationale: str | None = None


class CommandQueryRead(ORMModel):
    id: str
    user_id: str
    raw_query: str
    detected_intent: str
    required_tools: list[str]
    status: str
    created_at: datetime


class CommandToolCallRead(ORMModel):
    id: str
    command_query_id: str
    tool_name: str
    input_json: dict[str, Any]
    output_json: dict[str, Any]
    status: str
    created_at: datetime


class CommandResultRead(ORMModel):
    id: str
    command_query_id: str
    summary: str
    structured_result_json: dict[str, Any]
    data_sources_json: dict[str, Any]
    created_at: datetime


class WorkflowStateCreate(BaseModel):
    workflow_type: str
    entity_id: str
    current_state: WorkflowLifecycleState
    previous_state: WorkflowLifecycleState | None = None
    transition_reason: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class WorkflowStateRead(WorkflowStateCreate, ORMModel):
    id: str
    created_at: datetime
    updated_at: datetime


class WorkflowCreateRequest(BaseModel):
    entity_type: str
    entity_id: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkflowTransitionRequest(BaseModel):
    next_state: WorkflowLifecycleState
    reason: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkflowBlockRequest(BaseModel):
    reason: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class MonthlyDecisionReviewCreate(BaseModel):
    user_id: str
    period_start: date
    period_end: date
    total_trades: int = 0
    thesis_aligned_trades: int = 0
    thesis_violating_trades: int = 0
    impulsive_trades: int = 0
    blocked_trades: int = 0
    bypassed_warnings: int = 0
    planned_trade_pnl: float = 0
    impulsive_trade_pnl: float = 0
    overtrading_cost: float = 0
    top_behavior_patterns_json: list[dict[str, Any]] = Field(default_factory=list)
    recommended_rule_updates_json: list[dict[str, Any]] = Field(default_factory=list)
    ai_summary: str | None = None


class MonthlyDecisionReviewRead(MonthlyDecisionReviewCreate, ORMModel):
    id: str
    created_at: datetime


MonthlyReviewProvider = Literal["mock"]


class MonthlyReviewGenerateRequest(BaseModel):
    user_id: str
    period_start: date
    period_end: date
    provider: MonthlyReviewProvider = "mock"


class MonthlyReviewGenerateResponse(BaseModel):
    review: MonthlyDecisionReviewRead
    metrics: dict[str, Any]
    behavior_summary: str
    decision_quality_summary: str
    recommended_constitution_updates: list[dict[str, Any]] = Field(default_factory=list)
    recommended_playbook_updates: list[dict[str, Any]] = Field(default_factory=list)
    most_common_behavior_pattern: str | None = None
    biggest_prevented_loss: float = 0
    automatic_rule_updates_applied: bool = False


class ChainCreate(BaseModel):
    name: str
    chain_id: str
    native_symbol: str
    explorer_url: str | None = None
    is_active: bool = True


class ChainRead(ChainCreate, ORMModel):
    id: str
    created_at: datetime
    updated_at: datetime


class WalletCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str
    address: str
    chain: str
    label: str | None = None


class WalletRead(WalletCreate, ORMModel):
    id: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class TokenBalanceCreate(BaseModel):
    wallet_id: str
    chain: str
    token: str
    symbol: str
    token_address: str | None = None
    balance: float = 0
    usd_price: float = 0
    usd_value: float = 0
    source: str = "mock_read_only"


class TokenBalanceRead(TokenBalanceCreate, ORMModel):
    id: str
    as_of: datetime


class TokenAllowanceCreate(BaseModel):
    wallet_id: str
    chain: str
    token: str
    symbol: str
    token_address: str | None = None
    spender: str
    amount: float = 0
    usd_value: float = 0
    risk_level: str = "low"
    source: str = "mock_read_only"


class TokenAllowanceRead(TokenAllowanceCreate, ORMModel):
    id: str
    as_of: datetime


class WalletTransferCreate(BaseModel):
    wallet_id: str
    chain: str
    tx_hash: str
    from_address: str
    to_address: str
    token: str
    symbol: str
    amount: float = 0
    usd_value: float = 0
    direction: str
    is_known_contract: bool = True
    timestamp: datetime | None = None


class WalletTransferRead(WalletTransferCreate, ORMModel):
    id: str


class ProtocolPositionCreate(BaseModel):
    wallet_id: str
    chain: str
    protocol_name: str
    position_type: str
    asset_symbol: str
    usd_value: float = 0
    risk_json: dict[str, Any] = Field(default_factory=dict)


class ProtocolPositionRead(ProtocolPositionCreate, ORMModel):
    id: str
    as_of: datetime


class ExchangeExposureCreate(BaseModel):
    user_id: str
    exchange_name: str
    asset_symbol: str
    usd_value: float = 0
    exposure_pct: float = 0
    source: str = "manual_read_only"


class ExchangeExposureRead(ExchangeExposureCreate, ORMModel):
    id: str
    created_at: datetime
    updated_at: datetime


class StablecoinExposureCreate(BaseModel):
    user_id: str
    wallet_id: str | None = None
    chain: str
    symbol: str
    issuer: str | None = None
    amount: float = 0
    usd_value: float = 0
    reference_price: float = 1
    depeg_risk_score: float = 0


class StablecoinExposureRead(StablecoinExposureCreate, ORMModel):
    id: str
    as_of: datetime


class OnchainRiskAlertCreate(BaseModel):
    user_id: str
    wallet_id: str | None = None
    alert_type: str
    severity: str
    description: str
    evidence_json: dict[str, Any] = Field(default_factory=dict)
    resolved: bool = False


class OnchainRiskAlertRead(OnchainRiskAlertCreate, ORMModel):
    id: str
    created_at: datetime
    resolved_at: datetime | None = None


class Web3BalanceInput(BaseModel):
    token: str
    symbol: str
    balance: float = 0
    usd_price: float = 0
    usd_value: float = 0
    token_address: str | None = None
    reference_price: float | None = None


class Web3AllowanceInput(BaseModel):
    token: str
    symbol: str
    spender: str
    amount: float = 0
    usd_value: float = 0
    token_address: str | None = None


class Web3TransferInput(BaseModel):
    tx_hash: str
    from_address: str
    to_address: str
    token: str
    symbol: str
    amount: float = 0
    usd_value: float = 0
    direction: str = "outgoing"
    is_known_contract: bool = True
    timestamp: datetime | None = None


class Web3ProtocolPositionInput(BaseModel):
    protocol_name: str
    position_type: str
    asset_symbol: str
    usd_value: float = 0
    risk_json: dict[str, Any] = Field(default_factory=dict)


class Web3ExchangeExposureInput(BaseModel):
    exchange_name: str
    asset_symbol: str
    usd_value: float = 0
    exposure_pct: float = 0


class Web3RiskScanRequest(BaseModel):
    user_id: str | None = None
    wallet_id: str | None = None
    balances: list[Web3BalanceInput] = Field(default_factory=list)
    allowances: list[Web3AllowanceInput] = Field(default_factory=list)
    transfers: list[Web3TransferInput] = Field(default_factory=list)
    protocol_positions: list[Web3ProtocolPositionInput] = Field(default_factory=list)
    exchange_exposures: list[Web3ExchangeExposureInput] = Field(default_factory=list)
    max_exchange_exposure_pct: float = 0.25
    max_allowance_usd: float = 10_000
    stablecoin_depeg_threshold: float = 0.02
    large_transfer_usd: float = 50_000


class Web3RiskScanResponse(BaseModel):
    wallet_id: str | None = None
    alerts_created: int
    balances_imported: int
    allowances_imported: int
    transfers_imported: int
    protocol_positions_imported: int
    exchange_exposures_imported: int
    stablecoin_exposures: list[StablecoinExposureRead] = Field(default_factory=list)
    alerts: list[OnchainRiskAlertRead] = Field(default_factory=list)
    signing_available: bool = False
    execution_available: bool = False


class Web3WalletDetailRead(WalletRead):
    balances: list[TokenBalanceRead] = Field(default_factory=list)
    transfers: list[WalletTransferRead] = Field(default_factory=list)
    allowances: list[TokenAllowanceRead] = Field(default_factory=list)
    risk_alerts: list[OnchainRiskAlertRead] = Field(default_factory=list)


class OnchainRiskAlertResolveRequest(BaseModel):
    resolved: bool = True


class OrderIntentCreate(BaseModel):
    source_type: str
    source_id: str | None = None
    asset_id: str
    account_id: str
    investment_thesis_id: str | None = None
    strategy_playbook_id: str | None = None
    automation_policy_id: str | None = None
    source_signal_id: str | None = None
    side: str
    order_type: str
    quantity: float | None = None
    notional: float | None = None
    limit_price: float | None = None
    rationale: str
    user_rationale: str | None = None
    evidence_json: dict[str, Any] = Field(default_factory=dict)
    status: str = "created"


class OrderIntentRead(OrderIntentCreate, ORMModel):
    id: str
    created_at: datetime


class CommandRunResponse(BaseModel):
    query: CommandQueryRead
    tool_calls: list[CommandToolCallRead]
    result: CommandResultRead
    order_intent: OrderIntentRead | None = None


class OrderDraftCreate(BaseModel):
    order_intent_id: str
    risk_status: str = "pending"
    behavior_status: str = "pending"
    decision_gate_results: dict[str, Any] = Field(default_factory=dict)
    approval_policy: dict[str, Any] = Field(default_factory=dict)
    approval_status: str = "not_requested"
    execution_status: str = "not_executable"


class OrderDraftRead(OrderDraftCreate, ORMModel):
    id: str
    created_at: datetime


class DecisionNarrativeSectionRead(BaseModel):
    key: str
    title: str
    status: str
    summary: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    next_action: str | None = None


class DecisionNarrativeEventRead(BaseModel):
    id: str
    label: str
    status: str
    detail: str
    created_at: datetime


class DecisionNarrativeRead(BaseModel):
    draft_id: str
    order_intent_id: str
    asset_id: str
    asset_symbol: str | None = None
    account_id: str
    thesis_id: str | None = None
    thesis_link_kind: Literal["explicit", "candidate_latest_active", "missing"]
    signal_id: str | None = None
    strategy_playbook_id: str | None = None
    current_stage: str
    sections: list[DecisionNarrativeSectionRead] = Field(default_factory=list)
    timeline: list[DecisionNarrativeEventRead] = Field(default_factory=list)
    safety_flags: dict[str, Any] = Field(default_factory=dict)
    next_actions: list[str] = Field(default_factory=list)


class ApprovalDecisionRequest(BaseModel):
    approver_id: str | None = None
    decision_reason: str | None = None


class DraftModifyRequest(BaseModel):
    decision_reason: str | None = None


class ApprovalRead(ORMModel):
    id: str
    order_draft_id: str
    status: str
    approver_id: str | None
    decision_reason: str | None
    created_at: datetime
    decided_at: datetime | None


class PaperExecutionRequest(BaseModel):
    model_config = {'allow_inf_nan': False}
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=128, pattern=r'^[A-Za-z0-9_.:-]+$')
    approver_id: str | None = None
    decision_reason: str | None = None
    fill_price: float | None = None
    fill_quantity: float | None = None
    fee_bps: float = 1.0
    slippage_bps: float = 0.0


class PaperCashDividendRequest(BaseModel):
    account_id: str
    asset_id: str
    amount_per_share: float
    effective_at: datetime | None = None
    note: str | None = None


class PaperStockSplitRequest(BaseModel):
    account_id: str
    asset_id: str
    ratio_numerator: float
    ratio_denominator: float = 1.0
    effective_at: datetime | None = None
    note: str | None = None


class ExecutionRead(ORMModel):
    fill_sequence: int | None = None
    idempotency_key: str | None = None
    id: str
    order_draft_id: str
    position_id: str | None
    execution_mode: str
    status: str
    filled_quantity: float
    average_fill_price: float | None
    fill_notional: float
    fee_amount: float
    slippage_amount: float
    cash_effect: float
    requested_quantity: float = 0
    cumulative_filled_quantity: float = 0
    remaining_quantity: float = 0
    proceeds_amount: float = 0
    cost_basis_amount: float = 0
    realized_pnl: float = 0
    created_at: datetime


class PaperTaxLotRead(ORMModel):
    id: str
    account_id: str
    asset_id: str
    source_execution_id: str | None
    opened_order_draft_id: str | None
    status: str
    quantity_opened: float
    quantity_remaining: float
    average_cost: float
    cost_basis_remaining: float
    opened_at: datetime
    closed_at: datetime | None
    metadata_json: dict[str, Any]


class PaperTaxLotRealizationRead(ORMModel):
    id: str
    execution_id: str
    tax_lot_id: str
    quantity: float
    proceeds_amount: float
    cost_basis_amount: float
    fee_allocated: float
    realized_pnl: float
    created_at: datetime


class PaperCorporateActionRead(ORMModel):
    id: str
    account_id: str
    asset_id: str
    action_type: str
    effective_at: datetime
    quantity_before: float
    quantity_after: float
    cash_effect: float
    ratio: float | None
    amount_per_share: float | None
    status: str
    metadata_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class TradeJournalEntryRead(ORMModel):
    id: str
    asset_id: str | None
    account_id: str | None
    title: str
    notes: str
    tags_json: list
    created_at: datetime


class PaperCorporateActionResponse(BaseModel):
    corporate_action: PaperCorporateActionRead
    journal_entry: TradeJournalEntryRead


class PostTradeReviewRead(ORMModel):
    id: str
    execution_id: str
    trade_journal_entry_id: str
    order_draft_id: str
    user_id: str
    status: str
    prompt_json: dict[str, Any]
    review_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class PostTradeReviewUpdate(BaseModel):
    status: str | None = None
    review_json: dict[str, Any] | None = None


class PlaybookProposalDecisionRequest(BaseModel):
    reviewer_id: str | None = None
    decision_reason: str | None = None


class PlaybookProposalApplyRequest(BaseModel):
    reviewer_id: str | None = None
    decision_reason: str | None = None
    target_strategy_playbook_id: str | None = None
    edited_rule_json: dict[str, Any] | None = None


class PlaybookProposalPublishRequest(BaseModel):
    reviewer_id: str | None = None
    decision_reason: str | None = None
    publish_note: str | None = None


class PlaybookUpdateProposalRead(ORMModel):
    id: str
    user_id: str
    source_type: str
    source_id: str
    strategy_playbook_id: str | None
    proposal_json: dict[str, Any]
    rationale: str
    status: str
    requires_user_approval: bool
    reviewed_by: str | None
    reviewed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class PlaybookProposalApplyResponse(BaseModel):
    proposal: PlaybookUpdateProposalRead
    playbook: StrategyPlaybookRead
    patch_json: dict[str, Any]
    auto_applied: bool = False


class PlaybookProposalPublishResponse(BaseModel):
    proposal: PlaybookUpdateProposalRead
    previous_playbook: StrategyPlaybookRead
    published_playbook: StrategyPlaybookRead
    publish_metadata: dict[str, Any]


class PaperExecutionResponse(BaseModel):
    replayed: bool = False
    execution: ExecutionRead
    journal_entry: TradeJournalEntryRead
    post_trade_review: PostTradeReviewRead
    order_draft: OrderDraftRead
    tax_lots: list[PaperTaxLotRead] = Field(default_factory=list)
    tax_lot_realizations: list[PaperTaxLotRealizationRead] = Field(default_factory=list)


class AuditLogRead(ORMModel):
    id: str
    actor_type: str
    actor_id: str
    action: str
    entity_type: str
    entity_id: str
    payload_json: dict
    created_at: datetime


class ManualPaperEvidenceRead(BaseModel):
    order_intent_id: str
    data_snapshot_id: str
    quote_id: str
    price: float
    quote_source: str
    quote_as_of: datetime
    expires_at: datetime
    evidence_mode: Literal['manual_paper_quote']
