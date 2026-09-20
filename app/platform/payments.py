"""Durable schedule processing, balanced postings, explicit settlement and reversals."""
from datetime import date, timedelta
from sqlalchemy import select
from .models import Due, Circle, Contract, Bank, Posting, PaymentEvent, Account, Participant, Notice
from .services import get,rows,policy,balances,trust,notify,audit,transition,participants,fail
from .ledger import post_payment_result
from .payment_orchestration import PaymentOrchestrationService
from .outbox import emit

def event(db,due,key,status,detail):
    if db.scalar(select(PaymentEvent.id).where(PaymentEvent.key==key)): return False
    db.add(PaymentEvent(due_id=due.id,key=key,status=status,detail=detail));db.flush();return True

def apply_result(db,due,status,key,detail,actor='worker'):
    existing=db.scalar(select(PaymentEvent).where(PaymentEvent.key==key))
    if existing:
        if existing.due_id!=due.id or existing.status!=status: fail('Reconciliation key already used for a different result')
        return
    if status not in ['Settled','Failed','Pending','Reversed']: fail('Unsupported payment status',422)
    if due.status=='Settled' and status!='Reversed': return
    if due.status=='Reversed': fail('Reversed items need a new recovery obligation; cannot replay a debit')
    if status=='Reversed' and due.status!='Settled': fail('Only settled transactions can be reversed')
    if status in ['Settled','Failed'] and due.status not in ['Pending','Processing']: fail('Only submitted payments can settle or fail')
    c=get(db,Circle,due.circle_id)
    if status in ['Settled','Reversed']:
        post_payment_result(db,circle_id=c.id,due_id=due.id,user_id=due.user_id,kind=due.kind,
                            event_key=key,amount_minor=due.amount_minor,reversed=status=='Reversed')
    event(db,due,key,status,detail);due.status=status
    audit(db,actor,due.id,'payment_'+status.lower(),circle_id=c.id)
    notify(db,due.user_id,key,f'{due.kind.title()} {status.lower()}',f'{c.config["currency"]} {due.amount_minor} minor units. {detail}')
    if status=='Reversed': transition(db,c,'Disputed',actor,'Settled payment reversed; reconciliation required')

def complete(db,circle):
    dues=rows(db,Due,Due.circle_id==circle.id)
    if dues and all(d.status=='Settled' for d in dues) and circle.state in ['Active','Cycling']:
        p=get(db,Contract,circle.contract_id).content['policy']
        transition(db,circle,'Completed','worker','All payouts and obligations settled')
        for m in participants(db,circle.id):
            if m.status!='Delinquent': trust(db,m.user_id,p['completion_points'],'completed:'+circle.id+':'+m.user_id,'Completed rotation',circle.id)

