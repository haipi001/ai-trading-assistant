import uuid
from datetime import datetime
from datetime import date
from datetime import timezone

from sqlalchemy import Boolean
from sqlalchemy import Date
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import Index
from sqlalchemy import Integer
from sqlalchemy import JSON
from sqlalchemy import Numeric
from sqlalchemy import String
from sqlalchemy import Text
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def uuid_str() -> str:
    return str(uuid.uuid4())


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


class TenantOwnedMixin:
    user_id: Mapped[str] = mapped_column(String(128), default="default-user", nullable=False, index=True)


class Asset(Base, TimestampMixin):
    __tablename__ = "assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(32), nullable=False)
    market: Mapped[str] = mapped_column(String(64), nullable=False)
    venue: Mapped[str] = mapped_column(String(64), nullable=False)
    currency: Mapped[str] = mapped_column(String(16), nullable=False)
    chain_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    contract_address: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tradable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    manual_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    auto_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(32), default="medium", nullable=False)
    sector: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    industry: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    themes_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    factor_tags_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    classification_source: Mapped[str | None] = mapped_column(String(128), nullable=True)
    classification_snapshot_id: Mapped[str | None] = mapped_column(ForeignKey("data_snapshots.id"), nullable=True, index=True)


class Account(Base, TimestampMixin, TenantOwnedMixin):
    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    account_type: Mapped[str] = mapped_column(String(64), nullable=False)
    broker: Mapped[str] = mapped_column(String(128), nullable=False)
    base_currency: Mapped[str] = mapped_column(String(16), nullable=False)
    mode: Mapped[str] = mapped_column(String(32), default="read_only", nullable=False)
    live_trading_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Position(Base, TenantOwnedMixin):
    __tablename__ = "positions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), nullable=False, index=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), nullable=False, index=True)
    quantity: Mapped[float] = mapped_column(Numeric(28, 10), nullable=False)
    average_cost: Mapped[float] = mapped_column(Numeric(28, 10), default=0, nullable=False)
    market_price: Mapped[float] = mapped_column(Numeric(28, 10), default=0, nullable=False)
    market_value: Mapped[float] = mapped_column(Numeric(28, 10), default=0, nullable=False)
    unrealized_pnl: Mapped[float] = mapped_column(Numeric(28, 10), default=0, nullable=False)
    realized_pnl: Mapped[float] = mapped_column(Numeric(28, 10), default=0, nullable=False)
    weight: Mapped[float] = mapped_column(Numeric(18, 10), default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class Quote(Base):
    __tablename__ = "quotes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), nullable=False, index=True)
    price: Mapped[float] = mapped_column(Numeric(28, 10), nullable=False)
    bid: Mapped[float | None] = mapped_column(Numeric(28, 10), nullable=True)
    ask: Mapped[float | None] = mapped_column(Numeric(28, 10), nullable=True)
    source: Mapped[str] = mapped_column(String(128), default="manual", nullable=False)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class Candle(Base):
    __tablename__ = "candles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), nullable=False, index=True)
    timeframe: Mapped[str] = mapped_column(String(32), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    open: Mapped[float] = mapped_column(Numeric(28, 10), nullable=False)
    high: Mapped[float] = mapped_column(Numeric(28, 10), nullable=False)
    low: Mapped[float] = mapped_column(Numeric(28, 10), nullable=False)
    close: Mapped[float] = mapped_column(Numeric(28, 10), nullable=False)
    volume: Mapped[float] = mapped_column(Numeric(28, 10), default=0, nullable=False)
    source: Mapped[str] = mapped_column(String(128), default="manual", nullable=False)

    __table_args__ = (Index("ix_candles_asset_timeframe_timestamp", "asset_id", "timeframe", "timestamp"),)


class DataSourceConnection(Base, TimestampMixin, TenantOwnedMixin):
    __tablename__ = "data_source_connections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(64), default="market_data", nullable=False)
    mode: Mapped[str] = mapped_column(String(32), default="read_only", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="configured", nullable=False)
    base_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    credentials_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    config_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    capabilities_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    last_health_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_health_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class DataSnapshot(Base, TenantOwnedMixin):
    __tablename__ = "data_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    snapshot_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    data_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class DataQualityReport(Base, TenantOwnedMixin):
    __tablename__ = "data_quality_reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    data_snapshot_id: Mapped[str | None] = mapped_column(ForeignKey("data_snapshots.id"), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    metric_type: Mapped[str] = mapped_column(String(64), nullable=False)
    score: Mapped[float] = mapped_column(Numeric(8, 6), default=0, nullable=False)
    details_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class DataCatalogEntry(Base, TenantOwnedMixin):
    __tablename__ = "data_catalog_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    dataset_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    source_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    data_snapshot_id: Mapped[str | None] = mapped_column(ForeignKey("data_snapshots.id"), nullable=True, index=True)
    quality_report_id: Mapped[str | None] = mapped_column(ForeignKey("data_quality_reports.id"), nullable=True, index=True)
    row_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    quality_status: Mapped[str] = mapped_column(String(32), default="UNKNOWN", nullable=False, index=True)
    usable_for_trading: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    lineage_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    contract_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class InvestmentLedgerEntry(Base):
    __tablename__ = "investment_ledger_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(String(128), default="default-user", nullable=False, index=True)
    account_id: Mapped[str | None] = mapped_column(ForeignKey("accounts.id"), nullable=True, index=True)
    asset_id: Mapped[str | None] = mapped_column(ForeignKey("assets.id"), nullable=True, index=True)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    entry_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    side: Mapped[str | None] = mapped_column(String(16), nullable=True)
    quantity_delta: Mapped[float] = mapped_column(Numeric(28, 10), default=0, nullable=False)
    cash_delta: Mapped[float] = mapped_column(Numeric(28, 10), default=0, nullable=False)
    price: Mapped[float | None] = mapped_column(Numeric(28, 10), nullable=True)
    fee_amount: Mapped[float] = mapped_column(Numeric(28, 10), default=0, nullable=False)
    realized_pnl: Mapped[float] = mapped_column(Numeric(28, 10), default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(16), default="USD", nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default="posted", nullable=False, index=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    __table_args__ = (
        Index("ix_investment_ledger_source", "source_type", "source_id", "entry_type"),
        Index("ix_investment_ledger_account_asset", "account_id", "asset_id"),
    )


class ReconciliationRun(Base):
    __tablename__ = "reconciliation_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(String(128), default="default-user", nullable=False, index=True)
    scope: Mapped[str] = mapped_column(String(64), default="portfolio", nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default="ok", nullable=False, index=True)
    source_snapshot_id: Mapped[str | None] = mapped_column(ForeignKey("data_snapshots.id"), nullable=True, index=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    positions_checked: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ledger_entries_checked: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    breaks_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    summary_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    execution_available: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class ReconciliationBreak(Base, TenantOwnedMixin):
    __tablename__ = "reconciliation_breaks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    reconciliation_run_id: Mapped[str] = mapped_column(ForeignKey("reconciliation_runs.id"), nullable=False, index=True)
    account_id: Mapped[str | None] = mapped_column(ForeignKey("accounts.id"), nullable=True, index=True)
    asset_id: Mapped[str | None] = mapped_column(ForeignKey("assets.id"), nullable=True, index=True)
    break_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(32), default="warning", nullable=False, index=True)
    expected_quantity: Mapped[float] = mapped_column(Numeric(28, 10), default=0, nullable=False)
    observed_quantity: Mapped[float] = mapped_column(Numeric(28, 10), default=0, nullable=False)
    delta_quantity: Mapped[float] = mapped_column(Numeric(28, 10), default=0, nullable=False)
    expected_cash: Mapped[float] = mapped_column(Numeric(28, 10), default=0, nullable=False)
    observed_cash: Mapped[float] = mapped_column(Numeric(28, 10), default=0, nullable=False)
    delta_cash: Mapped[float] = mapped_column(Numeric(28, 10), default=0, nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class StatementImportBatch(Base):
    __tablename__ = "statement_import_batches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(String(128), default="default-user", nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    account_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    statement_type: Mapped[str] = mapped_column(String(64), default="broker_statement", nullable=False, index=True)
    source_ref: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    raw_payload_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    row_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    imported_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="imported", nullable=False, index=True)
    summary_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    execution_available: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class WorkflowReviewTask(Base, TimestampMixin):
    __tablename__ = "workflow_review_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(String(128), default="default-user", nullable=False, index=True)
    queue_item_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    item_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(String(32), default="normal", nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default="open", nullable=False, index=True)
    assignee_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    related_entity_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    related_entity_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_workflow_review_tasks_user_status_due", "user_id", "status", "due_at"),
        Index("ix_workflow_review_tasks_queue_user", "queue_item_id", "user_id"),
    )


class ProductionReadinessTarget(Base, TimestampMixin):
    __tablename__ = "production_readiness_targets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(String(128), default="default-user", nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(64), default="manual", nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    reference_key: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="planned", nullable=False, index=True)
    required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_production_targets_user_type_provider", "user_id", "target_type", "provider"),
    )


class ScheduledJob(Base, TimestampMixin, TenantOwnedMixin):
    __tablename__ = "scheduled_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    job_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default="paused", nullable=False)
    schedule_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    target_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_run_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_run_summary: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class WatchlistItem(Base, TimestampMixin):
    __tablename__ = "watchlist_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    asset_id: Mapped[str | None] = mapped_column(ForeignKey("assets.id"), nullable=True, index=True)
    investment_thesis_id: Mapped[str | None] = mapped_column(ForeignKey("investment_theses.id"), nullable=True, index=True)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    asset_type: Mapped[str] = mapped_column(String(32), default="stock", nullable=False)
    market: Mapped[str] = mapped_column(String(64), default="US", nullable=False)
    priority: Mapped[str] = mapped_column(String(32), default="normal", nullable=False)
    alert_rules_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (Index("ix_watchlist_user_symbol", "user_id", "symbol"),)


class Reminder(Base, TimestampMixin):
    __tablename__ = "reminders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    reminder_type: Mapped[str] = mapped_column(String(64), default="manual", nullable=False, index=True)
    related_entity_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    related_entity_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    recurrence_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    priority: Mapped[str] = mapped_column(String(32), default="normal", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False, index=True)
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_reminders_user_status_due", "user_id", "status", "due_at"),)


class LocalUserConfig(Base, TimestampMixin):
    __tablename__ = "local_user_configs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    config_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    value_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (Index("ix_local_user_configs_user_key", "user_id", "config_key", unique=True),)


class ExportArtifact(Base):
    __tablename__ = "export_artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    export_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    format: Mapped[str] = mapped_column(String(32), default="json", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="ready", nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    summary_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class UserAccount(Base, TimestampMixin):
    __tablename__ = "user_accounts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), default="owner", nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False, index=True)
    permissions_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    onboarding_state_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SecretReference(Base, TimestampMixin):
    __tablename__ = "secret_references"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    reference_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    scope: Mapped[str] = mapped_column(String(64), default="read_only", nullable=False)
    storage_backend: Mapped[str] = mapped_column(String(64), default="env_or_local_secret_store", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False, index=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_secret_refs_user_reference", "user_id", "reference_key", unique=True),)


class OperationalEvent(Base):
    __tablename__ = "operational_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    user_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(32), default="info", nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="open", nullable=False, index=True)
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class LiveExecutionConfig(Base, TimestampMixin):
    __tablename__ = "live_execution_configs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(String(128), default="default-user", nullable=False, index=True)
    exchange_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    api_key_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)


class BrokerStateCheck(Base, TenantOwnedMixin):
    __tablename__ = "broker_state_checks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    live_execution_config_id: Mapped[str | None] = mapped_column(
        ForeignKey("live_execution_configs.id"),
        nullable=True,
        index=True,
    )
    order_draft_id: Mapped[str | None] = mapped_column(ForeignKey("order_drafts.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="blocked", nullable=False, index=True)
    connected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    details_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class KillSwitch(Base, TenantOwnedMixin):
    __tablename__ = "kill_switches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    account_id: Mapped[str | None] = mapped_column(ForeignKey("accounts.id"), nullable=True, index=True)
    asset_id: Mapped[str | None] = mapped_column(ForeignKey("assets.id"), nullable=True, index=True)
    engaged_by: Mapped[str] = mapped_column(String(128), default="user", nullable=False)
    disengaged_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    disengage_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    engaged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    disengaged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)


class PortfolioSnapshot(Base, TenantOwnedMixin):
    __tablename__ = "portfolio_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    account_id: Mapped[str | None] = mapped_column(ForeignKey("accounts.id"), nullable=True, index=True)
    total_value: Mapped[float] = mapped_column(Numeric(28, 10), default=0, nullable=False)
    cash_value: Mapped[float] = mapped_column(Numeric(28, 10), default=0, nullable=False)
    positions_value: Mapped[float] = mapped_column(Numeric(28, 10), default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(16), default="USD", nullable=False)
    snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class ResearchReport(Base, TenantOwnedMixin):
    __tablename__ = "research_reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    report_type: Mapped[str] = mapped_column(String(64), nullable=False)
    agent_name: Mapped[str] = mapped_column(String(128), nullable=False)
    data_snapshot_id: Mapped[str] = mapped_column(String(128), nullable=False)
    asset_id: Mapped[str | None] = mapped_column(ForeignKey("assets.id"), nullable=True, index=True)
    input_facts: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    bullish_case: Mapped[str | None] = mapped_column(Text, nullable=True)
    bearish_case: Mapped[str | None] = mapped_column(Text, nullable=True)
    key_risks: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    suggested_action: Mapped[str] = mapped_column(String(64), default="none", nullable=False)
    confidence: Mapped[float] = mapped_column(Numeric(8, 6), default=0, nullable=False)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    limitations: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    @property
    def report_id(self) -> str:
        return self.id


class AgentRun(Base, TenantOwnedMixin):
    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    agent_name: Mapped[str] = mapped_column(String(128), nullable=False)
    run_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="created", nullable=False)
    input_snapshot_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    output_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Signal(Base, TenantOwnedMixin):
    __tablename__ = "signals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), nullable=False, index=True)
    signal_type: Mapped[str] = mapped_column(String(64), nullable=False)
    direction: Mapped[str] = mapped_column(String(32), nullable=False)
    strength: Mapped[float] = mapped_column(Numeric(8, 6), default=0, nullable=False)
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    observation_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    @property
    def horizon(self) -> str:
        return self.observation_json.get("horizon", "swing")

    @property
    def evidence(self) -> dict:
        return self.observation_json.get("evidence", {})

    @property
    def invalidation_condition(self) -> str:
        return self.observation_json.get("invalidation_condition", "Data unavailable.")

    @property
    def suggested_action(self) -> str:
        return self.observation_json.get("suggested_action", "watch")

    @property
    def confidence(self) -> float:
        return self.observation_json.get("confidence", 0)


