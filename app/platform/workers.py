"""Redis-backed workers for outbox events.

All worker processes use the same FastAPI application context and database
models. They are deployment processes, not separate services or codebases.
"""
from __future__ import annotations

import time
from datetime import date
from sqlalchemy import select
from .models import OutboxEvent, WorkerReceipt, now
from .payments import run_due, dispatch_notices
from .outbox import queue_for


WORKER_EVENT_PREFIX = {
    'payment': 'payment.',
    'notification': 'notification.',
}


def process_event(db, ctx, event_id: str, worker: str) -> str:
    receipt = db.get(WorkerReceipt, event_id)
    if receipt:
        event = db.get(OutboxEvent, event_id)
        if event and event.status != 'completed':
            event.status = 'completed'
            event.completed_at = receipt.completed_at
        return 'already_processed'

    event = db.get(OutboxEvent, event_id)
    if not event:
        return 'missing'

    expected = WORKER_EVENT_PREFIX[worker]
    if not event.event_type.startswith(expected):
        return 'wrong_worker'

    if event.event_type == 'payment.scan':
        run_due(db, ctx, date.fromisoformat(event.payload['as_of']))
    elif event.event_type == 'notification.dispatch':
        dispatch_notices(db, ctx, event.payload['notice_id'])
    else:
        raise ValueError('Unsupported outbox event type')

    stamp = now()
    db.add(WorkerReceipt(event_id=event.id, worker=worker, completed_at=stamp))
    event.status = 'completed'
    event.completed_at = stamp
    event.last_error = None
    return 'processed'


class RedisConsumer:
    def __init__(self, url: str):
        from redis import Redis
        self.client = Redis.from_url(url, decode_responses=True)

    def next_event(self, worker: str, timeout: int = 5) -> str | None:
        queue = queue_for(WORKER_EVENT_PREFIX[worker])
        item = self.client.blpop(queue, timeout=timeout)
        return item[1] if item else None

    def close(self) -> None:
        self.client.close()


def worker_loop(ctx, worker: str, redis_url: str, *, once: bool = False) -> None:
    consumer = RedisConsumer(redis_url)
    try:
        while True:
            event_id = consumer.next_event(worker, timeout=1 if once else 5)
            if not event_id:
                if once:
                    return
                continue
            try:
                gen = ctx.session()
                db = next(gen)
                process_event(db, ctx, event_id, worker)
                try:
                    next(gen)
                except StopIteration:
                    pass
            except Exception as exc:
                try:
                    gen.close()
                except Exception:
                    pass
                # Keep the outbox row incomplete so the dispatcher can publish it again.
                gen2 = ctx.session()
                db2 = next(gen2)
                event = db2.get(OutboxEvent, event_id)
                if event:
                    event.status = 'failed'
                    event.last_error = type(exc).__name__
                try:
                    next(gen2)
                except StopIteration:
                    pass
                if once:
                    raise
                time.sleep(1)
            if once:
                return
    finally:
        consumer.close()
