"""Operation-journal degraded mode and explicit test-data metadata."""
from alembic import op
import sqlalchemy as sa

revision='d8a1f3b92c10'
down_revision='c41d2f8a7b10'
branch_labels=None
depends_on=None


def _columns(table):
    return {c['name'] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade():
    existing=set(sa.inspect(op.get_bind()).get_table_names())
    if 'accounts' in existing:
        cols=_columns('accounts')
        if 'source' not in cols: op.add_column('accounts',sa.Column('source',sa.String(),nullable=False,server_default='app'))
        if 'is_test_account' not in cols: op.add_column('accounts',sa.Column('is_test_account',sa.Boolean(),nullable=False,server_default=sa.false()))
        if 'test_run_id' not in cols:
            op.add_column('accounts',sa.Column('test_run_id',sa.String(),nullable=True))
            op.create_index('ix_accounts_test_run_id','accounts',['test_run_id'])
    if 'circles' in existing:
        cols=_columns('circles')
        if 'source' not in cols: op.add_column('circles',sa.Column('source',sa.String(),nullable=False,server_default='app'))
        if 'is_test_data' not in cols: op.add_column('circles',sa.Column('is_test_data',sa.Boolean(),nullable=False,server_default=sa.false()))
        if 'test_run_id' not in cols:
            op.add_column('circles',sa.Column('test_run_id',sa.String(),nullable=True))
            op.create_index('ix_circles_test_run_id','circles',['test_run_id'])
    if 'degraded_operations' not in existing:
        op.create_table(
            'degraded_operations',
            sa.Column('id',sa.String(),primary_key=True,nullable=False),
            sa.Column('operation_type',sa.String(),nullable=False),
            sa.Column('aggregate_type',sa.String(),nullable=False),
            sa.Column('aggregate_id',sa.String(),nullable=True),
            sa.Column('payload',sa.JSON(),nullable=False),
            sa.Column('idempotency_key',sa.String(),nullable=False,unique=True),
            sa.Column('sequence',sa.Integer(),nullable=False),
            sa.Column('sync_status',sa.String(),nullable=False),
            sa.Column('retry_count',sa.Integer(),nullable=False),
            sa.Column('last_error',sa.String(),nullable=True),
            sa.Column('result',sa.String(),nullable=True),
            sa.Column('created_at',sa.String(),nullable=False),
            sa.Column('synced_at',sa.String(),nullable=True),
        )
        op.create_index('ix_degraded_operations_sequence','degraded_operations',['sequence'])
        op.create_index('ix_degraded_operations_sync_status','degraded_operations',['sync_status'])
    if 'degraded_operation_receipts' not in existing:
        op.create_table(
            'degraded_operation_receipts',
            sa.Column('idempotency_key',sa.String(),primary_key=True,nullable=False),
            sa.Column('event_id',sa.String(),nullable=False),
            sa.Column('applied_at',sa.String(),nullable=False),
        )


def downgrade():
    existing=set(sa.inspect(op.get_bind()).get_table_names())
    if 'degraded_operation_receipts' in existing: op.drop_table('degraded_operation_receipts')
    if 'degraded_operations' in existing:
        op.drop_index('ix_degraded_operations_sync_status',table_name='degraded_operations')
        op.drop_index('ix_degraded_operations_sequence',table_name='degraded_operations')
        op.drop_table('degraded_operations')
    if 'circles' in existing:
        cols=_columns('circles')
        if 'test_run_id' in cols:
            op.drop_index('ix_circles_test_run_id',table_name='circles');op.drop_column('circles','test_run_id')
        if 'is_test_data' in cols: op.drop_column('circles','is_test_data')
        if 'source' in cols: op.drop_column('circles','source')
    if 'accounts' in existing:
        cols=_columns('accounts')
        if 'test_run_id' in cols:
            op.drop_index('ix_accounts_test_run_id',table_name='accounts');op.drop_column('accounts','test_run_id')
        if 'is_test_account' in cols: op.drop_column('accounts','is_test_account')
        if 'source' in cols: op.drop_column('accounts','source')