def enqueue_due(db,ctx,as_of=None):
    """Persist payment execution intentions without calling a provider.

    This runs inside the payment.scan worker transaction. Each eligible Due is
    moved to Processing and receives a durable payment.execute outbox event.
    """
    as_of=as_of or date.today()
    if policy(db).data['scheduler_paused']: return {'paused':True,'queued':0}
    queued=0
    dues=list(db.scalars(select(Due).where(Due.date<=as_of.isoformat()).order_by(Due.date,Due.kind,Due.id)))
    dues.sort(key=lambda d:(d.kind=='payout',d.date,d.window,d.id))
    for d in dues:
        c=get(db,Circle,d.circle_id)
        if c.state not in ['Active','Cycling'] or d.status not in ['Scheduled','Failed']: continue
        p=get(db,Contract,c.contract_id).content['policy']
        if d.next_attempt and d.next_attempt>as_of.isoformat(): continue
        if d.attempts>=p['retries']+1:
            if d.kind=='contribution':
                m=db.scalar(select(Participant).where(Participant.circle_id==c.id,Participant.user_id==d.user_id))
                m.status='Delinquent'
                trust(db,d.user_id,-p['default_penalty'],'default:'+d.id,'Contribution retry policy exhausted',c.id)
                if as_of>=date.fromisoformat(d.date)+timedelta(days=p['grace_days']):
                    transition(db,c,'Disputed','worker','Missed contribution after grace period')
            continue
        if get(db,Account,d.user_id).suspended: continue
        if d.kind=='payout':
            pending=rows(db,Due,Due.circle_id==c.id,Due.kind=='payout',Due.status.in_(['Pending','Processing']))
            earlier=rows(db,Due,Due.circle_id==c.id,Due.kind=='payout',Due.window<d.window,Due.status!='Settled')
            eligible_ids={x.id for x in rows(db,Due,Due.circle_id==c.id,Due.window<=d.window)}
            window_pool=sum(x.amount_minor for x in rows(db,Posting,Posting.circle_id==c.id,Posting.account=='pool') if x.due_id in eligible_ids)
            available=min(window_pool,balances(db,c.id).get('pool',0))-sum(x.amount_minor for x in pending)
            if earlier or available<d.amount_minor:
                notify(db,d.user_id,'shortfall:'+d.id,'Payout held','Awaiting sufficient settled funds or earlier payouts')
                continue
            member=db.scalar(select(Participant).where(Participant.circle_id==c.id,Participant.user_id==d.user_id))
            if member.status=='Delinquent': continue
        bank=db.scalar(select(Bank).where(Bank.user_id==d.user_id,Bank.status=='Verified',Bank.mandate==True).order_by(Bank.id))
        if not bank: continue

        d.status='Processing';d.attempts+=1
        key=f'payment:{d.id}:attempt:{d.attempts}'
        event(db,d,key,'Attempted','Provider execution queued')
        emit(
            db,
            event_type='payment.execute',
            aggregate_type='due',
            aggregate_id=d.id,
            idempotency_key='execute:'+key,
            payload={'due_id':d.id,'attempt':d.attempts,'payment_key':key,'as_of':as_of.isoformat()},
        )
        if c.state=='Active': transition(db,c,'Cycling','worker','Scheduled money movement queued')
        queued+=1

    for d in rows(db,Due,Due.status=='Scheduled'):
        days=(date.fromisoformat(d.date)-as_of).days
        if days in [0,3]:
            notify(db,d.user_id,f'reminder:{d.id}:{days}','Upcoming '+d.kind,f'Due {d.date}: {d.amount_minor} minor units')
    return {'paused':False,'queued':queued}