class RiskCheck(Base, TenantOwnedMixin):
    __tablename__ = "risk_checks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    order_intent_id: Mapped[str | None] = mapped_column(ForeignKey("order_intents.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    hard_rule_passed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    rules_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class InvestmentConstitution(Base, TimestampMixin):
    __tablename__ = "investment_constitutions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    investment_style: Mapped[str] = mapped_column(String(128), nullable=False)
    allowed_markets: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    forbidden_assets: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    forbidden_actions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    max_single_position_pct: Mapped[float] = mapped_column(Numeric(8, 6), nullable=False)
    max_asset_class_pct: Mapped[float] = mapped_column(Numeric(8, 6), nullable=False)
    max_crypto_pct: Mapped[float] = mapped_column(Numeric(8, 6), nullable=False)
    max_single_exchange_pct: Mapped[float] = mapped_column(Numeric(8, 6), nullable=False)
    max_daily_loss_pct: Mapped[float] = mapped_column(Numeric(8, 6), nullable=False)
    max_monthly_drawdown_pct: Mapped[float] = mapped_column(Numeric(8, 6), nullable=False)
    leverage_allowed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    derivatives_allowed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    auto_execution_allowed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    human_approval_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    cooldown_rules_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class RiskBudget(Base, TimestampMixin):
    __tablename__ = "risk_budgets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    constitution_id: Mapped[str] = mapped_column(ForeignKey("investment_constitutions.id"), nullable=False, index=True)
    account_id: Mapped[str | None] = mapped_column(ForeignKey("accounts.id"), nullable=True, index=True)
    asset_class: Mapped[str] = mapped_column(String(64), nullable=False)
    max_allocation_pct: Mapped[float] = mapped_column(Numeric(8, 6), nullable=False)
    max_loss_pct: Mapped[float] = mapped_column(Numeric(8, 6), nullable=False)
    max_order_notional: Mapped[float] = mapped_column(Numeric(28, 10), nullable=False)
    max_leverage: Mapped[float] = mapped_column(Numeric(12, 6), nullable=False)
    rebalance_threshold_pct: Mapped[float] = mapped_column(Numeric(8, 6), nullable=False)


