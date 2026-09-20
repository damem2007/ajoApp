"""Persisted staff permissions, channels and synchronization evidence (not legacy store tables)."""
from alembic import op
import sqlalchemy as sa
from datetime import datetime, timezone
revision='938fa45d0182'
down_revision='67444298b84c'
branch_labels=None
depends_on=None

def upgrade():
    existing=set(sa.inspect(op.get_bind()).get_table_names())
    if 'notification_channels' not in existing:
        op.create_table('notification_channels',
            sa.Column('id',sa.String(),primary_key=True,nullable=False),
            sa.Column('display_name',sa.String(),nullable=False),
            sa.Column('enabled',sa.Boolean(),nullable=False),
            sa.Column('created_at',sa.String(),nullable=False),
            sa.Column('updated_at',sa.String(),nullable=False),
        )
    if 'staff_roles' not in existing:
        op.create_table('staff_roles',
            sa.Column('id',sa.String(),primary_key=True,nullable=False),
            sa.Column('permissions',sa.JSON(),nullable=False),
            sa.Column('created_at',sa.String(),nullable=False),
        )
    if 'sync_batches' not in existing:
        op.create_table('sync_batches',
            sa.Column('id',sa.String(),primary_key=True,nullable=False),
            sa.Column('sequence',sa.Integer(),nullable=False),
            sa.Column('source',sa.String(),nullable=False),
            sa.Column('changes',sa.JSON(),nullable=False),
            sa.Column('status',sa.String(),nullable=False),
            sa.Column('attempts',sa.Integer(),nullable=False),
            sa.Column('error_code',sa.String(),nullable=True),
            sa.Column('created_at',sa.String(),nullable=False),
            sa.Column('synced_at',sa.String(),nullable=True),
        )
    if 'sync_control' not in existing:
        op.create_table('sync_control',
            sa.Column('id',sa.String(),primary_key=True,nullable=False),
            sa.Column('state',sa.String(),nullable=False),
            sa.Column('detail',sa.String(),nullable=True),
            sa.Column('updated_at',sa.String(),nullable=False),
        )
    if 'sync_receipts' not in existing:
        op.create_table('sync_receipts',
            sa.Column('id',sa.String(),primary_key=True,nullable=False),
            sa.Column('source',sa.String(),nullable=False),
            sa.Column('applied_at',sa.String(),nullable=False),
        )
    if 'staff_invitations' not in existing:
        op.create_table('staff_invitations',
            sa.Column('id',sa.String(),primary_key=True,nullable=False),
            sa.Column('email',sa.String(),nullable=False),
            sa.Column('role_id',sa.String(),sa.ForeignKey('staff_roles.id'),nullable=False),
            sa.Column('token_hash',sa.String(),nullable=False,unique=True),
            sa.Column('expires',sa.BigInteger(),nullable=False),
            sa.Column('status',sa.String(),nullable=False),
            sa.Column('created_by',sa.String(),sa.ForeignKey('accounts.id'),nullable=False),
            sa.Column('accepted_by',sa.String(),sa.ForeignKey('accounts.id'),nullable=True),
            sa.Column('created_at',sa.String(),nullable=False),
        )
    if 'staff_memberships' not in existing:
        op.create_table('staff_memberships',
            sa.Column('user_id',sa.String(),sa.ForeignKey('accounts.id'),primary_key=True,nullable=False),
            sa.Column('role_id',sa.String(),sa.ForeignKey('staff_roles.id'),nullable=False),
            sa.Column('status',sa.String(),nullable=False),
            sa.Column('created_by',sa.String(),nullable=False),
            sa.Column('created_at',sa.String(),nullable=False),
            sa.Column('updated_at',sa.String(),nullable=False),
        )
    bind=op.get_bind()
    stamp=datetime.now(timezone.utc).isoformat()
    roles={'ops': ['circles.manage', 'circles.view', 'content.edit', 'contracts.view', 'members.view', 'metrics.view', 'notifications.manage', 'notifications.view', 'payments.manage', 'payments.view', 'sync.view'], 'compliance': ['audit.view', 'circles.view', 'compliance.manage', 'compliance.view', 'contracts.view', 'members.view', 'metrics.view', 'payments.view', 'support.manage', 'support.view'], 'support': ['circles.view', 'members.view', 'metrics.view', 'notifications.view', 'payments.view', 'support.manage', 'support.view'], 'admin': ['audit.view', 'channels.manage', 'channels.view', 'circles.manage', 'circles.view', 'compliance.manage', 'compliance.view', 'content.edit', 'content.publish', 'contracts.view', 'members.manage', 'members.view', 'metrics.view', 'notifications.manage', 'notifications.view', 'payments.manage', 'payments.view', 'roles.assign', 'settings.manage', 'settings.view', 'support.manage', 'support.view', 'sync.manage', 'sync.view']}
    role=sa.table('staff_roles',sa.column('id',sa.String),sa.column('permissions',sa.JSON),sa.column('created_at',sa.String))
    channel=sa.table('notification_channels',sa.column('id',sa.String),sa.column('display_name',sa.String),sa.column('enabled',sa.Boolean),sa.column('created_at',sa.String),sa.column('updated_at',sa.String))
    for name,grants in roles.items():
        if not bind.execute(sa.select(role.c.id).where(role.c.id==name)).first(): bind.execute(role.insert().values(id=name,permissions=grants,created_at=stamp))
    for name,display in {'in-app': 'In-app', 'email': 'Email', 'sms': 'SMS', 'push': 'Push'}.items():
        if not bind.execute(sa.select(channel.c.id).where(channel.c.id==name)).first(): bind.execute(channel.insert().values(id=name,display_name=display,enabled=True,created_at=stamp,updated_at=stamp))
    account=sa.table('accounts',sa.column('id'),sa.column('role'),sa.column('suspended'))
    member=sa.table('staff_memberships',sa.column('user_id'),sa.column('role_id'),sa.column('status'),sa.column('created_by'),sa.column('created_at'),sa.column('updated_at'))
    for row in bind.execute(sa.select(account).where(account.c.role.in_(roles))):
        if not bind.execute(sa.select(member.c.user_id).where(member.c.user_id==row.id)).first(): bind.execute(member.insert().values(user_id=row.id,role_id=row.role,status='disabled' if row.suspended else 'active',created_by='migration',created_at=stamp,updated_at=stamp))

def downgrade():
    op.drop_table('staff_memberships')
    op.drop_table('staff_invitations')
    op.drop_table('sync_receipts')
    op.drop_table('sync_control')
    op.drop_table('sync_batches')
    op.drop_table('staff_roles')
    op.drop_table('notification_channels')
