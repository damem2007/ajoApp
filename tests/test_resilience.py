"""PostgreSQL-authoritative degraded operation journal tests."""
import pytest
from sqlalchemy import select, create_engine
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError

from app.platform.models import Base, Account, DegradedOperation, DegradedOperationReceipt
from app.platform.security import Vault
from app.platform.resilience import DatabaseRouter
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


def test_primary_write_refreshes_non_authoritative_snapshot(databases):
    with databases.session() as db: db.add(account())
    with Session(databases.secondary) as db: assert db.get(Account,'stable-user')
    assert databases.mode=='postgres'


def test_fallback_records_operation_and_replays_exactly_once(databases,monkeypatch):
    r=databases;original=outage(r,monkeypatch)
    with r.session() as db: db.add(account())
    with Session(r.secondary) as db:
        operation=db.scalar(select(DegradedOperation))
        assert operation.sync_status=='PENDING'
        assert 'member@example.test' not in str(operation.payload)
        operation_id=operation.id
        key=operation.idempotency_key
    monkeypatch.setattr(r.primary,'connect',original)
    results=r.reconcile_pending()
    assert results[0]['result']=='SUCCESS'
    with Session(r.primary) as db:
        assert db.get(Account,'stable-user')
        assert db.get(DegradedOperationReceipt,key)
    with Session(r.secondary) as db,db.begin():
        op=db.get(DegradedOperation,operation_id);op.sync_status='PENDING';op.result=None
    results=r.reconcile_pending()
    assert results[0]['result']=='ALREADY_PROCESSED'
    with Session(r.primary) as db:
        assert len(list(db.scalars(select(Account).where(Account.id=='stable-user'))))==1


def test_conflict_is_quarantined_without_overwrite(databases,monkeypatch):
    r=databases
    with r.session() as db: db.add(account())
    original=outage(r,monkeypatch)
    with r.session() as db: db.get(Account,'stable-user').email='fallback@example.test'
    monkeypatch.setattr(r.primary,'connect',original)
    with Session(r.primary) as db,db.begin(): db.get(Account,'stable-user').email='primary@example.test'
    results=r.reconcile_pending()
    assert results[0]['result']=='CONFLICT'
    with Session(r.secondary) as db:
        assert db.scalar(select(DegradedOperation)).sync_status=='CONFLICT'
    with Session(r.primary) as db:
        assert db.get(Account,'stable-user').email=='primary@example.test'


def test_retryable_database_failure_is_classified(databases,monkeypatch):
    r=databases;original=outage(r,monkeypatch)
    with r.session() as db: db.add(account())
    monkeypatch.setattr(r.primary,'connect',original)
    begin=r.primary.begin
    def failure(): raise OperationalError('BEGIN',None,Exception('temporary'))
    monkeypatch.setattr(r.primary,'begin',failure)
    results=r.reconcile_pending()
    assert results[0]['result']=='FAILED_RETRYABLE'
    monkeypatch.setattr(r.primary,'begin',begin)
    results=r.reconcile_pending()
    assert results[0]['result']=='SUCCESS'


def test_uncertified_fallback_is_rejected(databases,monkeypatch):
    databases.control('unsafe','test')
    outage(databases,monkeypatch)
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as error:
        with databases.session(): pass
    assert error.value.status_code==503
