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


def reconcile_pending_payments(db, ctx):
    """Reconcile provider-side state for locally Pending payment attempts."""
    from sqlalchemy import select
    from .models import Due, Circle
    from .payments import apply_result, complete

    service=PaymentOrchestrationService(ctx)
    checked=updated=0
    for due in db.scalars(select(Due).where(Due.status=='Pending',Due.provider_ref.is_not(None)).limit(100)):
        checked+=1
        result=service.status(due.provider_ref)
        if result.status in {'Settled','Failed','Reversed'}:
            apply_result(db,due,result.status,'provider-reconcile:'+due.id+':'+result.reference,result.detail)
            complete(db,db.get(Circle,due.circle_id))
            updated+=1
    return {'checked':checked,'updated':updated}
