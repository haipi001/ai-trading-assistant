"""web3 read-only risk models

Revision ID: 20260529_0005
Revises: 20260529_0004
Create Date: 2026-05-29
"""
from typing import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260529_0005"
down_revision: Union[str, None] = "20260529_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chains",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("chain_id", sa.String(length=64), nullable=False),
        sa.Column("native_symbol", sa.String(length=32), nullable=False),
        sa.Column("explorer_url", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chain_id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "wallets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("address", sa.String(length=128), nullable=False),
        sa.Column("chain", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=128), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_wallets_user_id"), "wallets", ["user_id"], unique=False)
    op.create_index(op.f("ix_wallets_address"), "wallets", ["address"], unique=False)
    op.create_index(op.f("ix_wallets_chain"), "wallets", ["chain"], unique=False)
    op.create_index("ix_wallets_user_address_chain", "wallets", ["user_id", "address", "chain"], unique=False)

    op.create_table(
        "token_balances",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("wallet_id", sa.String(length=36), nullable=False),
        sa.Column("chain", sa.String(length=64), nullable=False),
        sa.Column("token", sa.String(length=128), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("token_address", sa.String(length=128), nullable=True),
        sa.Column("balance", sa.Numeric(precision=36, scale=18), nullable=False),
        sa.Column("usd_price", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("usd_value", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["wallet_id"], ["wallets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_token_balances_wallet_id"), "token_balances", ["wallet_id"], unique=False)
    op.create_index(op.f("ix_token_balances_chain"), "token_balances", ["chain"], unique=False)
    op.create_index(op.f("ix_token_balances_symbol"), "token_balances", ["symbol"], unique=False)
    op.create_index(op.f("ix_token_balances_token_address"), "token_balances", ["token_address"], unique=False)

    op.create_table(
        "token_allowances",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("wallet_id", sa.String(length=36), nullable=False),
        sa.Column("chain", sa.String(length=64), nullable=False),
        sa.Column("token", sa.String(length=128), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("token_address", sa.String(length=128), nullable=True),
        sa.Column("spender", sa.String(length=128), nullable=False),
        sa.Column("amount", sa.Numeric(precision=36, scale=18), nullable=False),
        sa.Column("usd_value", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("risk_level", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["wallet_id"], ["wallets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_token_allowances_wallet_id"), "token_allowances", ["wallet_id"], unique=False)
    op.create_index(op.f("ix_token_allowances_chain"), "token_allowances", ["chain"], unique=False)
    op.create_index(op.f("ix_token_allowances_symbol"), "token_allowances", ["symbol"], unique=False)
    op.create_index(op.f("ix_token_allowances_token_address"), "token_allowances", ["token_address"], unique=False)
    op.create_index(op.f("ix_token_allowances_spender"), "token_allowances", ["spender"], unique=False)

    op.create_table(
        "wallet_transfers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("wallet_id", sa.String(length=36), nullable=False),
        sa.Column("chain", sa.String(length=64), nullable=False),
        sa.Column("tx_hash", sa.String(length=128), nullable=False),
        sa.Column("from_address", sa.String(length=128), nullable=False),
        sa.Column("to_address", sa.String(length=128), nullable=False),
        sa.Column("token", sa.String(length=128), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("amount", sa.Numeric(precision=36, scale=18), nullable=False),
        sa.Column("usd_value", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("direction", sa.String(length=32), nullable=False),
        sa.Column("is_known_contract", sa.Boolean(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["wallet_id"], ["wallets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_wallet_transfers_wallet_id"), "wallet_transfers", ["wallet_id"], unique=False)
    op.create_index(op.f("ix_wallet_transfers_chain"), "wallet_transfers", ["chain"], unique=False)
    op.create_index(op.f("ix_wallet_transfers_tx_hash"), "wallet_transfers", ["tx_hash"], unique=False)
    op.create_index(op.f("ix_wallet_transfers_from_address"), "wallet_transfers", ["from_address"], unique=False)
    op.create_index(op.f("ix_wallet_transfers_to_address"), "wallet_transfers", ["to_address"], unique=False)

    op.create_table(
        "protocol_positions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("wallet_id", sa.String(length=36), nullable=False),
        sa.Column("chain", sa.String(length=64), nullable=False),
        sa.Column("protocol_name", sa.String(length=128), nullable=False),
        sa.Column("position_type", sa.String(length=64), nullable=False),
        sa.Column("asset_symbol", sa.String(length=32), nullable=False),
        sa.Column("usd_value", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("risk_json", sa.JSON(), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["wallet_id"], ["wallets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_protocol_positions_wallet_id"), "protocol_positions", ["wallet_id"], unique=False)
    op.create_index(op.f("ix_protocol_positions_chain"), "protocol_positions", ["chain"], unique=False)

    op.create_table(
        "exchange_exposures",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("exchange_name", sa.String(length=128), nullable=False),
        sa.Column("asset_symbol", sa.String(length=32), nullable=False),
        sa.Column("usd_value", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("exposure_pct", sa.Numeric(precision=18, scale=10), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_exchange_exposures_user_id"), "exchange_exposures", ["user_id"], unique=False)
    op.create_index(op.f("ix_exchange_exposures_exchange_name"), "exchange_exposures", ["exchange_name"], unique=False)

    op.create_table(
        "stablecoin_exposures",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("wallet_id", sa.String(length=36), nullable=True),
        sa.Column("chain", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("issuer", sa.String(length=128), nullable=True),
        sa.Column("amount", sa.Numeric(precision=36, scale=18), nullable=False),
        sa.Column("usd_value", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("reference_price", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("depeg_risk_score", sa.Numeric(precision=8, scale=6), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["wallet_id"], ["wallets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_stablecoin_exposures_user_id"), "stablecoin_exposures", ["user_id"], unique=False)
    op.create_index(op.f("ix_stablecoin_exposures_wallet_id"), "stablecoin_exposures", ["wallet_id"], unique=False)
    op.create_index(op.f("ix_stablecoin_exposures_chain"), "stablecoin_exposures", ["chain"], unique=False)
    op.create_index(op.f("ix_stablecoin_exposures_symbol"), "stablecoin_exposures", ["symbol"], unique=False)

    op.create_table(
        "onchain_risk_alerts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("wallet_id", sa.String(length=36), nullable=True),
        sa.Column("alert_type", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("resolved", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["wallet_id"], ["wallets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_onchain_risk_alerts_user_id"), "onchain_risk_alerts", ["user_id"], unique=False)
    op.create_index(op.f("ix_onchain_risk_alerts_wallet_id"), "onchain_risk_alerts", ["wallet_id"], unique=False)
    op.create_index(op.f("ix_onchain_risk_alerts_alert_type"), "onchain_risk_alerts", ["alert_type"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_onchain_risk_alerts_alert_type"), table_name="onchain_risk_alerts")
    op.drop_index(op.f("ix_onchain_risk_alerts_wallet_id"), table_name="onchain_risk_alerts")
    op.drop_index(op.f("ix_onchain_risk_alerts_user_id"), table_name="onchain_risk_alerts")
    op.drop_table("onchain_risk_alerts")
    op.drop_index(op.f("ix_stablecoin_exposures_symbol"), table_name="stablecoin_exposures")
    op.drop_index(op.f("ix_stablecoin_exposures_chain"), table_name="stablecoin_exposures")
    op.drop_index(op.f("ix_stablecoin_exposures_wallet_id"), table_name="stablecoin_exposures")
    op.drop_index(op.f("ix_stablecoin_exposures_user_id"), table_name="stablecoin_exposures")
    op.drop_table("stablecoin_exposures")
    op.drop_index(op.f("ix_exchange_exposures_exchange_name"), table_name="exchange_exposures")
    op.drop_index(op.f("ix_exchange_exposures_user_id"), table_name="exchange_exposures")
    op.drop_table("exchange_exposures")
    op.drop_index(op.f("ix_protocol_positions_chain"), table_name="protocol_positions")
    op.drop_index(op.f("ix_protocol_positions_wallet_id"), table_name="protocol_positions")
    op.drop_table("protocol_positions")
    op.drop_index(op.f("ix_wallet_transfers_to_address"), table_name="wallet_transfers")
    op.drop_index(op.f("ix_wallet_transfers_from_address"), table_name="wallet_transfers")
    op.drop_index(op.f("ix_wallet_transfers_tx_hash"), table_name="wallet_transfers")
    op.drop_index(op.f("ix_wallet_transfers_chain"), table_name="wallet_transfers")
    op.drop_index(op.f("ix_wallet_transfers_wallet_id"), table_name="wallet_transfers")
    op.drop_table("wallet_transfers")
    op.drop_index(op.f("ix_token_allowances_spender"), table_name="token_allowances")
    op.drop_index(op.f("ix_token_allowances_token_address"), table_name="token_allowances")
    op.drop_index(op.f("ix_token_allowances_symbol"), table_name="token_allowances")
    op.drop_index(op.f("ix_token_allowances_chain"), table_name="token_allowances")
    op.drop_index(op.f("ix_token_allowances_wallet_id"), table_name="token_allowances")
    op.drop_table("token_allowances")
    op.drop_index(op.f("ix_token_balances_token_address"), table_name="token_balances")
    op.drop_index(op.f("ix_token_balances_symbol"), table_name="token_balances")
    op.drop_index(op.f("ix_token_balances_chain"), table_name="token_balances")
    op.drop_index(op.f("ix_token_balances_wallet_id"), table_name="token_balances")
    op.drop_table("token_balances")
    op.drop_index("ix_wallets_user_address_chain", table_name="wallets")
    op.drop_index(op.f("ix_wallets_chain"), table_name="wallets")
    op.drop_index(op.f("ix_wallets_address"), table_name="wallets")
    op.drop_index(op.f("ix_wallets_user_id"), table_name="wallets")
    op.drop_table("wallets")
    op.drop_table("chains")
