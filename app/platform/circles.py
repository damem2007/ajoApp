import hashlib
import json
import time
from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import select
from .models import Account, Circle, Participant, Invitation, Contract, Signature, Due, Bank, IdentityCase
from .schemas import PolicyInput, CircleInput, CircleSetupResponse, InviteInput, JoinInput, FinalizeInput, SignInput, Reason
from .security import secret, digest, canonical
from .calendar import schedule
from .contracts import render_contract
from .services import (get,rows,fail,audit,notify,participants,eligible,require_member,check_cap,
                       circle_view,transition,policy,assert_launch_policy,commitments,cap)

from .setup import circle_setup, validate_circle_setup

def routes(ctx):
    router=APIRouter(prefix='/api/v1',tags=['Circles and contracts'])
    dbdep=ctx.session

    @router.get("/public/circle-setup", response_model=CircleSetupResponse)
    def setup(db=Depends(dbdep)):
        return circle_setup(db)

    def contract_access(db,con,user):
        from .rbac import has_permission
        if has_permission(db,user,'contracts.view'): return
        if user.id not in [m['id'] for m in con.content['members']]: fail('Only original contract parties can access this version',403)

    def owned(db,cid,user):
        c=get(db,Circle,cid);require_member(db,c,user);return c

    @router.get('/marketplace')
    def marketplace(q:str='',currency:Optional[str]=None,frequency:Optional[str]=None,
                    minimum:int=0,maximum:int=100_000_000_000,offset:int=Query(0,ge=0),limit:int=Query(30,ge=1,le=100),
                    db=Depends(dbdep),user=Depends(ctx.actor)):
        eligible(user)
        if commitments(db,user)>=cap(db,user): return []
        result=[]
        for c in rows(db,Circle,Circle.state=='Recruiting',Circle.removed==False):
            cfg=c.config
            if cfg['privacy']!='public' or cfg['premium'] or cfg['trust_threshold']>user.score or len(participants(db,c.id))>=cfg['planned_members']: continue
            if q.lower() not in (c.name+' '+cfg['description']).lower(): continue
            if currency and cfg['currency']!=currency: continue
            if frequency and cfg['contribution_frequency']!=frequency: continue
            if not minimum<=cfg['target_minor']<=maximum: continue
            if any(m.user_id==user.id for m in participants(db,c.id)): continue
            result.append(circle_view(db,c))
        return sorted(result,key=lambda c:(not c['featured'],c['name']))[offset:offset+limit]

    @router.get('/public/marketplace')
    def public_marketplace(q:str='',currency:Optional[str]=None,frequency:Optional[str]=None,db=Depends(dbdep)):
        result=[]
        for c in rows(db,Circle,Circle.state=='Recruiting',Circle.removed==False):
            cfg=c.config; count=len(participants(db,c.id))
            if cfg['privacy']!='public' or cfg['premium'] or count>=cfg['planned_members']: continue
            if q.lower() not in (c.name+' '+cfg['description']).lower(): continue
            if currency and currency!=cfg['currency']: continue
            if frequency and frequency!=cfg['contribution_frequency']: continue
            result.append({'id':c.id,'name':c.name,'description':cfg['description'],'currency':cfg['currency'],
                'category':cfg.get('category','Community'),'featured':c.featured,
                'start_date':cfg['start_date'],
                'target_minor':cfg['target_minor'],'frequency':cfg['contribution_frequency'],
                'members':cfg['planned_members'],'slots':cfg['planned_members']-count,
                'payout_frequency':cfg['collection_frequency'],
                'trust_threshold':cfg['trust_threshold']})
        return sorted(result,key=lambda item:item['name'])[:100]

    @router.get('/circles')
    def mine(db=Depends(dbdep),user=Depends(ctx.actor)):
        ids=[m.circle_id for m in rows(db,Participant,Participant.user_id==user.id,Participant.status!='Left')]
        return [circle_view(db,get(db,Circle,cid),user) for cid in ids]

    def fixed_plan(body):
        config=body.model_dump(mode='json')
        try:
            planned=schedule(config,[f'planned-member-{i}' for i in range(body.planned_members)],PolicyInput(fee_mode='none').model_dump())
        except ValueError as exc: fail(str(exc),422)
        return config,planned

    @router.post('/circles/preview')
    def preview_plan(body:CircleInput,db=Depends(dbdep),user=Depends(ctx.actor)):
        validate_circle_setup(db,body)
        if body.contribution_minor is None: fail('Enter a fixed contribution amount',422)
        config,planned=fixed_plan(body)
        return {'contribution_minor':config['contribution_minor'],'target_minor':config['target_minor'],
                'debit_dates':sorted({row['date'] for row in planned if row['kind']=='contribution'}),
                'payout_dates':[row['date'] for row in planned if row['kind']=='payout'],
                'planned_members':body.planned_members}

    @router.post('/circles',status_code=201)
    def create(body:CircleInput,db=Depends(dbdep),user=Depends(ctx.actor)):
        validate_circle_setup(db,body)
        eligible(user);check_cap(db,user)
        if body.contribution_minor is not None: fixed_plan(body)
        elif not ctx.sandbox: fail('Enter a fixed contribution amount',422)
        validate_circle_setup(db,body)
        if body.start_date<date.today(): fail('Start date cannot be in the past',422)
        seed=secret()
        c=Circle(creator_id=user.id,name=body.name,config=body.model_dump(mode='json'),seed=ctx.vault.seal(seed),commitment=digest(seed))
        db.add(c);db.flush();db.add(Participant(circle_id=c.id,user_id=user.id));db.flush()
        audit(db,user,c.id,'created')
        return circle_view(db,c,user)

    @router.get('/circles/{cid}')
    def detail(cid:str,db=Depends(dbdep),user=Depends(ctx.actor)):
        c=owned(db,cid,user)
        result=circle_view(db,c,user)
        if not c.config['identities_hidden']:
            for member in result['members']:
                identity=db.scalar(select(IdentityCase).where(IdentityCase.user_id==member['id'],IdentityCase.status=='Approved'))
                if identity: member['display_name']=json.loads(ctx.vault.open(identity.encrypted_data))['legal_name']
        return result

    @router.put('/circles/{cid}')
    def edit(cid:str,body:CircleInput,db=Depends(dbdep),user=Depends(ctx.actor)):
        validate_circle_setup(db,body)
        if body.contribution_minor is not None: fixed_plan(body)
        c=owned(db,cid,user)
        if c.state not in ['Draft','Recruiting','Finalizable']: fail('Frozen schemes require a new contract version')
        if body.planned_members<len(participants(db,cid)): fail('New cap is below current membership')
        c.config=body.model_dump(mode='json');c.name=body.name
        if c.state!='Draft': transition(db,c,'Recruiting',user,'Configuration changed; recruitment reopened')
        audit(db,user,cid,'configuration_updated')
        return circle_view(db,c,user)

    @router.post('/circles/{cid}/publish')
    def publish(cid:str,db=Depends(dbdep),user=Depends(ctx.actor)):
        c=owned(db,cid,user)
        if c.state!='Draft': fail('Only a draft can be published')
        transition(db,c,'Recruiting',user,'Recruitment opened')
        return circle_view(db,c,user)

    @router.post('/circles/{cid}/invitations',status_code=201)
    def invite(cid:str,body:InviteInput,db=Depends(dbdep),user=Depends(ctx.actor)):
        c=owned(db,cid,user)
        if c.state!='Recruiting': fail('Recruitment is not open')
        if c.config['invite_permission']=='creator-only' and c.creator_id!=user.id: fail('Only the creator can generate invitations',403)
        code=digest(cid+':'+user.id+':'+secret())
        i=Invitation(circle_id=cid,generator_id=user.id,code_hash=digest(code),max_uses=body.max_uses,
                     expires=int(time.time())+body.expires_hours*3600,
                     recipient_hash=ctx.vault.fingerprint(body.recipient_email.lower()) if body.recipient_email else None)
        db.add(i);db.flush();audit(db,user,cid,'invitation_created',invitation_id=i.id)
        return {'id':i.id,'code':code,'circle_id':cid,'expires':i.expires,'link':f'/app#invite={cid}:{code}'}

    @router.get('/circles/{cid}/invitations')
    def invitations(cid:str,db=Depends(dbdep),user=Depends(ctx.actor)):
        owned(db,cid,user)
        return [dict(id=i.id,generator_id=i.generator_id,uses=i.uses,max_uses=i.max_uses,expires=i.expires,revoked=i.revoked)
                for i in rows(db,Invitation,Invitation.circle_id==cid,Invitation.generator_id==user.id)]

    @router.post('/invitations/{iid}/revoke')
    def revoke(iid:str,db=Depends(dbdep),user=Depends(ctx.actor)):
        i=get(db,Invitation,iid)
        if i.generator_id!=user.id: fail('Only the generator can revoke this invitation',403)
        i.revoked=True;audit(db,user,i.circle_id,'invitation_revoked',invitation_id=i.id)
        return {'revoked':True}

    @router.post('/circles/{cid}/join')
    def join(cid:str,body:JoinInput,db=Depends(dbdep),user=Depends(ctx.actor)):
        eligible(user);c=get(db,Circle,cid);ms=participants(db,cid)
        if any(m.user_id==user.id for m in ms): return circle_view(db,c,user)
        if c.state!='Recruiting' or c.removed: fail('Recruitment closed')
        check_cap(db,user)
        if user.score<c.config['trust_threshold']: fail('Trust threshold not met',403)
        maximum=c.config['planned_members']
        if len(ms)>=maximum: fail('Circle is full')
        invite=None
        if body.code:
            invite=db.scalar(select(Invitation).where(Invitation.circle_id==cid,Invitation.code_hash==digest(body.code)))
            if not invite or invite.revoked or invite.expires<time.time() or invite.uses>=invite.max_uses: fail('Invalid or expired invitation',403)
            if invite.recipient_hash and invite.recipient_hash!=ctx.vault.fingerprint(user.email): fail('Invitation belongs to another recipient',403)
        elif c.config['privacy']=='private' or c.config['premium']: fail('Invitation required',403)
        previous=db.scalar(select(Participant).where(Participant.circle_id==cid,Participant.user_id==user.id))
        if previous:
            previous.status='Joined';previous.inviter_id=invite.generator_id if invite else None
        else: db.add(Participant(circle_id=cid,user_id=user.id,inviter_id=invite.generator_id if invite else None))
        if invite: invite.uses+=1
        db.flush();audit(db,user,cid,'joined')
        if len(ms)+1==c.config['planned_members']:
            transition(db,c,'Finalizable',user,'Planned membership reached')
        for m in participants(db,cid): notify(db,m.user_id,'join:'+cid+':'+user.id,'Member joined',c.name+' contributions have been recalculated')
        return circle_view(db,c,user)

    @router.post('/circles/{cid}/leave')
    def leave(cid:str,db=Depends(dbdep),user=Depends(ctx.actor)):
        c=owned(db,cid,user)
        if c.state not in ['Draft','Recruiting','Finalizable']: fail('Cannot leave frozen obligations')
        if c.creator_id==user.id: fail('Creator must cancel an uncontracted circle instead of leaving')
        m=next(m for m in participants(db,cid) if m.user_id==user.id);m.status='Left'
        transition(db,c,'Recruiting',user,'Member left; contributions recalculated')
        return {'status':'Left'}

    @router.post('/circles/{cid}/close-recruitment')
    def close(cid:str,db=Depends(dbdep),user=Depends(ctx.actor)):
        c=owned(db,cid,user)
        if c.state!='Recruiting': fail('Recruitment must be open')
        required=c.config['planned_members'] if c.config['strict_minimum'] else c.config['minimum_members']
        if len(participants(db,cid))<required: fail('Minimum membership not reached')
        transition(db,c,'Finalizable',user,'Recruitment closed')
        return circle_view(db,c,user)

    @router.post('/circles/{cid}/cancel')
    def cancel(cid:str,body:Reason,db=Depends(dbdep),user=Depends(ctx.actor)):
        c=owned(db,cid,user)
        if c.state not in ['Draft','Recruiting','Finalizable']: fail('Contracted schemes cannot be cancelled by a participant')
        transition(db,c,'Cancelled',user,body.reason)
        return circle_view(db,c,user)

    @router.post('/circles/{cid}/finalize')
    def finalize(cid:str,body:FinalizeInput,db=Depends(dbdep),user=Depends(ctx.actor)):
        c=owned(db,cid,user)
        if c.state!='Finalizable': fail('Scheme must be finalizable')
        p=assert_launch_policy(db,c,ctx.sandbox)
        if date.fromisoformat(c.config['start_date'])<date.today(): fail('Update the expired start date before finalization')
        ms=participants(db,cid);ids=[m.user_id for m in ms]
        for member in ms:
            eligible(get(db,Account,member.user_id))
            if not db.scalar(select(Bank.id).where(Bank.user_id==member.user_id,Bank.status=='Verified',Bank.mandate==True)):
                fail('Every member must have a verified bank mandate')
        proof=None
        if c.config['payout_order_mode']=='random':
            seed=ctx.vault.open(c.seed)
            ordered=sorted(ids,key=lambda i:digest(seed+':'+i))
            proof={'seed':seed,'commitment':c.commitment,'algorithm':'sort SHA256(seed + colon + user_id)'}
        else:
            ordered=body.payout_order
            if len(ordered)!=len(ids) or set(ordered)!=set(ids): fail('Specify every member exactly once',422)
        try: planned=schedule(c.config,ordered,p)
        except ValueError as exc: fail(str(exc),422)
        version=len(rows(db,Contract,Contract.circle_id==cid))+1
        content=dict(name=c.name,circle_id=cid,version=version,currency=c.config['currency'],config=c.config,
                     policy_version=policy(db).id,policy=p,sandbox=ctx.sandbox,proof=proof,
                     members=[{'id':i,'pseudonym':get(db,Account,i).pseudonym} for i in ordered],schedule=planned)
        hashed=digest(canonical(content));pdf=render_contract(content,hashed)
        con=Contract(circle_id=cid,version=version,content=content,digest=hashed,pdf=pdf,pdf_hash=hashlib.sha256(pdf).hexdigest())
        db.add(con);db.flush();c.contract_id=con.id
        for m in ms: m.rank=ordered.index(m.user_id)
        transition(db,c,'PendingSignatures',user,'New immutable contract version ready')
        return {'contract_id':con.id,'hash':hashed,'version':version}

    @router.get('/circles/{cid}/contracts')
    def contracts(cid:str,db=Depends(dbdep),user=Depends(ctx.actor)):
        c=get(db,Circle,cid);require_member(db,c,user,staff=True)
        return [dict(id=x.id,version=x.version,hash=x.digest,pdf_hash=x.pdf_hash,current=x.id==c.contract_id)
                for x in rows(db,Contract,Contract.circle_id==cid)]

    @router.get('/contracts/{conid}')
    def contract(conid:str,db=Depends(dbdep),user=Depends(ctx.actor)):
        con=get(db,Contract,conid);contract_access(db,con,user)
        return dict(id=con.id,hash=con.digest,content=con.content,
                    signed_by=[s.user_id for s in rows(db,Signature,Signature.contract_id==conid)])

    @router.get('/contracts/{conid}/pdf')
    def pdf(conid:str,db=Depends(dbdep),user=Depends(ctx.actor)):
        con=get(db,Contract,conid);contract_access(db,con,user)
        audit(db,user,conid,'contract_download')
        return Response(con.pdf,media_type='application/pdf',headers={'Content-Disposition':f'attachment; filename="ajo-contract-v{con.version}.pdf"','ETag':con.pdf_hash})

    @router.post('/contracts/{conid}/sign')
    def sign(conid:str,body:SignInput,request:Request,db=Depends(dbdep),user=Depends(ctx.actor)):
        con=get(db,Contract,conid);c=owned(db,con.circle_id,user);eligible(user)
        if c.contract_id!=conid or c.state!='PendingSignatures' or con.digest!=body.contract_hash: fail('Current pending contract hash required')
        if not ctx.sandbox: fail('Live signature provider and legal terms are not configured',503)
        if not db.scalar(select(Signature.id).where(Signature.contract_id==conid,Signature.user_id==user.id)):
            db.add(Signature(contract_id=conid,user_id=user.id,typed_name=ctx.vault.seal(body.typed_name),
                             ip=ctx.vault.seal(request.client.host),device=ctx.vault.seal(request.headers.get('user-agent','unknown')[:500])))
            audit(db,user,conid,'sandbox_signed',hash=body.contract_hash)
            db.flush()
        if len(rows(db,Signature,Signature.contract_id==conid))==len(con.content['members']):
            if date.fromisoformat(c.config['start_date'])<date.today(): fail('Start date passed; request a new version')
            for row in con.content['schedule']: db.add(Due(circle_id=c.id,**row))
            transition(db,c,'Active',user,'All finalized members signed')
        return {'state':c.state}

    @router.post('/circles/{cid}/request-revision')
    def revision(cid:str,body:Reason,db=Depends(dbdep),user=Depends(ctx.actor)):
        c=owned(db,cid,user)
        if c.state!='PendingSignatures': fail('Only an unactivated proposal may be revised')
        # Prior immutable versions/signatures remain evidence; no obligations have activated.
        c.contract_id=None
        transition(db,c,'Finalizable',user,'Proposal withdrawn for re-signature: '+body.reason)
        return {'state':c.state}

    @router.get('/circles/{cid}/schedule')
    def calendar(cid:str,db=Depends(dbdep),user=Depends(ctx.actor)):
        c=get(db,Circle,cid);require_member(db,c,user,staff=True)
        return [dict(id=d.id,user_id=d.user_id,date=d.date,kind=d.kind,amount_minor=d.amount_minor,
                     status=d.status,attempts=d.attempts,window=d.window) for d in rows(db,Due,Due.circle_id==cid)]

    return router
