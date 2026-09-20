"""Payment orchestration above provider adapters."""
from __future__ import annotations

import logging
from .providers import TransferRequest, PaymentResult

log=logging.getLogger('ajo.payment')


class PaymentOrchestrationService:
    def __init__(self, ctx):
        self.ctx=ctx

    def initiate(self, *, key, amount_minor, currency, kind, bank_token):
        if amount_minor<=0:
            raise ValueError('Payment amount must be positive')
        if kind not in {'contribution','payout','fee'}:
            raise ValueError('Unsupported payment kind')
        # Never initiate an external financial action while the canonical database
        # is unavailable. The durable local operation will be reconciled first.
        if self.ctx.router and self.ctx.router.mode=='sqlite':
            raise RuntimeError('Canonical database unavailable; payment execution deferred')
        request=TransferRequest(key=key,amount_minor=amount_minor,currency=currency,kind=kind,bank_token=bank_token)
        try:
            result=self.ctx.payments.initiate_transfer(request)
        except TimeoutError:
            log.warning('provider timeout payment_key=%s',key)
            return PaymentResult('Pending','unknown:'+key,'Provider timeout; reconcile before retry')
        if result.status not in {'Settled','Failed','Pending','Reversed'}:
            raise RuntimeError('Provider returned an unsupported payment status')
        return result

    def status(self, reference):
        result=self.ctx.payments.get_transfer(reference=reference)
        if result.status not in {'Settled','Failed','Pending','Reversed'}:
            raise RuntimeError('Provider returned an unsupported payment status')
        return result

    def cancel(self, *, reference, key):
        return self.ctx.payments.cancel_transfer(reference=reference,key=key)


def reconcile_pending_payments(ctx):
    """Query provider state without holding an application DB transaction open."""
    from contextlib import contextmanager
    from datetime import date, timedelta
    from sqlalchemy import select
    from .models import Due, Circle, Contract
    from .payments import apply_result, complete

    @contextmanager
    def scope():
        gen=ctx.session();db=next(gen)
        try:
            yield db
        except Exception:
            gen.close();raise
        else:
            try: next(gen)
            except StopIteration: pass

    with scope() as db:
        pending=[(d.id,d.provider_ref) for d in db.scalars(
            select(Due).where(Due.status=='Pending',Due.provider_ref.is_not(None)).limit(100)
        )]

    service=PaymentOrchestrationService(ctx)
    checked=updated=failed=0
    for due_id,reference in pending:
        checked+=1
        try:
            result=service.status(reference)
        except Exception:
            failed+=1
            log.warning('provider reconciliation failed due_id=%s provider_reference=%s',due_id,reference)
            continue
        if result.status not in {'Settled','Failed','Reversed'}:
            continue
        with scope() as db:
            due=db.get(Due,due_id)
            if not due or due.status!='Pending':
                continue
            apply_result(db,due,result.status,'provider-reconcile:'+due.id+':'+result.reference,result.detail)
            if result.status=='Failed':
                circle=db.get(Circle,due.circle_id)
                p=db.get(Contract,circle.contract_id).content['policy']
                due.next_attempt=(date.today()+timedelta(days=p['retry_days']*2**max(0,due.attempts-1))).isoformat()
            complete(db,db.get(Circle,due.circle_id))
            updated+=1
    return {'checked':checked,'updated':updated,'failed':failed}
