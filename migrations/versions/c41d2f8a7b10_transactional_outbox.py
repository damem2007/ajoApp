"""Transactional outbox and idempotent worker receipts."""
from alembic import op
import sqlalchemy as sa

revision = 'c41d2f8a7b10'
down_revision = '938fa45d0182'
branch_labels = None
depends_on = None


def upgrade():
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    if 'outbox_events' not in existing:
        op.create_table(
            'outbox_events',
            sa.Column('id', sa.String(), primary_key=True, nullable=False),
            sa.Column('event_type', sa.String(), nullable=False),
            sa.Column('aggregate_type', sa.String(), nullable=False),
            sa.Column('aggregate_id', sa.String(), nullable=False),
            sa.Column('idempotency_key', sa.String(), nullable=False),
            sa.Column('payload', sa.JSON(), nullable=False),
            sa.Column('status', sa.String(), nullable=False),
            sa.Column('attempt_count', sa.Integer(), nullable=False),
            sa.Column('last_error', sa.String(), nullable=True),
            sa.Column('created_at', sa.String(), nullable=False),
            sa.Column('published_at', sa.String(), nullable=True),
            sa.Column('completed_at', sa.String(), nullable=True),
            sa.UniqueConstraint('idempotency_key', name='uq_outbox_events_idempotency_key'),
        )
        op.create_index('ix_outbox_events_event_type', 'outbox_events', ['event_type'])
        op.create_index('ix_outbox_events_aggregate_id', 'outbox_events', ['aggregate_id'])
        op.create_index('ix_outbox_events_status', 'outbox_events', ['status'])
    if 'worker_receipts' not in existing:
        op.create_table(
            'worker_receipts',
            sa.Column('event_id', sa.String(), primary_key=True, nullable=False),
            sa.Column('worker', sa.String(), nullable=False),
            sa.Column('completed_at', sa.String(), nullable=False),
        )


def downgrade():
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    if 'worker_receipts' in existing:
        op.drop_table('worker_receipts')
    if 'outbox_events' in existing:
        op.drop_index('ix_outbox_events_status', table_name='outbox_events')
        op.drop_index('ix_outbox_events_aggregate_id', table_name='outbox_events')
        op.drop_index('ix_outbox_events_event_type', table_name='outbox_events')
        op.drop_table('outbox_events')
