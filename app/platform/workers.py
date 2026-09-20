"""Redis-backed workers for durable outbox events.

Provider calls are deliberately executed outside database transactions. Durable
intent is committed first; worker receipts and provider results are committed in
a later transaction. Redis delivery is at-least-once, so provider idempotency
keys and WorkerReceipt protect against duplicate effects.
"""
from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from datetime import date, timedelta

from sqlalchemy import select

from .models import (
    OutboxEvent, WorkerReceipt, PaymentEvent, Due, Circle, Contract, Bank,
    Notice, NotificationChannel, Account, now,
)
from .payments import enqueue_due, apply_result, complete
from .payment_orchestration import PaymentOrchestrationService, reconcile_pending_payments
from .outbox import queue_for
from .services import get

log=logging.getLogger('ajo.worker')

WORKER_EVENT_PREFIX = {
    'payment': 'payment.',
    'notification': 'notification.',
    'reconciliation': 'reconciliation.',
}


@contextmanager
def _session(ctx):
    gen=ctx.session();db=next(gen)
    try:
        yield db
    except Exception:
        gen.close()
        raise
    else:
        try: next(gen)
        except StopIteration: pass


def _finish(db,event,worker):
    receipt=db.get(WorkerReceipt,event.id)
    if not receipt:
        receipt=WorkerReceipt(event_id=event.id,worker=worker,completed_at=now())
        db.add(receipt)
    event.status='completed';event.completed_at=receipt.completed_at;event.last_error=None


def _event_type(ctx,event_id):
    with _session(ctx) as db:
        event=db.get(OutboxEvent,event_id)
        if not event: return None
        if db.get(WorkerReceipt,event_id):
            if event.status!='completed': _finish(db,event,'receipt')
            return 'completed'
        return event.event_type


def process_scan_event(db,ctx,event_id):
    """Transactional payment scan: create durable payment.execute intentions only."""
    receipt=db.get(WorkerReceipt,event_id)
    event=db.get(OutboxEvent,event_id)
    if receipt:
        if event and event.status!='completed': _finish(db,event,'payment')
        return 'already_processed'
    if not event: return 'missing'
    if event.event_type!='payment.scan': return 'wrong_worker'
    enqueue_due(db,ctx,date.fromisoformat(event.payload['as_of']))
    _finish(db,event,'payment')
    return 'processed'


def execute_payment_event(ctx,event_id):
    """Execute one provider transfer outside any open application transaction."""
    with _session(ctx) as db:
        receipt=db.get(WorkerReceipt,event_id)
        event=db.get(OutboxEvent,event_id)
        if receipt:
            if event and event.status!='completed': _finish(db,event,'payment')
            return 'already_processed'
        if not event: return 'missing'
        if event.event_type!='payment.execute': return 'wrong_worker'
        due=get(db,Due,event.payload['due_id'])
        result_key=event.payload['payment_key']+':result'
        existing=db.scalar(select(PaymentEvent).where(PaymentEvent.key==result_key))
        if existing:
            _finish(db,event,'payment')
            return 'already_processed'
        circle=get(db,Circle,due.circle_id)
        bank=db.scalar(select(Bank).where(
            Bank.user_id==due.user_id,Bank.status=='Verified',Bank.mandate==True
        ).order_by(Bank.id))
        if not bank:
            raise RuntimeError('Verified payment account disappeared before execution')
        request=dict(
            key=event.payload['payment_key'],
            amount_minor=due.amount_minor,
            currency=circle.config['currency'],
            kind=due.kind,
            bank_token=ctx.vault.open(bank.encrypted_token),
        )
        as_of=date.fromisoformat(event.payload['as_of'])

    result=PaymentOrchestrationService(ctx).initiate(**request)

    with _session(ctx) as db:
        event=db.get(OutboxEvent,event_id)
        if not event: return 'missing'
        if db.get(WorkerReceipt,event_id):
            return 'already_processed'
        due=get(db,Due,event.payload['due_id'])
        result_key=event.payload['payment_key']+':result'
        existing=db.scalar(select(PaymentEvent).where(PaymentEvent.key==result_key))
        if not existing:
            due.provider_ref=result.reference
            apply_result(db,due,result.status,result_key,result.detail)
            if result.status=='Failed':
                circle=get(db,Circle,due.circle_id)
                p=get(db,Contract,circle.contract_id).content['policy']
                due.next_attempt=(as_of+timedelta(days=p['retry_days']*2**max(0,due.attempts-1))).isoformat()
            complete(db,get(db,Circle,due.circle_id))
        _finish(db,event,'payment')
    log.info('worker=payment event_id=%s payment_id=%s provider_reference=%s status=%s',
             event_id,request['key'],result.reference,result.status)
    return 'processed'


