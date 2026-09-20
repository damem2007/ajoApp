from datetime import date
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session

from app.platform.models import Base, OutboxEvent, Due
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
