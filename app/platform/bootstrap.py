"""Idempotent bootstrap for required system data only.

No member/demo accounts or circles are created here. The optional Super Admin is
created only from deployment-provided credentials.
"""
from sqlalchemy import select
from app.config import setting, ConfigurationError
from .models import Account, StaffMembership
from .security import password_hash
from .services import audit
from .rbac import assign


def bootstrap_superadmin(db):
    values = {
        'email': setting('SUPERADMIN_EMAIL', required=False),
        'phone': setting('SUPERADMIN_PHONE', required=False),
        'username': setting('SUPERADMIN_USERNAME', required=False),
        'password': setting('SUPERADMIN_PASSWORD', required=False),
    }
    if not any(values.values()):
        return None
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise ConfigurationError('Super Admin bootstrap requires: ' + ', '.join('SUPERADMIN_'+name.upper() for name in missing))
    if len(values['password']) < 12:
        raise ConfigurationError('SUPERADMIN_PASSWORD must contain at least 12 characters')

    email = values['email'].lower()
    existing = db.scalar(select(Account).where((Account.email == email) | (Account.phone == values['phone'])))
    if existing:
        membership = db.get(StaffMembership, existing.id)
        if existing.email != email or existing.phone != values['phone'] or not membership or membership.role_id != 'admin':
            raise ConfigurationError('Super Admin bootstrap identity conflicts with an existing non-admin account')
        return existing

    user = Account(
        email=email,
        phone=values['phone'],
        password=password_hash(values['password']),
        pseudonym=values['username'],
        role='admin',
        email_verified=False,
        phone_verified=False,
        kyc_status='NotSubmitted',
    )
    db.add(user)
    db.flush()
    assign(db, user, 'admin', user)
    audit(db, 'system', user.id, 'superadmin_bootstrapped')
    return user
