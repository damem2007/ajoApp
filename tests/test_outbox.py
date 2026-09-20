from datetime import date
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session

from app.platform.models import Base, OutboxEvent, WorkerReceipt, Due, Account
from app.platform.outbox import emit, dispatch_pending
from app.platform.scheduler import enqueue_due_scan


def test_outbox_emit_is_idempotent_and_dispatch_retries_safely():
    engine=create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    published=[]
    with Session(engine) as db,db.begin():
        first=emit(
            db,
            event_type='notification.dispatch',
            aggregate_type='notice',
            aggregate_id='n-1',
            idempotency_key='notification:n-1',
            payload={'notice_id':'n-1'},
        )
        second=emit(
            db,
            event_type='notification.dispatch',
            aggregate_type='notice',
            aggregate_id='n-1',
            idempotency_key='notification:n-1',
            payload={'notice_id':'n-1'},
        )
        assert first.id==second.id
    with Session(engine) as db,db.begin():
        assert dispatch_pending(db,lambda event: published.append(event.id))==1
        event=db.scalar(select(OutboxEvent))
        assert event.status=='published'
        assert event.attempt_count==1
    with Session(engine) as db,db.begin():
        assert dispatch_pending(db,lambda event: published.append(event.id))==1
        event=db.scalar(select(OutboxEvent))
        assert event.attempt_count==2
    assert published==[published[0],published[0]]


def test_scheduler_uses_hour_bucket_idempotency():
    engine=create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    with Session(engine) as db,db.begin():
        db.add(Due(
            id='due-1',
            circle_id='circle-1',
            user_id='user-1',
            business_key='contribution:1',
            window=0,
            kind='contribution',
            date=date.today().isoformat(),
            amount_minor=100,
            status='Scheduled',
        ))
    with Session(engine) as db,db.begin():
        assert enqueue_due_scan(db,date.today())==1
        assert enqueue_due_scan(db,date.today())==1
        assert db.scalar(select(func.count()).select_from(OutboxEvent))==1


def test_domain_and_outbox_commit_are_atomic():
    engine=create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db,db.begin():
            db.add(Account(id='atomic-user',email='atomic@example.test',phone='+15555550123',password='hash'))
            emit(
                db,
                event_type='notification.dispatch',
                aggregate_type='account',
                aggregate_id='atomic-user',
                idempotency_key='atomic:rollback',
                payload={'notice_id':'missing'},
            )
            raise RuntimeError('force rollback')
    except RuntimeError:
        pass
    with Session(engine) as db:
        assert db.get(Account,'atomic-user') is None
        assert db.scalar(select(func.count()).select_from(OutboxEvent))==0


def test_worker_receipt_prevents_duplicate_scan_execution():
    from app.platform.workers import process_scan_event
    from app.platform.services import seed_policy
    class Context: pass
    engine=create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    with Session(engine) as db,db.begin():
        seed_policy(db,True)
        event=emit(
            db,
            event_type='payment.scan',
            aggregate_type='payment_schedule',
            aggregate_id=date.today().isoformat(),
            idempotency_key='worker:idempotency',
            payload={'as_of':date.today().isoformat()},
        )
        event_id=event.id
    with Session(engine) as db,db.begin():
        assert process_scan_event(db,Context(),event_id)=='processed'
    with Session(engine) as db,db.begin():
        assert process_scan_event(db,Context(),event_id)=='already_processed'
        assert db.scalar(select(func.count()).select_from(WorkerReceipt))==1