def run_due(db,ctx,as_of=None):
    """Sandbox-only inline execution retained for explicit local/manual test ticks."""
    if not ctx.sandbox:
        raise RuntimeError('Inline payment execution is disabled outside sandbox; use payment workers')
    as_of=as_of or date.today()
    if policy(db).data['scheduler_paused']: return {'paused':True,'processed':0}
    processed=0
    dues=list(db.scalars(select(Due).where(Due.date<=as_of.isoformat()).order_by(Due.date,Due.kind,Due.id)))
    dues.sort(key=lambda d:(d.kind=='payout',d.date,d.window,d.id))
    for d in dues:
        c=get(db,Circle,d.circle_id)
        if c.state not in ['Active','Cycling'] or d.status not in ['Scheduled','Failed']: continue
        p=get(db,Contract,c.contract_id).content['policy']
        if d.next_attempt and d.next_attempt>as_of.isoformat(): continue
        if d.attempts>=p['retries']+1:
            if d.kind=='contribution':
                m=db.scalar(select(Participant).where(Participant.circle_id==c.id,Participant.user_id==d.user_id))
                m.status='Delinquent'
                trust(db,d.user_id,-p['default_penalty'],'default:'+d.id,'Contribution retry policy exhausted',c.id)
                if as_of>=date.fromisoformat(d.date)+timedelta(days=p['grace_days']):
                    transition(db,c,'Disputed','worker','Missed contribution after grace period')
            continue
        if get(db,Account,d.user_id).suspended: continue
        if d.kind=='payout':
            pending=rows(db,Due,Due.circle_id==c.id,Due.kind=='payout',Due.status.in_(['Pending','Processing']))
            earlier=rows(db,Due,Due.circle_id==c.id,Due.kind=='payout',Due.window<d.window,Due.status!='Settled')
            eligible_ids={x.id for x in rows(db,Due,Due.circle_id==c.id,Due.window<=d.window)}
            window_pool=sum(x.amount_minor for x in rows(db,Posting,Posting.circle_id==c.id,Posting.account=='pool') if x.due_id in eligible_ids)
            available=min(window_pool,balances(db,c.id).get('pool',0))-sum(x.amount_minor for x in pending)
            if earlier or available<d.amount_minor:
                notify(db,d.user_id,'shortfall:'+d.id,'Payout held','Awaiting sufficient settled funds or earlier payouts')
                continue
            member=db.scalar(select(Participant).where(Participant.circle_id==c.id,Participant.user_id==d.user_id))
            if member.status=='Delinquent': continue
        bank=db.scalar(select(Bank).where(Bank.user_id==d.user_id,Bank.status=='Verified',Bank.mandate==True).order_by(Bank.id))
        if not bank: continue
        d.status='Processing';d.attempts+=1
        key=f'payment:{d.id}:attempt:{d.attempts}'
        event(db,d,key,'Attempted','Provider execution requested')
        result=PaymentOrchestrationService(ctx).initiate(
            key=key,amount_minor=d.amount_minor,currency=c.config['currency'],kind=d.kind,
            bank_token=ctx.vault.open(bank.encrypted_token))
        d.provider_ref=result.reference
        apply_result(db,d,result.status,key+':result',result.detail)
        if result.status=='Failed': d.next_attempt=(as_of+timedelta(days=p['retry_days']*2**(d.attempts-1))).isoformat()
        if c.state=='Active': transition(db,c,'Cycling','worker','Scheduled money movement started')
        processed+=1;db.flush();complete(db,c)
    for d in rows(db,Due,Due.status=='Scheduled'):
        days=(date.fromisoformat(d.date)-as_of).days
        if days in [0,3]: notify(db,d.user_id,f'reminder:{d.id}:{days}','Upcoming '+d.kind,f'Due {d.date}: {d.amount_minor} minor units')
    return {'paused':False,'processed':processed}

def dispatch_notices(db,ctx,notice_id=None):
    """Dispatch one outbox-addressed notice or a bounded legacy batch."""
    from .models import NotificationChannel
    enabled={c.id for c in db.scalars(select(NotificationChannel).where(NotificationChannel.enabled==True))}
    sent=0
    if notice_id:
        notice=db.get(Notice,notice_id)
        notices=[notice] if notice else []
    else:
        notices=rows(db,Notice,Notice.status.in_(['Queued','Failed']),Notice.attempts<5)[:100]
    for n in notices:
        if not n or n.status not in ['Queued','Failed'] or n.attempts>=5: continue
        if n.channel not in enabled: continue
        u=get(db,Account,n.user_id)
        destination=u.email if n.channel=='email' else u.phone if n.channel=='sms' else u.preferences.get('push_token','')
        if n.channel=='push' and not destination: n.status='NoDestination';continue
        n.attempts+=1
        try:
            body=ctx.vault.open(n.body) if n.title=='Verification code' else n.body
            if n.title=='Staff invitation':
                destination, token=ctx.vault.open(n.body).split('\n',1)
                body='Accept your staff invitation in Ajo using this one-time code: '+token
            if n.channel=='push': destination=ctx.vault.open(destination)
            n.status=ctx.notifications.send(key=n.key,channel=n.channel,destination=destination,title=n.title,body=body)
            sent+=1
        except RuntimeError: n.status='Failed'
    return sent
