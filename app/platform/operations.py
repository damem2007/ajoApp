import base64
import csv
import io
import json
from datetime import date,datetime,timezone
from typing import Optional,Literal
from fastapi import APIRouter,Depends,Query,Response
from sqlalchemy import select,func,delete
from pydantic import Field
from .models import (Account,SessionToken,IdentityCase,Document,Bank,Policy,Circle,Contract,Participant,Due,
                     Posting,PaymentEvent,TrustEvent,Notice,Complaint,Audit,DataRequest,Signature)
from .schemas import Input,Reason,ReviewInput,ComplaintInput,ResolutionInput,PolicyChange
from .services import (get,rows,fail,policy,audit,notify,trust,transition,require_member,participants,cap,
                       account_view,circle_view,balances,obligation)
from .payments import run_due,dispatch_notices,apply_result,complete
from .security import secret,digest

def routes(ctx):
    router=APIRouter(prefix='/api/v1',tags=['Operations'])
    dbdep=ctx.session
    admin=ctx.staff('admin');ops=ctx.staff('admin','ops');compliance=ctx.staff('admin','compliance')
    support=ctx.staff('admin','support','compliance')
    staff=ctx.staff('admin','ops','support','compliance')

    @router.get('/notifications')
    def notices(offset:int=Query(0,ge=0),db=Depends(dbdep),user=Depends(ctx.actor)):
        return [dict(id=n.id,title=n.title,body=n.body,read=n.read,created_at=n.created_at) for n in
                db.scalars(select(Notice).where(Notice.user_id==user.id,Notice.channel=='in-app',Notice.status!='Dismissed').order_by(Notice.created_at.desc()).offset(offset).limit(100))]

    @router.get('/notifications/summary')
    def notification_summary(db=Depends(dbdep),user=Depends(ctx.actor)):
        count=db.scalar(select(func.count()).select_from(Notice).where(Notice.user_id==user.id,
            Notice.channel=='in-app',Notice.status!='Dismissed',Notice.read==False))
        return {'unread':count}

    @router.post('/notifications/{nid}/read')
    def read_notice(nid:str,db=Depends(dbdep),user=Depends(ctx.actor)):
        n=get(db,Notice,nid)
        if n.user_id!=user.id: fail('Notification belongs to another user',403)
        n.read=True;return {'read':True}

    @router.delete('/notifications/{nid}')
    def delete_notice(nid:str,db=Depends(dbdep),user=Depends(ctx.actor)):
        n=get(db,Notice,nid)
        if n.user_id!=user.id or n.channel!='in-app': fail('Notification unavailable',404)
        if not n.read: fail('Read this notification before deleting it',409)
        n.status='Dismissed'
        return {'deleted':True}

    @router.get('/trust')
    def score(db=Depends(dbdep),user=Depends(ctx.actor)):
        return [dict(delta=t.delta,reason=t.reason,created_at=t.created_at) for t in rows(db,TrustEvent,TrustEvent.user_id==user.id)]

    @router.post('/complaints',status_code=201)
    def report(body:ComplaintInput,db=Depends(dbdep),user=Depends(ctx.actor)):
        c=get(db,Circle,body.circle_id);require_member(db,c,user)
        if body.target_id and body.target_id not in [m.user_id for m in participants(db,c.id)]: fail('Target must belong to this scheme',422)
        r=Complaint(filer_id=user.id,**body.model_dump());db.add(r);db.flush()
        audit(db,user,r.id,'complaint_submitted')
        notify(db,user.id,'complaint:'+r.id,'Report submitted','Your report is in the review queue')
        return {'id':r.id,'status':r.status}

    @router.get('/complaints')
    def complaints(db=Depends(dbdep),user=Depends(ctx.actor)):
        return [dict(id=r.id,circle_id=r.circle_id,category=r.category,status=r.status,resolution=r.resolution,created_at=r.created_at)
                for r in rows(db,Complaint,(Complaint.filer_id==user.id)|(Complaint.target_id==user.id))]

    @router.get('/admin/users')
    def users(q:str='',db=Depends(dbdep),user=Depends(staff)):
        audit(db,user,'accounts','user_search')
        return [account_view(db,u) for u in rows(db,Account) if q.lower() in (u.email+' '+(u.pseudonym or '')).lower()][:100]

    class AccountChange(Reason): suspended:bool
    @router.post('/admin/users/{uid}/status')
    def user_status(uid:str,body:AccountChange,db=Depends(dbdep),user=Depends(admin)):
        u=get(db,Account,uid)
        if u.id==user.id: fail('Cannot suspend your own administrator account')
        u.suspended=body.suspended
        if u.suspended: db.execute(delete(SessionToken).where(SessionToken.user_id==uid))
        audit(db,user,uid,'account_status',suspended=body.suspended,reason=body.reason)
        notify(db,uid,'account-status:'+secret(),'Account status changed',body.reason)
        return account_view(db,u)

    class RoleChange(Reason): role:Literal['member','admin','ops','support','compliance']
    @router.post('/admin/users/{uid}/role')
    def role(uid:str,body:RoleChange,db=Depends(dbdep),user=Depends(admin)):
        u=get(db,Account,uid)
        if u.id==user.id: fail('Cannot change your own role')
        u.role=body.role
        db.execute(delete(SessionToken).where(SessionToken.user_id==uid))
        audit(db,user,uid,'role_changed',role=body.role,reason=body.reason)
        return account_view(db,u)

    class TrustChange(Reason): delta:int=Field(ge=-1000,le=1000)
    @router.post('/admin/users/{uid}/trust')
    def adjust(uid:str,body:TrustChange,db=Depends(dbdep),user=Depends(admin)):
        trust(db,uid,body.delta,'manual:'+secret(),body.reason,propagate=False)
        audit(db,user,uid,'trust_override',delta=body.delta,reason=body.reason)
        return account_view(db,get(db,Account,uid))

    @router.get('/admin/kyc')
    def review_queue(db=Depends(dbdep),user=Depends(compliance)):
        audit(db,user,'kyc','review_queue_access')
        return [dict(id=k.id,user_id=k.user_id,status=k.status,signals=k.signals,created_at=k.created_at) for k in rows(db,IdentityCase)]

    @router.get('/admin/kyc/{kid}')
    def identity(kid:str,db=Depends(dbdep),user=Depends(compliance)):
        k=get(db,IdentityCase,kid);audit(db,user,kid,'identity_access')
        return dict(id=k.id,status=k.status,signals=k.signals,identity=json.loads(ctx.vault.open(k.encrypted_data)))

    @router.get('/admin/documents/{did}')
    def document(did:str,db=Depends(dbdep),user=Depends(compliance)):
        d=get(db,Document,did);audit(db,user,did,'document_access')
        return Response(base64.b64decode(ctx.vault.open(d.ciphertext.decode())),media_type=d.mime,
                        headers={'Content-Disposition':'attachment; filename="verification-document"','X-Content-Type-Options':'nosniff'})

    @router.post('/admin/kyc/{kid}/review')
    def review(kid:str,body:ReviewInput,db=Depends(dbdep),user=Depends(compliance)):
        k=get(db,IdentityCase,kid);u=get(db,Account,k.user_id)
        if k.status not in ['Pending','UnderReview']: fail('This submission is already decided; request a new submission')
        if body.decision=='Approved':
            ctx.require_sandbox()
            identity=json.loads(ctx.vault.open(k.encrypted_data))
            if date.fromisoformat(identity['expiry'])<=date.today(): fail('Identity document has expired')
            if any('Duplicate' in s or 'Shared device' in s for s in k.signals) and not body.duplicate_reviewed: fail('Explicit duplicate review acknowledgement required')
            if not u.pseudonym: u.pseudonym='Member-'+secret()[:12]
        k.status=body.decision;k.reason=body.reason;u.kyc_status=body.decision
        audit(db,user,kid,'kyc_decision',decision=body.decision,reason=body.reason,duplicate_reviewed=body.duplicate_reviewed)
        notify(db,u.id,'kyc-review:'+kid+':'+body.decision,'Identity verification updated',body.decision+': '+body.reason)
        return {'status':k.status}

    @router.get('/admin/circles')
    def circles(state:Optional[str]=None,db=Depends(dbdep),user=Depends(staff)):
        return [circle_view(db,c,user,staff=True) for c in rows(db,Circle) if not state or c.state==state]

    class CircleChange(Reason): state:Literal['Suspended','Disputed','Cycling','Cancelled']
    @router.post('/admin/circles/{cid}/state')
    def circle_state(cid:str,body:CircleChange,db=Depends(dbdep),user=Depends(ops)):
        c=get(db,Circle,cid)
        allowed={'Active':['Suspended','Disputed'],'Cycling':['Suspended','Disputed'],
                 'Disputed':['Suspended','Cycling'],'Suspended':['Cycling','Cancelled'],
                 'Draft':['Cancelled'],'Recruiting':['Cancelled'],'Finalizable':['Cancelled']}
        if body.state not in allowed.get(c.state,[]): fail('Invalid administrative transition')
        if body.state=='Cancelled' and rows(db,Posting,Posting.circle_id==cid): fail('Funded termination requires an approved unwind policy')
        if body.state=='Cycling' and not c.contract_id: fail('No active contract')
        transition(db,c,body.state,user,body.reason);return {'state':c.state}

    class Curation(Reason):
        featured:bool=False
        removed:bool=False
        premium:bool=False
    @router.post('/admin/circles/{cid}/curation')
    def curate(cid:str,body:Curation,db=Depends(dbdep),user=Depends(ops)):
        c=get(db,Circle,cid)
        if c.state not in ['Draft','Recruiting','Finalizable']: fail('Cannot change contracted marketplace terms')
        if c.config['privacy']!='public' and (body.featured or body.premium): fail('Only public circles may be featured or premium')
        c.featured=body.featured;c.removed=body.removed;c.config={**c.config,'premium':body.premium}
        audit(db,user,cid,'marketplace_curated',**body.model_dump());return circle_view(db,c,user,staff=True)

    @router.get('/admin/policies')
    def policies(db=Depends(dbdep),user=Depends(admin)):
        return [dict(id=p.id,data=p.data,reason=p.reason,created_at=p.created_at) for p in rows(db,Policy)]

    @router.post('/admin/policies',status_code=201)
    def change_policy(body:PolicyChange,db=Depends(dbdep),user=Depends(admin)):
        p=Policy(data=body.policy.model_dump(),actor_id=user.id,reason=body.reason);db.add(p);db.flush()
        audit(db,user,str(p.id),'policy_version_created',reason=body.reason)
        return {'id':p.id,'policy':p.data}

    @router.get('/admin/complaints')
    def reports(db=Depends(dbdep),user=Depends(support)):
        p=policy(db).data
        return [dict(id=r.id,circle_id=r.circle_id,filer_id=r.filer_id,target_id=r.target_id,category=r.category,
                     description=r.description,status=r.status,assignee=r.assignee,
                     overdue=(datetime.now(timezone.utc)-datetime.fromisoformat(r.created_at)).days>=p['complaint_sla_days'])
                for r in rows(db,Complaint)]

    @router.get('/admin/complaints/{rid}/evidence')
    def evidence(rid:str,db=Depends(dbdep),user=Depends(support)):
        r=get(db,Complaint,rid);audit(db,user,rid,'complaint_evidence_access')
        return {'report':{'category':r.category,'description':r.description,'status':r.status},
                'payments':[dict(id=d.id,user_id=d.user_id,status=d.status,amount_minor=d.amount_minor,date=d.date)
                            for d in rows(db,Due,Due.circle_id==r.circle_id)],
                'kyc_status':get(db,Account,r.target_id).kyc_status if r.target_id else None}

    @router.post('/admin/complaints/{rid}/resolve')
    def resolve(rid:str,body:ResolutionInput,db=Depends(dbdep),user=Depends(support)):
        r=get(db,Complaint,rid)
        transitions={'Submitted':['Triaged','Dismissed'],'Triaged':['UnderInvestigation','Dismissed'],
                     'UnderInvestigation':['ActionTaken','Dismissed']}
        if body.status not in transitions.get(r.status,[]): fail('Invalid complaint transition')
        if body.trust_delta and (body.status!='ActionTaken' or not r.target_id): fail('A penalty needs a resolved finding against a member')
        if body.assignee and get(db,Account,body.assignee).role not in ['admin','support','compliance']: fail('Assignee must be a reviewer')
        r.status=body.status;r.resolution=body.reason;r.assignee=body.assignee;r.updated_at=datetime.now(timezone.utc).isoformat()
        if body.trust_delta: trust(db,r.target_id,body.trust_delta,'complaint:'+r.id,body.reason,r.circle_id)
        audit(db,user,rid,'complaint_transition',status=r.status,reason=body.reason)
        for uid in {r.filer_id,r.target_id}-{None}:
            notify(db,uid,'complaint:'+r.id+':'+r.status,'Report status updated',r.status+': '+body.reason)
        return {'status':r.status}

    @router.get('/admin/payments')
    def payments(status:Optional[str]=None,circle_id:Optional[str]=None,db=Depends(dbdep),user=Depends(ops)):
        return [dict(id=d.id,circle_id=d.circle_id,user_id=d.user_id,date=d.date,kind=d.kind,status=d.status,
                     amount_minor=d.amount_minor,attempts=d.attempts,provider_ref=d.provider_ref)
                for d in rows(db,Due) if (not status or d.status==status) and (not circle_id or d.circle_id==circle_id)]

    class Tick(Input): as_of:Optional[date]=None
    @router.post('/admin/jobs/run')
    def tick(body:Tick,db=Depends(dbdep),user=Depends(ops)):
        ctx.require_sandbox()
        result=run_due(db,ctx,body.as_of);result['notifications_dispatched']=dispatch_notices(db,ctx)
        audit(db,user,'scheduler','manual_tick',as_of=str(body.as_of or date.today()))
        return result

    class Reconcile(Reason):
        status:Literal['Settled','Failed','Reversed']
        event_id:str=Field(min_length=8,max_length=100)
    @router.post('/admin/payments/{did}/reconcile')
    def reconcile(did:str,body:Reconcile,db=Depends(dbdep),user=Depends(ops)):
        ctx.require_sandbox();d=get(db,Due,did)
        apply_result(db,d,body.status,'manual:'+did+':'+body.event_id,body.reason,user.id)
        complete(db,get(db,Circle,d.circle_id));return {'status':d.status}

    @router.post('/admin/payments/{did}/retry')
    def retry(did:str,body:Reason,db=Depends(dbdep),user=Depends(ops)):
        d=get(db,Due,did)
        if d.status!='Failed': fail('Only definitive failures may be retried; pending payments require reconciliation')
        frozen=get(db,Contract,get(db,Circle,d.circle_id).contract_id).content['policy']
        if d.attempts>=frozen['retries']+1: fail('Contracted retry limit exhausted; resolve the default first')
        d.next_attempt=date.today().isoformat();audit(db,user,did,'retry_requested',reason=body.reason)
        return {'status':'RetryScheduled'}

    @router.get('/admin/notifications')
    def delivery(db=Depends(dbdep),user=Depends(ops)):
        return [dict(id=n.id,user_id=n.user_id,channel=n.channel,title=n.title,status=n.status,attempts=n.attempts)
                for n in rows(db,Notice)][-500:]

    @router.post('/admin/notifications/{nid}/resend')
    def resend(nid:str,body:Reason,db=Depends(dbdep),user=Depends(ops)):
        n=get(db,Notice,nid)
        if n.title=='Verification code': fail('User must request a fresh verification code')
        n.status='Queued';n.attempts=0;audit(db,user,nid,'notification_resend',reason=body.reason)
        return {'status':n.status}

    @router.get('/admin/audit')
    def audits(resource:Optional[str]=None,db=Depends(dbdep),user=Depends(admin)):
        return [dict(id=a.id,actor_id=a.actor_id,resource=a.resource,action=a.action,detail=a.detail,created_at=a.created_at)
                for a in rows(db,Audit) if not resource or a.resource==resource][-500:]

    @router.get('/admin/metrics')
    def metrics(db=Depends(dbdep),user=Depends(staff)):
        circles=rows(db,Circle);dues=rows(db,Due);identities=rows(db,IdentityCase)
        totals={}
        for c in circles:
            currency=c.config['currency'];totals.setdefault(currency,0)
            totals[currency]+=sum(d.amount_minor for d in dues if d.circle_id==c.id and d.kind=='payout' and d.status=='Settled')
        accounts=rows(db,Account);members=rows(db,Participant);reports=rows(db,Complaint)
        cohorts={}
        for account in accounts:
            tier=str(cap(db,account));cohorts[tier]=cohorts.get(tier,0)+1
        return {'default_rate':sum(m.status=='Delinquent' for m in members)/max(1,len(members)),
                'dispute_rate':len(reports)/max(1,len(circles)),'accounts_by_concurrent_cap':cohorts,
                'accounts':len(accounts),'active_circles':sum(c.state in ['Active','Cycling'] for c in circles),
                'completion_rate':sum(c.state=='Completed' for c in circles)/max(1,len(circles)),
                'settled_payouts_by_currency_minor':totals,'failed_payments':sum(d.status=='Failed' for d in dues),
                'pending_payments':sum(d.status=='Pending' for d in dues),
                'kyc_approval_rate':sum(k.status=='Approved' for k in identities)/max(1,len(identities)),
                'open_complaints':len([r for r in rows(db,Complaint) if r.status not in ['Dismissed','ActionTaken']]),
                'queued_notifications':len(rows(db,Notice,Notice.status=='Queued')),'scheduler_paused':policy(db).data['scheduler_paused']}

    @router.get('/admin/ledger.csv')
    def export(db=Depends(dbdep),user=Depends(ops)):
        out=io.StringIO();writer=csv.writer(out);writer.writerow(['id','circle_id','currency','user_id','event_key','account','amount_minor','created_at'])
        for p in rows(db,Posting): writer.writerow([p.id,p.circle_id,get(db,Circle,p.circle_id).config['currency'],p.user_id,p.event_key,p.account,p.amount_minor,p.created_at])
        audit(db,user,'ledger','export')
        return Response(out.getvalue(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="ajo-ledger.csv"'})

    @router.get('/me/export')
    def own_export(db=Depends(dbdep),user=Depends(ctx.actor)):
        audit(db,user,user.id,'personal_data_export')
        memberships=rows(db,Participant,Participant.user_id==user.id)
        content={'account':account_view(db,user),
                 'circles':[circle_view(db,get(db,Circle,m.circle_id),user) for m in memberships if m.status!='Left'],
                 'trust':[{'delta':t.delta,'reason':t.reason,'date':t.created_at} for t in rows(db,TrustEvent,TrustEvent.user_id==user.id)],
                 'reports':[{'id':r.id,'description':r.description,'status':r.status} for r in rows(db,Complaint,Complaint.filer_id==user.id)]}
        return Response(json.dumps(content,indent=2),media_type='application/json',headers={'Content-Disposition':'attachment; filename="ajo-personal-data.json"'})

    @router.post('/banks/{bid}/disable')
    def disable_bank(bid:str,body:Reason,db=Depends(dbdep),user=Depends(ctx.actor)):
        b=get(db,Bank,bid)
        if b.user_id!=user.id: fail('This bank link belongs to another member',403)
        b.mandate=False;b.status='Disabled'
        audit(db,user,bid,'bank_mandate_disabled',reason=body.reason)
        notify(db,user.id,'bank-disabled:'+bid,'Bank mandate disabled','Future collections are paused until another verified mandate is available. Existing obligations remain due.')
        return {'status':b.status}

    @router.get('/admin/data-requests')
    def requests(db=Depends(dbdep),user=Depends(compliance)):
        return [dict(id=r.id,user_id=r.user_id,kind=r.kind,status=r.status,reason=r.reason) for r in rows(db,DataRequest)]

    class RequestDecision(Reason): status:Literal['UnderReview','Retained','Fulfilled']
    @router.post('/admin/data-requests/{rid}')
    def decide(rid:str,body:RequestDecision,db=Depends(dbdep),user=Depends(compliance)):
        r=get(db,DataRequest,rid)
        if body.status=='Fulfilled': fail('Fulfilment requires the retention/export workflow; recording a decision cannot delete evidence')
        r.status=body.status;r.reason=body.reason;audit(db,user,rid,'data_request_reviewed',**body.model_dump())
        return {'status':r.status}

    return router
