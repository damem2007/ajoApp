"""Persisted role grants and staff membership; one existing account identity."""
from sqlalchemy import select
from .models import StaffRole, StaffMembership, NotificationChannel, Account, now

COMMON = {'members.view', 'circles.view', 'metrics.view'}
ROLE_PERMISSIONS = {
    'ops': COMMON | {'payments.view','payments.manage','circles.manage','notifications.view','notifications.manage','content.edit','contracts.view','sync.view'},
    'compliance': COMMON | {'compliance.view','compliance.manage','support.view','support.manage','contracts.view','audit.view','payments.view'},
    'support': COMMON | {'support.view','support.manage','payments.view','notifications.view'},
}
ROLE_PERMISSIONS['admin'] = set().union(*ROLE_PERMISSIONS.values()) | {'members.manage','roles.assign','settings.view','settings.manage','channels.view','channels.manage','content.publish','sync.manage'}
CHANNELS = {'in-app':'In-app','email':'Email','sms':'SMS','push':'Push'}


def bootstrap(db):
    for name, permissions in ROLE_PERMISSIONS.items():
        if not db.get(StaffRole,name):
            db.add(StaffRole(id=name,permissions=sorted(permissions)))
    for name, display in CHANNELS.items():
        if not db.get(NotificationChannel,name):
            db.add(NotificationChannel(id=name,display_name=display,enabled=True))
    db.flush()
    for account in db.scalars(select(Account).where(Account.role.in_(ROLE_PERMISSIONS))):
        if not db.get(StaffMembership,account.id):
            db.add(StaffMembership(user_id=account.id,role_id=account.role,status='disabled' if account.suspended else 'active',created_by='migration'))
    db.flush()


def permissions(db, user):
    if user.suspended: return set()
    membership = db.get(StaffMembership,user.id)
    if not membership or membership.status != 'active': return set()
    role = db.get(StaffRole,membership.role_id)
    return set(role.permissions) if role else set()


def has_permission(db,user,permission):
    return permission in permissions(db,user)


def assign(db,user,role,actor):
    from .services import fail
    if role != 'member' and not db.get(StaffRole,role): fail('Unsupported role',422)
    membership=db.get(StaffMembership,user.id)
    if role=='member':
        if membership: membership.status='disabled';membership.updated_at=now()
    elif membership:
        membership.role_id=role;membership.status='disabled' if user.suspended else 'active';membership.updated_at=now()
    else:
        db.add(StaffMembership(user_id=user.id,role_id=role,status='active',created_by=actor.id))
    user.role=role
