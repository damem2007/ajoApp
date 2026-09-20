"""Append-oriented ledger services.

Provider responses never become balances directly. Financial state is represented
by balanced, idempotent ledger postings linked to the originating payment event.
"""
from sqlalchemy import select
from .models import Posting


def post_payment_result(db, *, circle_id, due_id, user_id, kind, event_key, amount_minor, reversed=False):
    account={'contribution':'member_contributions','payout':'member_payouts','fee':'fee_income'}[kind]
    cash='fees_cash' if kind=='fee' else 'pool'
    sign=-1 if kind=='payout' else 1
    if reversed:
        sign*=-1
    entries=[
        (cash,sign*amount_minor),
        (account,-sign*amount_minor),
    ]
    for name, amount in entries:
        existing=db.scalar(select(Posting).where(Posting.event_key==event_key,Posting.account==name))
        if existing:
            if existing.amount_minor!=amount or existing.due_id!=due_id:
                raise ValueError('Ledger idempotency key conflicts with an existing posting')
            continue
        db.add(Posting(circle_id=circle_id,due_id=due_id,user_id=user_id,event_key=event_key,
                       account=name,amount_minor=amount))
    if sum(amount for _,amount in entries)!=0:
        raise ValueError('Ledger transaction is not balanced')
