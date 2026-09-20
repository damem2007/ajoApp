"""Database routing state-machine tests; SQLite engines model transaction boundaries.
A deployment smoke test separately validates actual PostgreSQL compatibility.
"""
import pytest
from sqlalchemy import select, create_engine
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError
from app.platform.models import Base, Account, SyncBatch, SyncReceipt
from app.platform.security import Vault
from app.platform.resilience import DatabaseRouter, SyncConflict
from app.platform.services import seed_policy
from app.platform.rbac import bootstrap

@pytest.fixture
def databases(tmp_path):
    primary=create_engine('sqlite:///'+str(tmp_path/'primary.db'))
    secondary=create_engine('sqlite:///'+str(tmp_path/'secondary.db'))
    for engine in [primary,secondary]: Base.metadata.create_all(engine)
    with Session(primary) as db,db.begin(): seed_policy(db,True);bootstrap(db)
    router=DatabaseRouter(primary,secondary,Vault(b'x'*32));router.bootstrap()
    yield router
    primary.dispose();secondary.dispose()


def outage(router,monkeypatch):
    original=router.primary.connect
    def unavailable(*args,**kwargs): raise OperationalError('SELECT 1',None,Exception('offline'))
    monkeypatch.setattr(router.primary,'connect',unavailable)
    return original


def account(email='member@example.test'):
    return Account(id='stable-user',email=email,phone='+15555550100',password='fixture-hash')


def test_primary_write_updates_certified_mirror(databases):
    r=databases
    with r.session() as db: db.add(account())
    with Session(r.secondary) as db: assert db.get(Account,'stable-user')
    assert r.mode=='postgres'


def test_fallback_write_restart_recovery_duplicate_replay(databases,monkeypatch):
    r=databases;original=outage(r,monkeypatch)
    with r.session() as db: db.add(account())
    assert r.mode=='sqlite'
    with Session(r.secondary) as db:
        batch=db.scalar(select(SyncBatch));assert batch.status=='pending'
        assert 'member@example.test' not in str(batch.changes)
        batch_id=batch.id
    restarted=DatabaseRouter(r.primary,r.secondary,r.vault)
    monkeypatch.setattr(r.primary,'connect',original)
    with restarted.session() as db: assert db.get(Account,'stable-user')
    with Session(r.secondary) as db,db.begin(): db.get(SyncBatch,batch_id).status='pending'
    restarted.replay(r.secondary,r.primary)
    with Session(r.primary) as db:
        assert len(list(db.scalars(select(Account))))==1
        assert db.get(SyncReceipt,batch_id)
    with Session(r.secondary) as db: assert db.get(SyncBatch,batch_id).status=='synced'


def test_conflicting_independent_change_blocks_recovery(databases,monkeypatch):
    r=databases
    with r.session() as db: db.add(account())
    original=outage(r,monkeypatch)
    with r.session() as db: db.get(Account,'stable-user').email='fallback@example.test'
    monkeypatch.setattr(r.primary,'connect',original)
    with Session(r.primary) as db,db.begin(): db.get(Account,'stable-user').email='primary@example.test'
    with pytest.raises(SyncConflict): r.replay(r.secondary,r.primary)
    with Session(r.secondary) as db: assert db.scalar(select(SyncBatch)).status=='conflict'
    with Session(r.primary) as db: assert db.get(Account,'stable-user').email=='primary@example.test'


def test_failed_replay_retry_and_tombstone(databases,monkeypatch):
    r=databases
    with r.session() as db: db.add(account())
    original=outage(r,monkeypatch)
    with r.session() as db: db.delete(db.get(Account,'stable-user'))
    monkeypatch.setattr(r.primary,'connect',original)
    begin=r.primary.begin
    def failure(): raise RuntimeError('temporary replay failure')
    monkeypatch.setattr(r.primary,'begin',failure)
    with pytest.raises(RuntimeError): r.replay(r.secondary,r.primary)
    with Session(r.secondary) as db: assert db.scalar(select(SyncBatch)).status=='failed'
    monkeypatch.setattr(r.primary,'begin',begin)
    r.replay(r.secondary,r.primary)
    with Session(r.primary) as db: assert db.get(Account,'stable-user') is None


def test_uncertified_fallback_rejected(databases,monkeypatch):
    r=databases;r.control('unsafe');outage(r,monkeypatch)
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as error:
        with r.session(): pass
    assert error.value.status_code==503


def test_bulk_session_delete_survives_replay(databases,monkeypatch):
    from sqlalchemy import delete
    from app.platform.models import SessionToken
    r=databases
    with r.session() as db:
        db.add(account());db.flush()
        db.add(SessionToken(token_hash='token',user_id='stable-user',refresh_hash='refresh',expires=9999999999,refresh_expires=9999999999))
    original=outage(r,monkeypatch)
    with r.session() as db: db.execute(delete(SessionToken).where(SessionToken.user_id=='stable-user'))
    monkeypatch.setattr(r.primary,'connect',original)
    r.replay(r.secondary,r.primary)
    with Session(r.primary) as db: assert db.get(SessionToken,'token') is None


def test_restart_detects_untracked_primary_divergence(databases):
    r=databases
    with Session(r.primary) as db,db.begin(): db.add(account())
    restarted=DatabaseRouter(r.primary,r.secondary,r.vault)
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as error:
        with restarted.session(): pass
    assert error.value.status_code==503
    with Session(r.secondary) as db:
        from app.platform.models import SyncControl
        assert db.get(SyncControl,'mirror').detail=='mirror_diverged'
