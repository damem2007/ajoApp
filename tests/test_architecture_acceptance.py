import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.platform.models import Base, Posting
from app.platform.ledger import post_payment_result
from app.platform.providers import (SandboxPayments, SandboxIdentity, SandboxNotifications, TransferRequest,
    PaymentProvider, IdentityProvider, NotificationProvider)
from app.platform.scheduler import enqueue_reconciliation_scan
from app.platform.outbox import queue_for
from tests.test_full_platform import client, activate


def test_provider_contracts_support_portable_operations():
    payment=SandboxPayments()
    assert isinstance(payment,PaymentProvider)
    assert isinstance(SandboxIdentity(),IdentityProvider)
    assert isinstance(SandboxNotifications(),NotificationProvider)
    result=payment.initiate_transfer(TransferRequest('idem-1',100,'CAD','contribution','sandbox-ok-bank'))
    assert result.status=='Settled'
    assert payment.initiate_transfer(TransferRequest('idem-1',100,'CAD','contribution','sandbox-ok-bank'))==result
    with pytest.raises(ValueError):
        payment.initiate_transfer(TransferRequest('idem-1',200,'CAD','contribution','sandbox-ok-bank'))
    assert payment.get_transfer(reference=result.reference)==result
    assert SandboxIdentity().submit(key='k',identity={},document=b'x',selfie=b'y')['status']=='Pending'
    assert SandboxNotifications().send(key='k',channel='email',destination='a@b.c',title='t',body='b')=='SandboxDelivered'


def test_ledger_posting_is_balanced_and_idempotent():
    engine=create_engine('sqlite:///:memory:');Base.metadata.create_all(engine)
    with Session(engine) as db,db.begin():
        post_payment_result(db,circle_id='c',due_id='d',user_id='u',kind='contribution',event_key='e',amount_minor=500)
        post_payment_result(db,circle_id='c',due_id='d',user_id='u',kind='contribution',event_key='e',amount_minor=500)
    with Session(engine) as db:
        rows=list(db.scalars(select(Posting)))
        assert len(rows)==2
        assert sum(r.amount_minor for r in rows)==0


def test_reconciliation_events_have_dedicated_queue():
    assert queue_for('reconciliation.scan')=='ajo:reconciliation'


def test_degraded_mode_never_executes_external_payment_provider(tmp_path,monkeypatch):
    from app.platform.runtime import Context
    from app.platform.security import Vault
    from app.platform.resilience import DatabaseRouter
    from app.platform.payment_orchestration import PaymentOrchestrationService

    primary=create_engine('sqlite:///'+str(tmp_path/'primary.db'))
    secondary=create_engine('sqlite:///'+str(tmp_path/'secondary.db'))
    Base.metadata.create_all(primary);Base.metadata.create_all(secondary)
    class Ctx:
        router=type('Router',(),{'mode':'sqlite'})()
        payments=SandboxPayments()
    with pytest.raises(RuntimeError):
        PaymentOrchestrationService(Ctx()).initiate(
            key='degraded-payment',amount_minor=100,currency='CAD',
            kind='contribution',bank_token='sandbox-ok-bank')


def test_payment_scan_creates_durable_execution_intent_without_provider_call(client):
    from datetime import date, timedelta
    from sqlalchemy.orm import Session
    from app.platform.payments import enqueue_due
    from app.platform.models import OutboxEvent, Due

    cid,_=activate(client)
    class ExplodingProvider:
        def initiate_transfer(self,*args,**kwargs):
            raise AssertionError('provider must not be called during scan transaction')
    original=client.app.state.ctx.payments
    client.app.state.ctx.payments=ExplodingProvider()
    try:
        with Session(client.app.state.ctx.engine) as db,db.begin():
            result=enqueue_due(db,client.app.state.ctx,date.today()+timedelta(days=40))
            assert result['queued']>0
            assert list(db.scalars(select(OutboxEvent).where(OutboxEvent.event_type=='payment.execute')))
            assert list(db.scalars(select(Due).where(Due.circle_id==cid,Due.status=='Processing')))
    finally:
        client.app.state.ctx.payments=original
