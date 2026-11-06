"""Durable Paper fill sequence and optional idempotency identity."""
from alembic import op
import sqlalchemy as sa
revision = '20261102_0025'
down_revision = '20261102_0024'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('executions', sa.Column('fill_sequence', sa.Integer(), nullable=True))
    op.add_column('executions', sa.Column('idempotency_key', sa.String(128), nullable=True))
    op.add_column('executions', sa.Column('request_fingerprint', sa.String(64), nullable=True))
    connection = op.get_bind()
    rows = connection.execute(sa.text('SELECT id, order_draft_id FROM executions ORDER BY order_draft_id, created_at, id')).mappings()
    counters = {}
    for row in rows:
        sequence = counters.get(row['order_draft_id'], 0) + 1
        counters[row['order_draft_id']] = sequence
        connection.execute(sa.text('UPDATE executions SET fill_sequence=:sequence WHERE id=:id'),
                           {'sequence': sequence, 'id': row['id']})
    with op.batch_alter_table('executions') as batch:
        batch.create_check_constraint('ck_paper_execution_fill_sequence', "execution_mode != 'paper' OR (fill_sequence IS NOT NULL AND fill_sequence > 0)")
    op.create_index('ux_executions_draft_fill_sequence', 'executions', ['order_draft_id', 'fill_sequence'], unique=True)
    op.create_index('ux_executions_draft_idempotency_key', 'executions', ['order_draft_id', 'idempotency_key'], unique=True)


def downgrade():
    with op.batch_alter_table('executions') as batch:
        batch.drop_constraint('ck_paper_execution_fill_sequence', type_='check')
    op.drop_index('ux_executions_draft_idempotency_key', table_name='executions')
    op.drop_index('ux_executions_draft_fill_sequence', table_name='executions')
    op.drop_column('executions', 'request_fingerprint')
    op.drop_column('executions', 'idempotency_key')
    op.drop_column('executions', 'fill_sequence')
