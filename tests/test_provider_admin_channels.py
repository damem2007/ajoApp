import time
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.platform.providers import resolve_provider, register_provider, SandboxPayments, SandboxIdentity, SandboxNotifications
from app.platform.models import Account, Notice, StaffMembership, StaffInvitation
from app.platform.rbac import assign
from app.platform.security import secret,digest
from tests.test_full_platform import client,request


def test_registered_provider_contracts_are_database_independent(monkeypatch):
    from app.config import provider_name, database_url
    for kind,cls in [('payments',SandboxPayments),('identity',SandboxIdentity),('notifications',SandboxNotifications)]:
        monkeypatch.setenv('AJO_'+kind.upper()+'_PROVIDER','sandbox')
        assert isinstance(resolve_provider(kind,provider_name(kind)),cls)
    register_provider('payments','fixture',SandboxPayments)
    monkeypatch.setenv('AJO_PAYMENTS_PROVIDER','fixture')
    assert isinstance(resolve_provider('payments',provider_name('payments')),SandboxPayments)
    assert database_url().get_backend_name()=='sqlite'
    provider=resolve_provider('payments','sandbox')
    with pytest.raises(ValueError): provider.link_bank(bank_token='real-bank-details')
    provider.link_bank(bank_token='sandbox-ok-configured-account')
    assert provider.execute(key='test',amount_minor=100,currency='CAD',kind='payout',bank_token='sandbox-ok-configured-account').reference=='sandbox:test'
    assert provider.execute(key='test-fail',amount_minor=100,currency='CAD',kind='contribution',bank_token='sandbox-fail-configured-account').status=='Failed'


def test_channels_configuration_and_notifications(client):
    c=client
    channels=request(c,'GET','/admin/channels',user='u3')
    assert {row['id'] for row in channels.json()}=={'in-app','email','sms','push'}
    assert request(c,'PUT','/admin/channels/sms',{'enabled':False,'display_name':'SMS','reason':'Pause SMS delivery'}).status_code==403
    assert request(c,'PUT','/admin/channels/sms',{'enabled':False,'display_name':'SMS','reason':'Pause SMS delivery'},user='u3').status_code==200
    from app.platform.services import notify
    with Session(c.app.state.ctx.engine) as db,db.begin():
        notify(db,'u0','configured','Update','Configured channels')
        assert not list(db.scalars(select(Notice).where(Notice.key=='configured:u0:sms')))
        assert list(db.scalars(select(Notice).where(Notice.key=='configured:u0:in-app')))


@pytest.mark.parametrize('role,allowed,denied',[
    ('ops','/admin/payments','/admin/channels'),
    ('compliance','/admin/kyc','/admin/policies'),
    ('support','/admin/payments','/admin/kyc'),
    ('admin','/admin/channels',None),
])
def test_persisted_role_permissions_enforced(client,role,allowed,denied):
    c=client
    with Session(c.app.state.ctx.engine) as db,db.begin(): assign(db,db.get(Account,'u0'),role,db.get(Account,'u3'))
    assert request(c,'GET',allowed).status_code==200
    if denied: assert request(c,'GET',denied).status_code==403


def test_staff_invite_accept_and_disable(client):
    c=client
    body={'email':'u0@example.test','role':'ops','reason':'Onboard operations colleague'}
    assert request(c,'POST','/admin/staff-invitations',body).status_code==403
    invitation=request(c,'POST','/admin/staff-invitations',body,user='u3')
    assert invitation.status_code==201
    assert 'token' not in invitation.json()
    with Session(c.app.state.ctx.engine) as db:
        notice=db.scalar(select(Notice).where(Notice.title=='Staff invitation'))
        email,token=c.app.state.ctx.vault.open(notice.body).split('\n')
        assert email=='u0@example.test'
    accepted=request(c,'POST','/auth/staff-invitations/accept',{'token':token})
    assert accepted.status_code==200
    with Session(c.app.state.ctx.engine) as db:
        assert db.get(StaffMembership,'u0').role_id=='ops'
        assert db.get(StaffInvitation,invitation.json()['id']).status=='active'
    assert request(c,'POST','/admin/users/u0/status',{'suspended':True,'reason':'Disable staff access'},user='u3').status_code==200
    assert request(c,'GET','/admin/payments').status_code in [401,403]
    assert request(c,'POST','/admin/staff-invitations',{**body,'role':'owner'},user='u3').status_code==422