def execute_notification_event(ctx,event_id):
    """Deliver one notification outside the database transaction."""
    with _session(ctx) as db:
        event=db.get(OutboxEvent,event_id)
        if not event: return 'missing'
        if db.get(WorkerReceipt,event_id):
            _finish(db,event,'notification')
            return 'already_processed'
        if event.event_type!='notification.dispatch': return 'wrong_worker'
        notice=db.get(Notice,event.payload['notice_id'])
        if not notice or notice.status not in {'Queued','Failed'} or notice.attempts>=5:
            _finish(db,event,'notification')
            return 'skipped'
        channel=db.get(NotificationChannel,notice.channel)
        if not channel or not channel.enabled:
            _finish(db,event,'notification')
            return 'channel_disabled'
        user=get(db,Account,notice.user_id)
        destination=user.email if notice.channel=='email' else user.phone if notice.channel=='sms' else user.preferences.get('push_token','')
        if notice.channel=='push' and not destination:
            notice.status='NoDestination';_finish(db,event,'notification')
            return 'no_destination'
        body=ctx.vault.open(notice.body) if notice.title=='Verification code' else notice.body
        if notice.title=='Staff invitation':
            destination,token=ctx.vault.open(notice.body).split('\n',1)
            body='Accept your staff invitation in Ajo using this one-time code: '+token
        if notice.channel=='push': destination=ctx.vault.open(destination)
        delivery=dict(key=notice.key,channel=notice.channel,destination=destination,title=notice.title,body=body)

    try:
        status=ctx.notifications.send(**delivery)
    except Exception:
        with _session(ctx) as db:
            notice=db.get(Notice,event.payload['notice_id'])
            if notice:
                notice.attempts+=1;notice.status='Failed'
        raise

    with _session(ctx) as db:
        event=db.get(OutboxEvent,event_id)
        if not event: return 'missing'
        if db.get(WorkerReceipt,event_id): return 'already_processed'
        notice=db.get(Notice,event.payload['notice_id'])
        if notice:
            notice.attempts+=1;notice.status=status
        _finish(db,event,'notification')
    log.info('worker=notification event_id=%s status=%s',event_id,status)
    return 'processed'


def execute_reconciliation_event(ctx,event_id):
    """Reconcile SQLite journal and provider state, then receipt the durable event."""
    if ctx.router:
        results=ctx.router.reconcile_pending()
        if any(r['result'] in {'CONFLICT','INVALID','FAILED_PERMANENT','FAILED_RETRYABLE'} for r in results):
            raise RuntimeError('Reconciliation did not complete cleanly')

    provider_result=reconcile_pending_payments(ctx)

    with _session(ctx) as db:
        event=db.get(OutboxEvent,event_id)
        if not event: return 'missing'
        if db.get(WorkerReceipt,event_id): return 'already_processed'
        if event.event_type!='reconciliation.scan': return 'wrong_worker'
        _finish(db,event,'reconciliation')
    log.info('worker=reconciliation event_id=%s provider_checked=%s provider_updated=%s',
             event_id,provider_result['checked'],provider_result['updated'])
    if provider_result['failed']:
        raise RuntimeError('One or more provider reconciliation checks failed')
    return 'processed'


def _mark_failed(ctx,event_id,error):
    try:
        with _session(ctx) as db:
            event=db.get(OutboxEvent,event_id)
            if event and event.status!='completed':
                event.status='failed'
                event.last_error=type(error).__name__
                event.attempt_count+=1
    except Exception:
        pass


def worker_loop(ctx,worker,redis_url,*,once=False):
    if worker not in WORKER_EVENT_PREFIX: raise ValueError('Unknown worker')
    from redis import Redis
    client=Redis.from_url(redis_url,decode_responses=True)
    queue=queue_for(WORKER_EVENT_PREFIX[worker])
    try:
        while True:
            if ctx.router and not ctx.router.primary_available():
                if once:return
                time.sleep(2);continue

            if worker=='reconciliation' and ctx.router:
                results=ctx.router.reconcile_pending()
                if any(r['result'] in {'CONFLICT','INVALID','FAILED_PERMANENT'} for r in results):
                    log.warning('reconciliation quarantined results=%s',results)
                    if once:return
                    time.sleep(5);continue

            item=client.blpop(queue,timeout=1 if once else 5)
            if not item:
                if once:return
                continue
            event_id=item[1]
            try:
                event_type=_event_type(ctx,event_id)
                if event_type in {None,'completed'}:
                    continue
                if worker=='payment' and event_type=='payment.execute':
                    execute_payment_event(ctx,event_id)
                elif worker=='payment' and event_type=='payment.scan':
                    with _session(ctx) as db: process_scan_event(db,ctx,event_id)
                elif worker=='notification' and event_type=='notification.dispatch':
                    execute_notification_event(ctx,event_id)
                elif worker=='reconciliation' and event_type=='reconciliation.scan':
                    execute_reconciliation_event(ctx,event_id)
                else:
                    raise ValueError('Event was delivered to the wrong worker queue')
            except Exception as exc:
                log.warning('worker=%s event_id=%s error=%s',worker,event_id,type(exc).__name__)
                _mark_failed(ctx,event_id,exc)
                if once: raise
                time.sleep(1)
            if once:return
    finally:
        client.close()
