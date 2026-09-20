"""Add generic transactional outbox events.

Revision ID: 4d2c8a1e9f31
Revises: 938fa45d0182
"""
from alembic import op
import sqlalchemy as sa

revision = "4d2c8a1e9f31"
down_revision = "938fa45d0182"
branch_labels = None
depends_on = None


def upgrade():
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    if "outbox_events" in existing:
        return
    op.create_table(
        "outbox_events",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("aggregate_type", sa.String(), nullable=False),
        sa.Column("aggregate_id", sa.String(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(), nullable=False, unique=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("published_at", sa.String(), nullable=True),
        sa.Column("completed_at", sa.String(), nullable=True),
        sa.Column("last_error", sa.String(), nullable=True),
    )
    op.create_index("ix_outbox_events_event_type", "outbox_events", ["event_type"])
    op.create_index("ix_outbox_events_status", "outbox_events", ["status"])


def downgrade():
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    if "outbox_events" in existing:
        op.drop_index("ix_outbox_events_status", table_name="outbox_events")
        op.drop_index("ix_outbox_events_event_type", table_name="outbox_events")
        op.drop_table("outbox_events")
