"""Private notification dispositions, separate from trading approval."""
from alembic import op
import sqlalchemy as sa
revision = '20261102_0026'
down_revision = '20261102_0025'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('ace_action_states',
        sa.Column('user_id', sa.String(128), primary_key=True),
        sa.Column('action_id', sa.String(128), primary_key=True),
        sa.Column('source_revision', sa.String(64), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(32), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False))


def downgrade():
    op.drop_table('ace_action_states')
