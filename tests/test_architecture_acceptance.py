import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.platform.models import Base, Posting
from app.platform.ledger import post_payment_result
from app.platform.providers import SandboxPayments, SandboxIdentity, SandboxNotifications, TransferRequest
from app.platform.scheduler import enqueue_reconciliation_scan
from app.platform.outbox import queue_for


def test_provider_contracts_support_portable_operations():
    payment=SandboxPayments()
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
