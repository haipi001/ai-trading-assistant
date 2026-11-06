"""Server-issued Paper manual trade quote evidence."""
from alembic import op
import sqlalchemy as sa
revision = '20261102_0024'
down_revision = '20261101_0023'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('manual_trade_evidence',
        sa.Column('data_snapshot_id', sa.String(36), sa.ForeignKey('data_snapshots.id'), primary_key=True),
        sa.Column('order_intent_id', sa.String(36), sa.ForeignKey('order_intents.id'), nullable=False),
        sa.Column('quote_id', sa.String(36), sa.ForeignKey('quotes.id'), nullable=False),
        sa.Column('content_hash', sa.String(64), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('user_id', sa.String(128), nullable=False))
    op.create_index('ix_manual_trade_evidence_order_intent_id', 'manual_trade_evidence', ['order_intent_id'])
    op.create_index('ix_manual_trade_evidence_user_id', 'manual_trade_evidence', ['user_id'])


def downgrade():
    op.drop_table('manual_trade_evidence')
