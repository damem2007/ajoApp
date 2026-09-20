"""Shared domain services. Callers own the database transaction."""
import base64
import hashlib
import json
import os
from app.config import environment_path
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from fastapi import HTTPException
from sqlalchemy import select, func
from .models import (Account, Policy, Circle, Participant, Contract, Signature, Due, NotificationChannel,
                     Posting, TrustEvent, Notice, Audit, Bank, PaymentEvent, IdentityCase)
from .schemas import PolicyInput
from .security import Vault, digest

TERMINAL = ['Completed', 'Cancelled']

def fail(message, status=409): raise HTTPException(status, message)
def get(db, model, key):
    obj = db.get(model, key)
    if obj is None: fail('Resource not found',404)
    return obj
def rows(db, model, *filters): return list(db.scalars(select(model).where(*filters)))
def policy(db): return db.scalar(select(Policy).order_by(Policy.id.desc()).limit(1))
def audit(db, actor, resource, action, **detail):
    db.add(Audit(actor_id=actor.id if hasattr(actor,'id') else actor,
                 resource=resource,action=action,detail=detail))

def notify(db, user_id, key, title, body, channels=None):
    user = get(db,Account,user_id)
    template=policy(db).data.get('notification_templates',{}).get(title)
    if template and title not in {'Verification code','Staff invitation'}: body=template.replace('{body}',body)
    configured = {row.id:row for row in db.scalars(select(NotificationChannel))}
    requested = list(configured) if channels is None else channels
    for channel in requested:
        config = configured.get(channel)
        if not config or not config.enabled:
            if channels is not None: fail('Notification channel is unavailable: '+channel,409)
            continue
        if channels is None and channel not in ('in-app',) and user.preferences.get(channel,True) is False: continue
        unique = f'{key}:{user_id}:{channel}'
        if db.scalar(select(Notice.id).where(Notice.key==unique)): continue
        db.add(Notice(user_id=user_id,key=unique,channel=channel,title=title,body=body,
                      status='Delivered' if channel=='in-app' else 'Queued'))
    db.flush()

def participants(db,cid):
    return list(db.scalars(select(Participant).where(Participant.circle_id==cid,
                       Participant.status!='Left').order_by(Participant.joined_at,Participant.id)))

def require_member(db,circle,user,staff=False):
    from .rbac import has_permission
    if staff and has_permission(db,user,'circles.view'): return
    if not any(m.user_id==user.id for m in participants(db,circle.id)): fail('Membership required',403)

def eligible(user):
    if user.suspended or not user.email_verified or not user.phone_verified or user.kyc_status!='Approved':
        fail('Verified channels and approved KYC are required',403)

def cap(db,user):
    return max(t['cap'] for t in policy(db).data['tiers'] if t['score']<=max(0,user.score))

def commitments(db,user):
    return db.scalar(select(func.count()).select_from(Participant).join(Circle).where(
        Participant.user_id==user.id,Participant.status!='Left',Circle.state.notin_(TERMINAL)))

def check_cap(db,user):
    if commitments(db,user)>=cap(db,user): fail('Concurrent scheme cap reached')

def transition(db,circle,state,actor,reason):
    old=circle.state
    circle.state=state
    audit(db,actor,circle.id,'state_transition',old=old,new=state,reason=reason)
    for m in participants(db,circle.id):
        notify(db,m.user_id,f'state:{circle.id}:{state}:{time.time_ns()}',
               'Circle status changed',f'{circle.name}: {state}. {reason}')

def trust(db,user_id,delta,key,reason,circle_id=None,propagate=True):
    if db.scalar(select(TrustEvent.id).where(TrustEvent.key==key)): return
    user=get(db,Account,user_id)
    user.score+=delta
    db.add(TrustEvent(user_id=user_id,circle_id=circle_id,key=key,delta=delta,reason=reason))
    db.flush()
    notify(db,user_id,'trust:'+key,'Trust score changed',f'{delta:+d} points: {reason}')
    if delta<0 and propagate and circle_id:
        member=db.scalar(select(Participant).where(Participant.circle_id==circle_id,Participant.user_id==user_id))
        if member and member.inviter_id:
            circle=get(db,Circle,circle_id)
            frozen=get(db,Contract,circle.contract_id).content['policy'] if circle.contract_id else policy(db).data
            penalty=(abs(delta)*frozen['inviter_penalty_bps']+9999)//10000
            if penalty: trust(db,member.inviter_id,-penalty,key+':inviter','Inviter accountability: '+reason,circle_id,False)

def balances(db,cid):
    return {account:amount for account,amount in db.execute(select(Posting.account,func.sum(Posting.amount_minor)).where(
        Posting.circle_id==cid).group_by(Posting.account))}

