from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.platform.models import Base, OutboxEvent
from app.platform.outbox import enqueue, publish_pending
from app.platform.scheduler import schedule_once


class Context:
    def __init__(self, engine):
        self.engine = engine

    @contextmanager
    def session(self):
        with Session(self.engine) as db:
            try:
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise


class FakeRedis:
    def __init__(self, fail=False):
        self.fail = fail
        self.items = []

    def rpush(self, queue, event_id):
        if self.fail:
            raise ConnectionError("offline")
        self.items.append((queue, event_id))


def context():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Context(engine)


def test_enqueue_is_idempotent_and_dispatches_only_event_ids():
    ctx = context()
    with ctx.session() as db:
        first = enqueue(
            db,
            event_type="payment.run_due",
            aggregate_type="system",
            aggregate_id=None,
            payload={"secret": "stays-in-db"},
            idempotency_key="test:payment:1",
        )
        second = enqueue(
            db,
            event_type="payment.run_due",
            aggregate_type="system",
            aggregate_id=None,
            payload={"secret": "different"},
            idempotency_key="test:payment:1",
        )
        assert first.id == second.id

    redis = FakeRedis()
    result = publish_pending(ctx, redis_client=redis)
    assert result == {"published": 1, "failed": 0}
    assert redis.items == [("ajo:payment", first.id)]

    with Session(ctx.engine) as db:
        rows = list(db.scalars(select(OutboxEvent)))
        assert len(rows) == 1
        assert rows[0].payload == {"secret": "stays-in-db"}
        assert rows[0].status == "published"


def test_redis_failure_keeps_event_retryable():
    ctx = context()
    with ctx.session() as db:
        event = enqueue(
            db,
            event_type="notification.dispatch",
            aggregate_type="system",
            aggregate_id=None,
            idempotency_key="test:notification:1",
        )
        event_id = event.id

    result = publish_pending(ctx, redis_client=FakeRedis(fail=True))
    assert result == {"published": 0, "failed": 1}
    with Session(ctx.engine) as db:
        event = db.get(OutboxEvent, event_id)
        assert event.status == "retry"
        assert event.last_error == "ConnectionError"


def test_scheduler_uses_minute_bucket_idempotency():
    ctx = context()
    instant = datetime(2026, 9, 20, 18, 30, tzinfo=timezone.utc)
    first = schedule_once(ctx, now=instant)
    second = schedule_once(ctx, now=instant)
    assert first == second

    with Session(ctx.engine) as db:
        events = list(db.scalars(select(OutboxEvent).order_by(OutboxEvent.event_type)))
        assert len(events) == 3
        assert {event.event_type for event in events} == {
            "payment.run_due",
            "notification.dispatch",
            "reconciliation.run",
        }
