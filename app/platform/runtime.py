import time
from fastapi import Depends, Header
from sqlalchemy import text
from sqlalchemy.orm import Session
from .models import Account, SessionToken
from .security import digest, password_hash
from .services import load_vault,fail,get
from .providers import SandboxPayments,SandboxIdentity,SandboxNotifications,UnconfiguredProvider

class Context:
    def __init__(self,engine,sandbox):
        self.engine=engine;self.sandbox=sandbox;self.vault=load_vault(sandbox)
        self.payments=SandboxPayments() if sandbox else UnconfiguredProvider()
        self.identity=SandboxIdentity() if sandbox else UnconfiguredProvider()
        self.notifications=SandboxNotifications() if sandbox else UnconfiguredProvider()
        self.dummy_password=password_hash('nonexistent-account-timing-placeholder')

        def session():
            if not self.vault: fail('Set AJO_KEY_FILE to a mounted encryption key; live providers remain unconfigured',503)
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

    def staff(self,*roles):
        def check(user=Depends(self.actor)):
            if user.role not in roles: fail('Staff permission required',403)
            if not self.sandbox and not user.mfa_enabled: fail('Staff MFA required',403)
            return user
        return check

    def require_sandbox(self):
        if not self.sandbox: fail('Sandbox-only operation; live adapter is not configured',503)
