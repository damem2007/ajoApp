"""Application-owned staff onboarding, channel configuration and RBAC visibility."""
import time
from typing import Literal
from fastapi import APIRouter, Depends
from sqlalchemy import select, delete
from .models import StaffRole, StaffMembership, StaffInvitation, NotificationChannel, SessionToken, Account, Notice, now
from .schemas import Input, Reason
from .security import secret, digest
from .services import audit, notify, get, fail
from .rbac import assign, permissions
from pydantic import Field

class StaffInvite(Input):
    email: str = Field(pattern=r'^[^\s@]+@[^\s@]+\.[^\s@]+$',max_length=254)
    role: Literal['admin','ops','compliance','support']
    reason: str = Field(min_length=5,max_length=2000)

class AcceptInvite(Input):
    token: str = Field(min_length=20,max_length=200)

class ChannelChange(Reason):
    enabled: bool
    display_name: str = Field(min_length=1,max_length=80)


def routes(ctx):
    router=APIRouter(prefix='/api/v1',tags=['Backoffice setup'])
    @router.get('/admin/roles')
    def roles(db=Depends(ctx.session),user=Depends(ctx.require_permission('roles.assign'))):
        return [{'id':r.id,'permissions':r.permissions} for r in db.scalars(select(StaffRole))]

    @router.get('/admin/staff-invitations')
    def invitations(db=Depends(ctx.session),user=Depends(ctx.require_permission('members.manage'))):
        return [dict(id=i.id,email=i.email,role=i.role_id,status=i.status,expires=i.expires,created_by=i.created_by,created_at=i.created_at) for i in db.scalars(select(StaffInvitation))]

    @router.post('/admin/staff-invitations',status_code=201)
    def invite(body:StaffInvite,db=Depends(ctx.session),user=Depends(ctx.require_permission('members.manage'))):
        if db.scalar(select(StaffInvitation).where(StaffInvitation.email==body.email.lower(),StaffInvitation.status=='invited',StaffInvitation.expires>int(time.time()))): fail('An active invitation already exists',409)
        token=secret()
        invitation=StaffInvitation(email=body.email.lower(),role_id=body.role,token_hash=digest(token),expires=int(time.time())+86400*3,created_by=user.id)
        db.add(invitation);db.flush()
        # Token is delivered only to its recipient, encrypted in the notification outbox.
        in_app=db.get(NotificationChannel,'in-app')
        if in_app and in_app.enabled:
            notify(db,user.id,'staff-invite:'+invitation.id,'Staff invitation created','Invitation created for '+body.email.lower(),channels=['in-app'])
        channel=db.get(NotificationChannel,'email')
        if not channel or not channel.enabled: fail('Enable email delivery before inviting staff',409)
        # Staff invitations use a dedicated encrypted delivery payload with recipient context.
        notify(db,user.id,'staff-invitation:'+invitation.id,'Staff invitation',ctx.vault.seal(body.email.lower()+'\n'+token),channels=['email'])
        audit(db,user,invitation.id,'staff_invited',role=body.role,email=body.email.lower(),reason=body.reason)
        return {'id':invitation.id,'status':'invited'}

    @router.post('/auth/staff-invitations/accept')
    def accept(body:AcceptInvite,db=Depends(ctx.session),user=Depends(ctx.actor)):
        invitation=db.scalar(select(StaffInvitation).where(StaffInvitation.token_hash==digest(body.token)))
        if not invitation or invitation.status!='invited' or invitation.expires<=time.time(): fail('Invitation is invalid or expired',422)
        if user.email.lower()!=invitation.email or not user.email_verified: fail('Sign in with the verified invited email address',403)
        inviter=get(db,Account,invitation.created_by)
        if 'members.manage' not in permissions(db,inviter): fail('Inviting administrator no longer has onboarding authority',403)
        assign(db,user,invitation.role_id,inviter)
        invitation.status='active';invitation.accepted_by=user.id
        db.execute(delete(SessionToken).where(SessionToken.user_id==user.id))
        audit(db,user,invitation.id,'staff_invitation_accepted',role=invitation.role_id)
        return {'status':'active','role':invitation.role_id,'sign_in_required':True}

    @router.get('/auth/staff-invitations/test-inbox')
    def test_inbox(db=Depends(ctx.session),user=Depends(ctx.actor)):
        ctx.require_sandbox('notifications')
        if not user.email_verified: fail('Verify your email before reading test invitations',403)
        result=[]
        for invitation in db.scalars(select(StaffInvitation).where(StaffInvitation.email==user.email.lower(),StaffInvitation.status=='invited',StaffInvitation.expires>int(time.time()))):
            notice=db.scalar(select(Notice).where(Notice.key=='staff-invitation:'+invitation.id+':'+invitation.created_by+':email'))
            if notice:
                recipient,token=ctx.vault.open(notice.body).split('\n',1)
                if recipient==user.email.lower(): result.append({'id':invitation.id,'token':token,'role':invitation.role_id})
        return result

    @router.get('/admin/channels')
    def channels(db=Depends(ctx.session),user=Depends(ctx.require_permission('channels.view'))):
        return [dict(id=c.id,display_name=c.display_name,enabled=c.enabled,created_at=c.created_at,updated_at=c.updated_at) for c in db.scalars(select(NotificationChannel))]

    @router.put('/admin/channels/{channel}')
    def change(channel:str,body:ChannelChange,db=Depends(ctx.session),user=Depends(ctx.require_permission('channels.manage'))):
        c=get(db,NotificationChannel,channel)
        c.enabled=body.enabled;c.display_name=body.display_name;c.updated_at=now()
        audit(db,user,channel,'channel_configured',enabled=c.enabled,display_name=c.display_name,reason=body.reason)
        return {'id':c.id,'enabled':c.enabled}
    @router.get('/admin/sync/status')
    def sync_status(db=Depends(ctx.session),user=Depends(ctx.require_permission('sync.view'))):
        if not ctx.router:
            return {'enabled':False,'active':ctx.engine.dialect.name,'operations':[],'batches':[]}
        from .models import DegradedOperation
        operations=[dict(
            id=o.id,
            operation_type=o.operation_type,
            aggregate_type=o.aggregate_type,
            aggregate_id=o.aggregate_id,
            status=o.sync_status,
            sequence=o.sequence,
            attempts=o.retry_count,
            error_code=o.last_error,
            result=o.result,
            created_at=o.created_at,
            synced_at=o.synced_at,
        ) for o in db.scalars(select(DegradedOperation).order_by(
            DegradedOperation.sequence.desc(),DegradedOperation.created_at.desc()
        ).limit(100))]
        # "batches" is retained temporarily for existing backoffice clients while
        # the new operation-journal terminology rolls out.
        return {'enabled':True,'active':ctx.router.mode,'operations':operations,'batches':operations}
    return router
