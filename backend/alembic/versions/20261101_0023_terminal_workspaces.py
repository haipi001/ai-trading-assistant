"""User-owned terminal workspaces with optimistic versions."""
from alembic import op
import sqlalchemy as sa
revision = '20261101_0023'
down_revision = '20260717_0022'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('terminal_workspaces',
        sa.Column('user_id',sa.String(128),primary_key=True),
        sa.Column('workspace_id',sa.String(128),primary_key=True),
        sa.Column('version',sa.Integer(),nullable=False),
        sa.Column('context_json',sa.JSON(),nullable=False),
        sa.Column('layout_json',sa.JSON(),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_terminal_workspaces_user_id','terminal_workspaces',['user_id'])


def downgrade():
    op.drop_index('ix_terminal_workspaces_user_id',table_name='terminal_workspaces')
    op.drop_table('terminal_workspaces')
