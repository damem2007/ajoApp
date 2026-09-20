"""Redis-backed workers for durable outbox events."""
from __future__ import annotations

import logging
import time
from datetime import date

from .models import OutboxEvent, WorkerReceipt, now
from .payments import run_due, dispatch_notices
from .payment_orchestration import reconcile_pending_payments
from .outbox import queue_for

log=logging.getLogger('ajo.worker')

WORKER_EVENT_PREFIX = {
    'payment': 'payment.',
    'notification': 'notification.',
    'reconciliation': 'reconciliation.',
}


def process_event(db, ctx, event_id: str, worker: str) -> str:
    receipt=db.get(WorkerReceipt,event_id)
    if receipt:
        event=db.get(OutboxEvent,event_id)
        if event and event.status!='completed':
            event.status='completed';event.completed_at=receipt.completed_at
        return 'already_processed'

    event=db.get(OutboxEvent,event_id)
    if not event: return 'missing'
    expected=WORKER_EVENT_PREFIX[worker]
    if not event.event_type.startswith(expected): return 'wrong_worker'

    if event.event_type=='payment.scan':
        run_due(db,ctx,date.fromisoformat(event.payload['as_of']))
    elif event.event_type=='notification.dispatch':
        dispatch_notices(db,ctx,event.payload['notice_id'])
    elif event.event_type=='reconciliation.scan':
        # Provider reconciliation is safe only after the canonical database is
        # available. SQLite journal replay itself uses a separate transaction.
        if ctx.router:
            results=ctx.router.reconcile_pending()
            if any(r['result'] in {'CONFLICT','INVALID','FAILED_PERMANENT','FAILED_RETRYABLE'} for r in results):
                raise RuntimeError('Reconciliation did not complete cleanly')
        reconcile_pending_payments(db,ctx)
    else:
        raise ValueError('Unsupported outbox event type')

    stamp=now()
    db.add(WorkerReceipt(event_id=event.id,worker=worker,completed_at=stamp))
    event.status='completed';event.completed_at=stamp;event.last_error=None
    log.info('worker=%s event_id=%s status=completed',worker,event_id)
    return 'processed'


class RedisConsumer:
    def __init__(self,url):
        from redis import Redis
        self.client=Redis.from_url(url,decode_responses=True)

    def next_event(self,worker,timeout=5):
        item=self.client.blpop(queue_for(WORKER_EVENT_PREFIX[worker]),timeout=timeout)
        return item[1] if item else None

    def close(self): self.client.close()


def worker_loop(ctx,worker,redis_url,*,once=False):
    if worker not in WORKER_EVENT_PREFIX: raise ValueError('Unknown worker')
    consumer=RedisConsumer(redis_url)
    try:
        while True:
            event_id=consumer.next_event(worker,timeout=1 if once else 5)
            if not event_id:
                if once:return
                continue
            gen=None
            try:
                gen=ctx.session();db=next(gen)
                process_event(db,ctx,event_id,worker)
                try: next(gen)
                except StopIteration: pass
            except Exception as exc:
                if gen:
                    try: gen.close()
                    except Exception: pass
                log.warning('worker=%s event_id=%s error=%s',worker,event_id,type(exc).__name__)
                # Keep the durable event retryable.
                try:
                    gen2=ctx.session();db2=next(gen2)
                    event=db2.get(OutboxEvent,event_id)
                    if event:
                        event.status='failed';event.last_error=type(exc).__name__;event.attempt_count+=1
                    try: next(gen2)
                    except StopIteration: pass
                except Exception:
                    pass
                if once: raise
                time.sleep(1)
            if once:return
    finally:
        consumer.close()