def obligation(db,circle,user_id):
    dues=rows(db,Due,Due.circle_id==circle.id,Due.user_id==user_id)
    postings=rows(db,Posting,Posting.circle_id==circle.id,Posting.user_id==user_id)
    contributed=-sum(p.amount_minor for p in postings if p.account=='member_contributions')
    collected=sum(p.amount_minor for p in postings if p.account=='member_payouts')
    fees=-sum(p.amount_minor for p in postings if p.account=='fee_income')
    total=sum(d.amount_minor for d in dues if d.kind=='contribution') if circle.contract_id else circle.config['target_minor']
    return dict(contributed_minor=contributed,collected_minor=collected,fees_minor=fees,
                net_position_minor=contributed-collected,remaining_obligation_minor=total-contributed,
                position='payback' if collected else 'credit')

def account_view(db,u):
    from .rbac import permissions
    return dict(permissions=sorted(permissions(db,u)),id=u.id,email=u.email,phone=u.phone,email_verified=u.email_verified,phone_verified=u.phone_verified,
                kyc_status=u.kyc_status,pseudonym=u.pseudonym,role=u.role,suspended=u.suspended,
                trust_score=u.score,scheme_cap=cap(db,u),commitments=commitments(db,u),mfa_enabled=u.mfa_enabled)

def circle_view(db,circle,user=None,staff=False):
    ms=participants(db,circle.id)
    is_member=user and any(m.user_id==user.id for m in ms)
    result=dict(id=circle.id,name=circle.name,state=circle.state,config=circle.config,
                count=len(ms),featured=circle.featured,removed=circle.removed,commitment=circle.commitment,
                provisional=circle.state in ['Draft','Recruiting'],
                per_payout_window_minor={'quotient':circle.config.get('contribution_minor') or circle.config['target_minor']//max(1,len(ms)),
                                        'remainder':0 if circle.config.get('contribution_minor') else circle.config['target_minor']%max(1,len(ms))})
    if is_member or staff:
        result['members']=[]
        for m in sorted(ms,key=lambda m:m.rank if m.rank is not None else 999):
            account=get(db,Account,m.user_id)
            item=dict(id=m.user_id,pseudonym=account.pseudonym,rank=m.rank,status=m.status)
            if not circle.config['identities_hidden']:
                # Legal names are populated from reviewed KYC via a separate authorized identity view.
                item['display_name']=account.pseudonym
            result['members'].append(item)
        result['contract_id']=circle.contract_id
        result['pool_minor']=balances(db,circle.id).get('pool',0)
        if is_member: result['obligation']=obligation(db,circle,user.id)
    return result

def load_vault(sandbox):
    # Production receives a mounted secret from a vault; no plaintext secret env value required.
    filename=environment_path('AJO_KEY_FILE',required=False)
    if filename:
        return Vault(base64.urlsafe_b64decode(Path(filename).read_bytes().strip()))
    if not sandbox: return None
    path=environment_path('AJO_DATA_DIR')
    path.mkdir(mode=0o700,parents=True,exist_ok=True)
    keyfile=path/'sandbox.key'
    if not keyfile.exists():
        try:
            fd=os.open(str(keyfile),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'wb') as stream: stream.write(base64.urlsafe_b64encode(os.urandom(32)))
        except FileExistsError: pass
    return Vault(base64.urlsafe_b64decode(keyfile.read_bytes()))

def seed_policy(db,sandbox):
    if policy(db): return
    p=PolicyInput().model_dump()
    if sandbox:
        p.update(mixed_frequency_policy='payout_window',calendar_policy='utc_calendar_clip',
                 overflow_strategy='extend_rotation',random_policy='server_commitment',
                 default_policy='hold_payout_flag_member',fee_mode='none',
                 launch_countries=['NG','CA','US','GB'],
                 id_types={c:['passport','national-id','drivers-license'] for c in ['NG','CA','US','GB']})
    db.add(Policy(data=p,actor_id='system',reason='Sandbox example policies' if sandbox else 'Unresolved launch policies'))
    db.flush()

def assert_launch_policy(db,circle,sandbox):
    p=policy(db).data
    required=['calendar_policy','default_policy','fee_mode']
    if circle.config['contribution_frequency']!=circle.config['collection_frequency']: required+=['mixed_frequency_policy']
    if circle.config['allow_overflow']: required+=['overflow_strategy']
    if circle.config['payout_order_mode']=='random': required+=['random_policy']
    missing=[k for k in required if p.get(k) is None]
    if not sandbox and not p['legal_approved']: missing+=['legal_approved']
    if missing: fail('Unresolved policies: '+', '.join(missing))
    return p
