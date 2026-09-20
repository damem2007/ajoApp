from __future__ import annotations

import argparse
from sqlalchemy import delete, select

from app.config import app_environment
from app.database import make_engine
from app.platform.models import (
    Account, Circle, Participant, Invitation, Contract, Signature, Due, Posting, PaymentEvent,
    TrustEvent, Notice, Complaint, Audit, DataRequest, IdentityCase, Document, Bank, SessionToken,
    StaffMembership, StaffInvitation, Challenge, OutboxEvent, WorkerReceipt
)
from sqlalchemy.orm import Session


def require_safe_environment():
    if app_environment() not in {'development','test'}:
        raise RuntimeError('Test-data cleanup is disabled in production.')


def cleanup_run(run_id):
    require_safe_environment()
    engine=make_engine()
    with Session(engine) as db,db.begin():
        users=list(db.scalars(select(Account.id).where(
            Account.test_run_id==run_id,Account.is_test_account==True,Account.source=='test_cli')))
        circles=list(db.scalars(select(Circle.id).where(
            Circle.test_run_id==run_id,Circle.is_test_data==True,Circle.source=='test_cli')))
        if not users and not circles: return {'users':0,'circles':0}
        contract_ids=list(db.scalars(select(Contract.id).where(Contract.circle_id.in_(circles)))) if circles else []
        due_ids=list(db.scalars(select(Due.id).where(Due.circle_id.in_(circles)))) if circles else []
        notice_ids=list(db.scalars(select(Notice.id).where(Notice.user_id.in_(users)))) if users else []
        event_ids=list(db.scalars(select(OutboxEvent.id).where(
            OutboxEvent.aggregate_id.in_(circles+due_ids+notice_ids)))) if circles or due_ids or notice_ids else []
        if event_ids: db.execute(delete(WorkerReceipt).where(WorkerReceipt.event_id.in_(event_ids)))
        if circles or due_ids or notice_ids: db.execute(delete(OutboxEvent).where(OutboxEvent.aggregate_id.in_(circles+due_ids+notice_ids)))
        if due_ids:
            db.execute(delete(Posting).where(Posting.due_id.in_(due_ids)))
            db.execute(delete(PaymentEvent).where(PaymentEvent.due_id.in_(due_ids)))
        if contract_ids: db.execute(delete(Signature).where(Signature.contract_id.in_(contract_ids)))
        if circles:
            db.execute(delete(Due).where(Due.circle_id.in_(circles)))
            db.execute(delete(Invitation).where(Invitation.circle_id.in_(circles)))
            db.execute(delete(Participant).where(Participant.circle_id.in_(circles)))
            db.execute(delete(Complaint).where(Complaint.circle_id.in_(circles)))
            db.execute(delete(TrustEvent).where(TrustEvent.circle_id.in_(circles)))
            db.execute(delete(Contract).where(Contract.circle_id.in_(circles)))
            db.execute(delete(Circle).where(Circle.id.in_(circles)))
        if users:
            # Remove only records owned by the explicitly tagged test accounts.
            db.execute(delete(Challenge).where(Challenge.user_id.in_(users)))
            db.execute(delete(StaffInvitation).where(
                (StaffInvitation.created_by.in_(users)) | (StaffInvitation.accepted_by.in_(users))
            ))
            db.execute(delete(SessionToken).where(SessionToken.user_id.in_(users)))
            db.execute(delete(StaffMembership).where(StaffMembership.user_id.in_(users)))
            db.execute(delete(IdentityCase).where(IdentityCase.user_id.in_(users)))
            db.execute(delete(Document).where(Document.user_id.in_(users)))
            db.execute(delete(Bank).where(Bank.user_id.in_(users)))
            db.execute(delete(Notice).where(Notice.user_id.in_(users)))
            db.execute(delete(DataRequest).where(DataRequest.user_id.in_(users)))
            db.execute(delete(TrustEvent).where(TrustEvent.user_id.in_(users)))
            db.execute(delete(Participant).where(Participant.user_id.in_(users)))
            db.execute(delete(Invitation).where(Invitation.generator_id.in_(users)))
            db.execute(delete(Complaint).where(
                (Complaint.filer_id.in_(users)) | (Complaint.target_id.in_(users))
            ))
            db.execute(delete(Account).where(
                Account.id.in_(users),
                Account.role!='admin',
                Account.is_test_account==True,
                Account.source=='test_cli',
                Account.test_run_id==run_id,
            ))
        # Audit rows are non-FK evidence; only explicit test actors/resources are removed.
        if users or circles:
            db.execute(delete(Audit).where((Audit.actor_id.in_(users)) | (Audit.resource.in_(users+circles))))
    return {'users':len(users),'circles':len(circles)}


def main():
    parser=argparse.ArgumentParser()
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--run-id')
    group.add_argument('--all',action='store_true')
    args=parser.parse_args()
    require_safe_environment()
    if args.all:
        engine=make_engine()
        with Session(engine) as db:
            run_ids=sorted({x for x in db.scalars(select(Account.test_run_id).where(
                Account.is_test_account==True,Account.source=='test_cli',Account.test_run_id.is_not(None)))})
        result={'runs':{run_id:cleanup_run(run_id) for run_id in run_ids}}
    else:
        result=cleanup_run(args.run_id)
    print(result)


if __name__=='__main__': main()