class StrategyPlaybook(Base, TimestampMixin):
    __tablename__ = "strategy_playbooks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    strategy_type: Mapped[str] = mapped_column(String(64), nullable=False)
    applicable_markets: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    applicable_assets: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    entry_conditions_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    exit_conditions_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    risk_rules_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    automation_level: Mapped[str] = mapped_column(String(32), default="A1_RESEARCH", nullable=False)
    requires_human_approval: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class StrategyRule(Base, TimestampMixin, TenantOwnedMixin):
    __tablename__ = "strategy_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    strategy_playbook_id: Mapped[str] = mapped_column(ForeignKey("strategy_playbooks.id"), nullable=False, index=True)
    rule_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    priority: Mapped[int] = mapped_column(Integer, default=5, nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    conditions_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    actions_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    __table_args__ = (
        Index("ix_strategy_rules_playbook_priority", "strategy_playbook_id", "priority"),
    )


class BacktestRun(Base):
    __tablename__ = "backtest_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(String(128), default="default-user", nullable=False, index=True)
    strategy_playbook_id: Mapped[str] = mapped_column(ForeignKey("strategy_playbooks.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    date_from: Mapped[date] = mapped_column(Date, nullable=False)
    date_to: Mapped[date] = mapped_column(Date, nullable=False)
    initial_capital: Mapped[float] = mapped_column(Numeric(28, 10), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False, index=True)
    parameters_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    results_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    __table_args__ = (
        Index("ix_backtest_runs_playbook_created", "strategy_playbook_id", "created_at"),
    )


class InvestmentThesis(Base, TimestampMixin):
    __tablename__ = "investment_theses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), nullable=False, index=True)
    account_id: Mapped[str | None] = mapped_column(ForeignKey("accounts.id"), nullable=True, index=True)
    position_id: Mapped[str | None] = mapped_column(ForeignKey("positions.id"), nullable=True, index=True)
    strategy_playbook_id: Mapped[str | None] = mapped_column(ForeignKey("strategy_playbooks.id"), nullable=True, index=True)
    data_snapshot_id: Mapped[str | None] = mapped_column(ForeignKey("data_snapshots.id"), nullable=True, index=True)
    entry_reason: Mapped[str] = mapped_column(Text, nullable=False)
    key_drivers_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    invalidation_conditions_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    expected_horizon: Mapped[str] = mapped_column(String(64), nullable=False)
    target_condition: Mapped[str] = mapped_column(Text, nullable=False)
    max_loss_tolerance_pct: Mapped[float] = mapped_column(Numeric(8, 6), nullable=False)
    position_plan_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    confidence: Mapped[float] = mapped_column(Numeric(8, 6), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)


class ThesisCheckpoint(Base, TenantOwnedMixin):
    __tablename__ = "thesis_checkpoints"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    thesis_id: Mapped[str] = mapped_column(ForeignKey("investment_theses.id"), nullable=False, index=True)
    data_snapshot_id: Mapped[str | None] = mapped_column(ForeignKey("data_snapshots.id"), nullable=True, index=True)
    checkpoint_type: Mapped[str] = mapped_column(String(64), nullable=False)
    observed_facts_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    supports_thesis: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    weakens_thesis: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    invalidates_thesis: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Numeric(8, 6), default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class ThesisViolation(Base):
    __tablename__ = "thesis_violations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    thesis_id: Mapped[str] = mapped_column(ForeignKey("investment_theses.id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    related_order_intent_id: Mapped[str | None] = mapped_column(ForeignKey("order_intents.id"), nullable=True, index=True)
    violation_type: Mapped[str] = mapped_column(String(64), nullable=False)
    prior_user_statement: Mapped[str] = mapped_column(Text, nullable=False)
    current_action: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    intervention_level: Mapped[str] = mapped_column(String(32), nullable=False)
    resolved_status: Mapped[str] = mapped_column(String(32), default="open", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class DecisionGate(Base, TenantOwnedMixin):
    __tablename__ = "decision_gates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    order_intent_id: Mapped[str | None] = mapped_column(ForeignKey("order_intents.id"), nullable=True, index=True)
    gate_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    score: Mapped[float | None] = mapped_column(Numeric(8, 6), nullable=True)
    blocking_reasons_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    warnings_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    evidence_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    recommended_intervention_level: Mapped[str] = mapped_column(String(32), default="SILENT_RECORD", nullable=False)
    evaluator: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class BehaviorPattern(Base, TimestampMixin):
    __tablename__ = "behavior_patterns"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    pattern_type: Mapped[str] = mapped_column(String(64), nullable=False)
    asset_id: Mapped[str | None] = mapped_column(ForeignKey("assets.id"), nullable=True, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    estimated_cost: Mapped[float] = mapped_column(Numeric(28, 10), default=0, nullable=False)
    frequency: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)


class BehaviorIntervention(Base):
    __tablename__ = "behavior_interventions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    pattern_id: Mapped[str | None] = mapped_column(ForeignKey("behavior_patterns.id"), nullable=True, index=True)
    order_intent_id: Mapped[str | None] = mapped_column(ForeignKey("order_intents.id"), nullable=True, index=True)
    intervention_level: Mapped[str] = mapped_column(String(32), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    user_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    bypassed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class AutomationPolicy(Base, TimestampMixin):
    __tablename__ = "automation_policies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    account_id: Mapped[str | None] = mapped_column(ForeignKey("accounts.id"), nullable=True, index=True)
    asset_id: Mapped[str | None] = mapped_column(ForeignKey("assets.id"), nullable=True, index=True)
    strategy_playbook_id: Mapped[str | None] = mapped_column(ForeignKey("strategy_playbooks.id"), nullable=True, index=True)
    automation_level: Mapped[str] = mapped_column(String(32), default="A0_READ_ONLY", nullable=False)
    max_notional_per_order: Mapped[float] = mapped_column(Numeric(28, 10), default=0, nullable=False)
    max_orders_per_day: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    allowed_actions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    forbidden_actions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class WorkflowState(Base, TimestampMixin, TenantOwnedMixin):
    __tablename__ = "workflow_states"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    workflow_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    current_state: Mapped[str] = mapped_column(String(64), nullable=False)
    previous_state: Mapped[str | None] = mapped_column(String(64), nullable=True)
    transition_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class MonthlyDecisionReview(Base):
    __tablename__ = "monthly_decision_reviews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    total_trades: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    thesis_aligned_trades: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    thesis_violating_trades: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    impulsive_trades: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    blocked_trades: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    bypassed_warnings: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    planned_trade_pnl: Mapped[float] = mapped_column(Numeric(28, 10), default=0, nullable=False)
    impulsive_trade_pnl: Mapped[float] = mapped_column(Numeric(28, 10), default=0, nullable=False)
    overtrading_cost: Mapped[float] = mapped_column(Numeric(28, 10), default=0, nullable=False)
    top_behavior_patterns_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    recommended_rule_updates_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class CommandQuery(Base):
    __tablename__ = "command_queries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    raw_query: Mapped[str] = mapped_column(Text, nullable=False)
    detected_intent: Mapped[str] = mapped_column(String(64), nullable=False)
    required_tools: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class CommandToolCall(Base, TenantOwnedMixin):
    __tablename__ = "command_tool_calls"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    command_query_id: Mapped[str] = mapped_column(ForeignKey("command_queries.id"), nullable=False, index=True)
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False)
    input_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    output_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class CommandResult(Base, TenantOwnedMixin):
    __tablename__ = "command_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    command_query_id: Mapped[str] = mapped_column(ForeignKey("command_queries.id"), nullable=False, index=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    structured_result_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    data_sources_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class Chain(Base, TimestampMixin):
    __tablename__ = "chains"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    chain_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    native_symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    explorer_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Wallet(Base, TimestampMixin):
    __tablename__ = "wallets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    address: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    chain: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    label: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (Index("ix_wallets_user_address_chain", "user_id", "address", "chain"),)


class TokenBalance(Base, TenantOwnedMixin):
    __tablename__ = "token_balances"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    wallet_id: Mapped[str] = mapped_column(ForeignKey("wallets.id"), nullable=False, index=True)
    chain: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    token: Mapped[str] = mapped_column(String(128), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    token_address: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    balance: Mapped[float] = mapped_column(Numeric(36, 18), default=0, nullable=False)
    usd_price: Mapped[float] = mapped_column(Numeric(28, 10), default=0, nullable=False)
    usd_value: Mapped[float] = mapped_column(Numeric(28, 10), default=0, nullable=False)
    source: Mapped[str] = mapped_column(String(64), default="mock_read_only", nullable=False)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class TokenAllowance(Base, TenantOwnedMixin):
    __tablename__ = "token_allowances"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    wallet_id: Mapped[str] = mapped_column(ForeignKey("wallets.id"), nullable=False, index=True)
    chain: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    token: Mapped[str] = mapped_column(String(128), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    token_address: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    spender: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    amount: Mapped[float] = mapped_column(Numeric(36, 18), default=0, nullable=False)
    usd_value: Mapped[float] = mapped_column(Numeric(28, 10), default=0, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(32), default="low", nullable=False)
    source: Mapped[str] = mapped_column(String(64), default="mock_read_only", nullable=False)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class WalletTransfer(Base, TenantOwnedMixin):
    __tablename__ = "wallet_transfers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    wallet_id: Mapped[str] = mapped_column(ForeignKey("wallets.id"), nullable=False, index=True)
    chain: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    tx_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    from_address: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    to_address: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    token: Mapped[str] = mapped_column(String(128), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(36, 18), default=0, nullable=False)
    usd_value: Mapped[float] = mapped_column(Numeric(28, 10), default=0, nullable=False)
    direction: Mapped[str] = mapped_column(String(32), nullable=False)
    is_known_contract: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class ProtocolPosition(Base, TenantOwnedMixin):
    __tablename__ = "protocol_positions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    wallet_id: Mapped[str] = mapped_column(ForeignKey("wallets.id"), nullable=False, index=True)
    chain: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    protocol_name: Mapped[str] = mapped_column(String(128), nullable=False)
    position_type: Mapped[str] = mapped_column(String(64), nullable=False)
    asset_symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    usd_value: Mapped[float] = mapped_column(Numeric(28, 10), default=0, nullable=False)
    risk_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class ExchangeExposure(Base, TimestampMixin):
    __tablename__ = "exchange_exposures"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    exchange_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    asset_symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    usd_value: Mapped[float] = mapped_column(Numeric(28, 10), default=0, nullable=False)
    exposure_pct: Mapped[float] = mapped_column(Numeric(18, 10), default=0, nullable=False)
    source: Mapped[str] = mapped_column(String(64), default="manual_read_only", nullable=False)


class StablecoinExposure(Base):
    __tablename__ = "stablecoin_exposures"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    wallet_id: Mapped[str | None] = mapped_column(ForeignKey("wallets.id"), nullable=True, index=True)
    chain: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    issuer: Mapped[str | None] = mapped_column(String(128), nullable=True)
    amount: Mapped[float] = mapped_column(Numeric(36, 18), default=0, nullable=False)
    usd_value: Mapped[float] = mapped_column(Numeric(28, 10), default=0, nullable=False)
    reference_price: Mapped[float] = mapped_column(Numeric(28, 10), default=1, nullable=False)
    depeg_risk_score: Mapped[float] = mapped_column(Numeric(8, 6), default=0, nullable=False)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class OnchainRiskAlert(Base):
    __tablename__ = "onchain_risk_alerts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    wallet_id: Mapped[str | None] = mapped_column(ForeignKey("wallets.id"), nullable=True, index=True)
    alert_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OrderIntent(Base, TenantOwnedMixin):
    __tablename__ = "order_intents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), nullable=False, index=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), nullable=False, index=True)
    investment_thesis_id: Mapped[str | None] = mapped_column(ForeignKey("investment_theses.id"), nullable=True, index=True)
    strategy_playbook_id: Mapped[str | None] = mapped_column(ForeignKey("strategy_playbooks.id"), nullable=True, index=True)
    automation_policy_id: Mapped[str | None] = mapped_column(ForeignKey("automation_policies.id"), nullable=True, index=True)
    source_signal_id: Mapped[str | None] = mapped_column(ForeignKey("signals.id"), nullable=True, index=True)
    side: Mapped[str] = mapped_column(String(16), nullable=False)
    order_type: Mapped[str] = mapped_column(String(32), nullable=False)
    quantity: Mapped[float | None] = mapped_column(Numeric(28, 10), nullable=True)
    notional: Mapped[float | None] = mapped_column(Numeric(28, 10), nullable=True)
    limit_price: Mapped[float | None] = mapped_column(Numeric(28, 10), nullable=True)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    user_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="created", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class OrderDraft(Base, TenantOwnedMixin):
    __tablename__ = "order_drafts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    order_intent_id: Mapped[str] = mapped_column(ForeignKey("order_intents.id"), nullable=False, index=True)
    risk_status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    behavior_status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    decision_gate_results: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    approval_policy: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    approval_status: Mapped[str] = mapped_column(String(32), default="not_requested", nullable=False)
    execution_status: Mapped[str] = mapped_column(String(32), default="not_executable", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class Approval(Base, TenantOwnedMixin):
    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    order_draft_id: Mapped[str] = mapped_column(ForeignKey("order_drafts.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    approver_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Execution(Base, TenantOwnedMixin):
    __tablename__ = "executions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    order_draft_id: Mapped[str] = mapped_column(ForeignKey("order_drafts.id"), nullable=False, index=True)
    position_id: Mapped[str | None] = mapped_column(ForeignKey("positions.id"), nullable=True, index=True)
    execution_mode: Mapped[str] = mapped_column(String(32), default="none", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="not_started", nullable=False)
    filled_quantity: Mapped[float] = mapped_column(Numeric(28, 10), default=0, nullable=False)
    average_fill_price: Mapped[float | None] = mapped_column(Numeric(28, 10), nullable=True)
    fill_notional: Mapped[float] = mapped_column(Numeric(28, 10), default=0, nullable=False)
    fee_amount: Mapped[float] = mapped_column(Numeric(28, 10), default=0, nullable=False)
    slippage_amount: Mapped[float] = mapped_column(Numeric(28, 10), default=0, nullable=False)
    cash_effect: Mapped[float] = mapped_column(Numeric(28, 10), default=0, nullable=False)
    requested_quantity: Mapped[float] = mapped_column(Numeric(28, 10), default=0, nullable=False)
    cumulative_filled_quantity: Mapped[float] = mapped_column(Numeric(28, 10), default=0, nullable=False)
    remaining_quantity: Mapped[float] = mapped_column(Numeric(28, 10), default=0, nullable=False)
    proceeds_amount: Mapped[float] = mapped_column(Numeric(28, 10), default=0, nullable=False)
    cost_basis_amount: Mapped[float] = mapped_column(Numeric(28, 10), default=0, nullable=False)
    realized_pnl: Mapped[float] = mapped_column(Numeric(28, 10), default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class PaperTaxLot(Base, TenantOwnedMixin):
    __tablename__ = "paper_tax_lots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), nullable=False, index=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), nullable=False, index=True)
    source_execution_id: Mapped[str | None] = mapped_column(ForeignKey("executions.id"), nullable=True, index=True)
    opened_order_draft_id: Mapped[str | None] = mapped_column(ForeignKey("order_drafts.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="open", nullable=False)
    quantity_opened: Mapped[float] = mapped_column(Numeric(28, 10), nullable=False)
    quantity_remaining: Mapped[float] = mapped_column(Numeric(28, 10), nullable=False)
    average_cost: Mapped[float] = mapped_column(Numeric(28, 10), nullable=False)
    cost_basis_remaining: Mapped[float] = mapped_column(Numeric(28, 10), nullable=False)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class PaperTaxLotRealization(Base, TenantOwnedMixin):
    __tablename__ = "paper_tax_lot_realizations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    execution_id: Mapped[str] = mapped_column(ForeignKey("executions.id"), nullable=False, index=True)
    tax_lot_id: Mapped[str] = mapped_column(ForeignKey("paper_tax_lots.id"), nullable=False, index=True)
    quantity: Mapped[float] = mapped_column(Numeric(28, 10), nullable=False)
    proceeds_amount: Mapped[float] = mapped_column(Numeric(28, 10), default=0, nullable=False)
    cost_basis_amount: Mapped[float] = mapped_column(Numeric(28, 10), default=0, nullable=False)
    fee_allocated: Mapped[float] = mapped_column(Numeric(28, 10), default=0, nullable=False)
    realized_pnl: Mapped[float] = mapped_column(Numeric(28, 10), default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class PaperCorporateAction(Base, TimestampMixin, TenantOwnedMixin):
    __tablename__ = "paper_corporate_actions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), nullable=False, index=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), nullable=False, index=True)
    action_type: Mapped[str] = mapped_column(String(32), nullable=False)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    quantity_before: Mapped[float] = mapped_column(Numeric(28, 10), default=0, nullable=False)
    quantity_after: Mapped[float] = mapped_column(Numeric(28, 10), default=0, nullable=False)
    cash_effect: Mapped[float] = mapped_column(Numeric(28, 10), default=0, nullable=False)
    ratio: Mapped[float | None] = mapped_column(Numeric(28, 10), nullable=True)
    amount_per_share: Mapped[float | None] = mapped_column(Numeric(28, 10), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="applied", nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class TradeJournalEntry(Base, TenantOwnedMixin):
    __tablename__ = "trade_journal_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    asset_id: Mapped[str | None] = mapped_column(ForeignKey("assets.id"), nullable=True, index=True)
    account_id: Mapped[str | None] = mapped_column(ForeignKey("accounts.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False)
    tags_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class PostTradeReview(Base, TimestampMixin):
    __tablename__ = "post_trade_reviews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    execution_id: Mapped[str] = mapped_column(ForeignKey("executions.id"), nullable=False, index=True)
    trade_journal_entry_id: Mapped[str] = mapped_column(ForeignKey("trade_journal_entries.id"), nullable=False, index=True)
    order_draft_id: Mapped[str] = mapped_column(ForeignKey("order_drafts.id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    prompt_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    review_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class PlaybookUpdateProposal(Base, TimestampMixin):
    __tablename__ = "playbook_update_proposals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    strategy_playbook_id: Mapped[str | None] = mapped_column(ForeignKey("strategy_playbooks.id"), nullable=True, index=True)
    proposal_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    requires_user_approval: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditLog(Base, TenantOwnedMixin):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    actor_type: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(128), nullable=False)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(128), nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
