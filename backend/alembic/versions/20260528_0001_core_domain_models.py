"""core domain models

Revision ID: 20260528_0001
Revises:
Create Date: 2026-05-28
"""
from typing import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260528_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "assets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("asset_type", sa.String(length=32), nullable=False),
        sa.Column("market", sa.String(length=64), nullable=False),
        sa.Column("venue", sa.String(length=64), nullable=False),
        sa.Column("currency", sa.String(length=16), nullable=False),
        sa.Column("chain_id", sa.String(length=64), nullable=True),
        sa.Column("contract_address", sa.String(length=128), nullable=True),
        sa.Column("tradable", sa.Boolean(), nullable=False),
        sa.Column("manual_enabled", sa.Boolean(), nullable=False),
        sa.Column("auto_enabled", sa.Boolean(), nullable=False),
        sa.Column("risk_level", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_assets_symbol"), "assets", ["symbol"], unique=False)

    op.create_table(
        "accounts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("account_type", sa.String(length=64), nullable=False),
        sa.Column("broker", sa.String(length=128), nullable=False),
        sa.Column("base_currency", sa.String(length=16), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("live_trading_enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "agent_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("agent_name", sa.String(length=128), nullable=False),
        sa.Column("run_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("input_snapshot_id", sa.String(length=128), nullable=True),
        sa.Column("output_json", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("actor_type", sa.String(length=64), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=False),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=128), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "portfolio_snapshots",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=True),
        sa.Column("total_value", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("cash_value", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("positions_value", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("currency", sa.String(length=16), nullable=False),
        sa.Column("snapshot_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_portfolio_snapshots_account_id"), "portfolio_snapshots", ["account_id"], unique=False)

    op.create_table(
        "positions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=False),
        sa.Column("asset_id", sa.String(length=36), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("average_cost", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("market_price", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("market_value", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("unrealized_pnl", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("realized_pnl", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("weight", sa.Numeric(precision=18, scale=10), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_positions_account_id"), "positions", ["account_id"], unique=False)
    op.create_index(op.f("ix_positions_asset_id"), "positions", ["asset_id"], unique=False)

    op.create_table(
        "quotes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("asset_id", sa.String(length=36), nullable=False),
        sa.Column("price", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("bid", sa.Numeric(precision=28, scale=10), nullable=True),
        sa.Column("ask", sa.Numeric(precision=28, scale=10), nullable=True),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_quotes_asset_id"), "quotes", ["asset_id"], unique=False)

    op.create_table(
        "candles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("asset_id", sa.String(length=36), nullable=False),
        sa.Column("timeframe", sa.String(length=32), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("high", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("low", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("close", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("volume", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_candles_asset_timeframe_timestamp", "candles", ["asset_id", "timeframe", "timestamp"], unique=False)
    op.create_index(op.f("ix_candles_asset_id"), "candles", ["asset_id"], unique=False)

    op.create_table(
        "research_reports",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("report_type", sa.String(length=64), nullable=False),
        sa.Column("agent_name", sa.String(length=128), nullable=False),
        sa.Column("data_snapshot_id", sa.String(length=128), nullable=False),
        sa.Column("asset_id", sa.String(length=36), nullable=True),
        sa.Column("input_facts", sa.JSON(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("bullish_case", sa.Text(), nullable=True),
        sa.Column("bearish_case", sa.Text(), nullable=True),
        sa.Column("key_risks", sa.JSON(), nullable=False),
        sa.Column("suggested_action", sa.String(length=64), nullable=False),
        sa.Column("confidence", sa.Numeric(precision=8, scale=6), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("limitations", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_research_reports_asset_id"), "research_reports", ["asset_id"], unique=False)

    op.create_table(
        "signals",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("asset_id", sa.String(length=36), nullable=False),
        sa.Column("signal_type", sa.String(length=64), nullable=False),
        sa.Column("direction", sa.String(length=32), nullable=False),
        sa.Column("strength", sa.Numeric(precision=8, scale=6), nullable=False),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column("observation_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_signals_asset_id"), "signals", ["asset_id"], unique=False)

    op.create_table(
        "order_intents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("source_id", sa.String(length=128), nullable=True),
        sa.Column("asset_id", sa.String(length=36), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=False),
        sa.Column("side", sa.String(length=16), nullable=False),
        sa.Column("order_type", sa.String(length=32), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=28, scale=10), nullable=True),
        sa.Column("notional", sa.Numeric(precision=28, scale=10), nullable=True),
        sa.Column("limit_price", sa.Numeric(precision=28, scale=10), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_order_intents_account_id"), "order_intents", ["account_id"], unique=False)
    op.create_index(op.f("ix_order_intents_asset_id"), "order_intents", ["asset_id"], unique=False)

    op.create_table(
        "order_drafts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("order_intent_id", sa.String(length=36), nullable=False),
        sa.Column("risk_status", sa.String(length=32), nullable=False),
        sa.Column("approval_status", sa.String(length=32), nullable=False),
        sa.Column("execution_status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["order_intent_id"], ["order_intents.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_order_drafts_order_intent_id"), "order_drafts", ["order_intent_id"], unique=False)

    op.create_table(
        "risk_checks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("order_intent_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("hard_rule_passed", sa.Boolean(), nullable=False),
        sa.Column("rules_json", sa.JSON(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["order_intent_id"], ["order_intents.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_risk_checks_order_intent_id"), "risk_checks", ["order_intent_id"], unique=False)

    op.create_table(
        "approvals",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("order_draft_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("approver_id", sa.String(length=128), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["order_draft_id"], ["order_drafts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_approvals_order_draft_id"), "approvals", ["order_draft_id"], unique=False)

    op.create_table(
        "executions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("order_draft_id", sa.String(length=36), nullable=False),
        sa.Column("execution_mode", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("filled_quantity", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("average_fill_price", sa.Numeric(precision=28, scale=10), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["order_draft_id"], ["order_drafts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_executions_order_draft_id"), "executions", ["order_draft_id"], unique=False)

    op.create_table(
        "trade_journal_entries",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("asset_id", sa.String(length=36), nullable=True),
        sa.Column("account_id", sa.String(length=36), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("tags_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_trade_journal_entries_account_id"), "trade_journal_entries", ["account_id"], unique=False)
    op.create_index(op.f("ix_trade_journal_entries_asset_id"), "trade_journal_entries", ["asset_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_trade_journal_entries_asset_id"), table_name="trade_journal_entries")
    op.drop_index(op.f("ix_trade_journal_entries_account_id"), table_name="trade_journal_entries")
    op.drop_table("trade_journal_entries")
    op.drop_index(op.f("ix_executions_order_draft_id"), table_name="executions")
    op.drop_table("executions")
    op.drop_index(op.f("ix_approvals_order_draft_id"), table_name="approvals")
    op.drop_table("approvals")
    op.drop_index(op.f("ix_risk_checks_order_intent_id"), table_name="risk_checks")
    op.drop_table("risk_checks")
    op.drop_index(op.f("ix_order_drafts_order_intent_id"), table_name="order_drafts")
    op.drop_table("order_drafts")
    op.drop_index(op.f("ix_order_intents_asset_id"), table_name="order_intents")
    op.drop_index(op.f("ix_order_intents_account_id"), table_name="order_intents")
    op.drop_table("order_intents")
    op.drop_index(op.f("ix_signals_asset_id"), table_name="signals")
    op.drop_table("signals")
    op.drop_index(op.f("ix_research_reports_asset_id"), table_name="research_reports")
    op.drop_table("research_reports")
    op.drop_index(op.f("ix_candles_asset_id"), table_name="candles")
    op.drop_index("ix_candles_asset_timeframe_timestamp", table_name="candles")
    op.drop_table("candles")
    op.drop_index(op.f("ix_quotes_asset_id"), table_name="quotes")
    op.drop_table("quotes")
    op.drop_index(op.f("ix_positions_asset_id"), table_name="positions")
    op.drop_index(op.f("ix_positions_account_id"), table_name="positions")
    op.drop_table("positions")
    op.drop_index(op.f("ix_portfolio_snapshots_account_id"), table_name="portfolio_snapshots")
    op.drop_table("portfolio_snapshots")
    op.drop_table("audit_logs")
    op.drop_table("agent_runs")
    op.drop_table("accounts")
    op.drop_index(op.f("ix_assets_symbol"), table_name="assets")
    op.drop_table("assets")
