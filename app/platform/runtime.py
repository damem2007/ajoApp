import time
from fastapi import Depends, Header
from sqlalchemy import text
from sqlalchemy.orm import Session
from .models import Account, SessionToken
from .security import digest, password_hash
from .services import load_vault,fail,get
from .providers import resolve_provider
from app.config import provider_name, resilience_enabled, setting
from .rbac import permissions
from .resilience import DatabaseRouter
from app.database import make_engine

class Context:
    def __init__(self,engine,sandbox=None):
        self.engine=engine
        self.provider_names={kind: ('sandbox' if sandbox else 'unconfigured') if sandbox is not None else provider_name(kind) for kind in ['payments','identity','notifications']}
        self.sandbox=all(name=='sandbox' for name in self.provider_names.values())
        self.vault=load_vault(self.sandbox)
        self.payments=resolve_provider('payments',self.provider_names['payments'])
        self.identity=resolve_provider('identity',self.provider_names['identity'])
        self.notifications=resolve_provider('notifications',self.provider_names['notifications'])
        self.router=None
        if resilience_enabled() and engine.dialect.name=='postgresql':
            fallback=make_engine(setting('AJO_FALLBACK_DATABASE_URL'))
            if fallback.dialect.name!='sqlite': raise ValueError('Fallback database must be SQLite')
            self.router=DatabaseRouter(engine,fallback,self.vault)
        self.dummy_password=password_hash('nonexistent-account-timing-placeholder')

        def session():
            if not self.vault: fail('Set AJO_KEY_FILE to a mounted encryption key; live providers remain unconfigured',503)
            if self.router:
                with self.router.session() as db: yield db
                return
            with Session(engine) as db:
                if engine.dialect.name=='sqlite': db.execute(text('BEGIN IMMEDIATE'))
                else: db.execute(text('SELECT pg_advisory_xact_lock(714206)'))
                try:
                    yield db;db.commit()
                except Exception:
                    db.rollback();raise
        self.session=session

        def actor(authorization:str=Header(default=''),db=Depends(session)):
            if not authorization.startswith('Bearer '): fail('Bearer token required',401)
            token=db.get(SessionToken,digest(authorization[7:]))
            if not token or token.expires<=time.time(): fail('Session expired',401)
            user=get(db,Account,token.user_id)
            if user.suspended: fail('Account suspended',403)
            return user
        self.actor=actor

    def require_permission(self,permission):
        def check(user=Depends(self.actor),db=Depends(self.session)):
            if permission not in permissions(db,user): fail('Permission required: '+permission,403)
            if not self.sandbox and not user.mfa_enabled: fail('Staff MFA required',403)
            return user
        return check

    def staff(self,*roles):
        # Compatibility entry point, backed by persisted membership.
        def check(user=Depends(self.actor),db=Depends(self.session)):
            from .models import StaffMembership
            membership=db.get(StaffMembership,user.id)
            if not membership or membership.status!='active' or membership.role_id not in roles: fail('Staff permission required',403)
            if not self.sandbox and not user.mfa_enabled: fail('Staff MFA required',403)
            return user
        return check

    def canonical_available(self):
        return not self.router or self.router.primary_available()

    def require_canonical(self):
        if not self.canonical_available():
            fail('PostgreSQL is temporarily unavailable; external provider operations are paused until reconciliation',503)

    def ensure_configured(self,kind):
        if self.provider_names[kind]=='unconfigured': fail(kind.capitalize()+' integration adapter is not implemented',503)

    def require_sandbox(self,kind='payments'):
        if self.provider_names[kind]!='sandbox': fail('This testing operation requires a simulated '+kind+' provider',403)
