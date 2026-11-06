"""Remove the redundant legacy PostgreSQL identity constraint, retaining uniqueness."""
from alembic import context, op
import sqlalchemy as sa

revision = '20261106_0027'
down_revision = '20261102_0026'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != 'postgresql':
        return
    if context.is_offline_mode():
        raise RuntimeError('PostgreSQL identity parity requires live schema inspection')
    inspector = sa.inspect(bind)
    indexes = inspector.get_indexes('user_accounts')
    if not any(index['name'] == 'ix_user_accounts_user_id' and index.get('unique')
               and index['column_names'] == ['user_id'] for index in indexes):
        raise RuntimeError('Retain a verified unique user_id index before removing the legacy constraint')
    for constraint in inspector.get_unique_constraints('user_accounts'):
        if constraint['name'] == 'user_accounts_user_id_key' and constraint['column_names'] == ['user_id']:
            op.drop_constraint(constraint['name'], 'user_accounts', type_='unique')


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        if context.is_offline_mode():
            raise RuntimeError('PostgreSQL identity parity requires live schema inspection')
        if not any(item['name'] == 'user_accounts_user_id_key'
                   for item in sa.inspect(bind).get_unique_constraints('user_accounts')):
            op.create_unique_constraint('user_accounts_user_id_key', 'user_accounts', ['user_id'])
