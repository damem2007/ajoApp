import os
from datetime import date,timedelta
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.platform.application import create_platform
from app.platform.models import Account,Bank,Policy,Posting,Due,Signature
from app.platform.security import password_hash,totp
from app.platform.calendar import schedule,occurrence
from app.platform.schemas import PolicyInput

PASSWORD='Local-testing-password-42'

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('AJO_DATA_DIR',str(tmp_path/'secrets'))
    app=create_platform(f'sqlite:///{tmp_path}/platform.db',sandbox=True)
    with TestClient(app) as c:
        with Session(app.state.ctx.engine) as db,db.begin():
            for i in range(4):
                u=Account(id=f'u{i}',email=f'u{i}@example.test',phone=f'+1555555000{i}',password=password_hash(PASSWORD),
                          email_verified=True,phone_verified=True,kyc_status='Approved',pseudonym=f'Person {i}',role='admin' if i==3 else 'member')
                db.add(u);db.flush();token=f'sandbox-ok-{i}'
                db.add(Bank(user_id=u.id,token_hash=app.state.ctx.vault.fingerprint(token),encrypted_token=app.state.ctx.vault.seal(token),
                            masked='000'+str(i),status='Verified',mandate=True))
            from app.platform.rbac import bootstrap
            bootstrap(db)
        c.tokens={}
        for i in range(4):
            r=c.post('/api/v1/auth/login',json={'email':f'u{i}@example.test','password':PASSWORD})
            assert r.status_code==200,r.text
            c.tokens[f'u{i}']=r.json()['access_token']
        yield c

def request(c,method,path,body=None,user='u0'):
    return c.request(method,'/api/v1'+path,json=body,headers={'Authorization':'Bearer '+c.tokens[user]})

def new_circle(c,**overrides):
    cfg=dict(name='Test circle',target_minor=10001,start_date=date.today().isoformat(),minimum_members=3,
             planned_members=3,hard_cap=3)
    cfg.update(overrides)
    r=request(c,'POST','/circles',cfg);assert r.status_code==201,r.text
    cid=r.json()['id'];r=request(c,'POST',f'/circles/{cid}/publish');assert r.status_code==200,r.text
    return cid

def activate(c,**overrides):
    cid=new_circle(c,**overrides)
    for user in ['u1','u2']:
        r=request(c,'POST',f'/circles/{cid}/join',{},user);assert r.status_code==200,r.text
    r=request(c,'POST',f'/circles/{cid}/finalize',{'payout_order':['u2','u0','u1']});assert r.status_code==200,r.text
    con=r.json()
    for user in ['u0','u1','u2']:
        r=request(c,'POST',f'/contracts/{con["contract_id"]}/sign',{'contract_hash':con['hash'],'typed_name':'Test Person','accepted':True},user)
        assert r.status_code==200,r.text
    assert r.json()['state']=='Active'
    return cid,con

def test_calendar_mixed_frequency_conservation():
    p=PolicyInput(fee_mode='none').model_dump()
    cfg=dict(start_date='2028-01-31',target_minor=10001,contribution_frequency='weekly',collection_frequency='monthly')
    result=schedule(cfg,['a','b','c'],p)
    assert occurrence(date(2028,1,31),'monthly',1)==date(2028,2,29)
    assert occurrence(date(2028,1,31),'monthly',2)==date(2028,3,31)
    for i in range(3): assert sum(r['amount_minor'] for r in result if r['window']==i and r['kind']=='contribution')==10001
    for u in ['a','b','c']: assert sum(r['amount_minor'] for r in result if r['user_id']==u and r['kind']=='contribution')==10001
    cfg['contribution_frequency']='yearly'
    with pytest.raises(ValueError): schedule(cfg,['a','b','c'],p)

def test_full_rotation_and_ledger(client):
    cid,con=activate(client,contribution_frequency='weekly',collection_frequency='monthly')
    end=(date.today()+timedelta(days=100)).isoformat()
    r=request(client,'POST','/admin/jobs/run',{'as_of':end},'u3');assert r.status_code==200,r.text
    assert request(client,'GET',f'/circles/{cid}').json()['state']=='Completed'
    for u in ['u0','u1','u2']:
        v=request(client,'GET',f'/circles/{cid}',user=u).json()['obligation']
        assert v['contributed_minor']==v['collected_minor']==10001
        assert v['remaining_obligation_minor']==v['net_position_minor']==0
    with Session(client.app.state.ctx.engine) as db:
        entries=list(db.scalars(select(Posting)));count=len(entries)
        assert sum(e.amount_minor for e in entries)==0
    request(client,'POST','/admin/jobs/run',{'as_of':end},'u3')
    with Session(client.app.state.ctx.engine) as db: assert len(list(db.scalars(select(Posting))))==count
    pdf=request(client,'GET',f'/contracts/{con["contract_id"]}/pdf')
    assert pdf.status_code==200 and pdf.content.startswith(b'%PDF')

def test_private_invites_and_permissions(client):
    cid=new_circle(client,privacy='private',invite_permission='creator-only')
    assert request(client,'GET','/marketplace',user='u1').json()==[]
    assert request(client,'GET',f'/circles/{cid}',user='u1').status_code==403
    assert request(client,'POST',f'/circles/{cid}/join',{},'u1').status_code==403
    invite=request(client,'POST',f'/circles/{cid}/invitations',{'recipient_email':'u1@example.test'}).json()
    assert request(client,'POST',f'/circles/{cid}/join',{'code':invite['code']},'u2').status_code==403
    assert request(client,'POST',f'/circles/{cid}/join',{'code':invite['code']},'u1').status_code==200
    assert request(client,'POST',f'/circles/{cid}/invitations',{},'u1').status_code==403
    assert request(client,'GET','/admin/users',user='u1').status_code==403

def test_signup_channel_lockout_and_refresh(client):
    r=client.post('/api/v1/auth/register',json={'email':'new@example.test','phone':'+15555551111','password':PASSWORD})
    assert r.status_code==201,r.text
    pair=r.json();client.tokens['new']=pair['access_token']
    assert request(client,'GET','/marketplace',user='new').status_code==403
    inbox=request(client,'GET','/auth/sandbox-inbox',user='new').json()
    for row in inbox:
        assert request(client,'POST','/auth/verify',{'channel':row['channel'],'code':row['code']},'new').status_code==200
    assert request(client,'GET','/me',user='new').json()['email_verified']
    refreshed=client.post('/api/v1/auth/refresh',json={'refresh_token':pair['refresh_token']})
    assert refreshed.status_code==200
    assert client.post('/api/v1/auth/refresh',json={'refresh_token':pair['refresh_token']}).status_code==401
    assert request(client,'GET','/me',user='new').status_code==401

def test_policy_freeze_and_kill_switch(client):
    cid,con=activate(client)
    policies=request(client,'GET','/admin/policies',user='u3').json();p=policies[-1]['data'];p['scheduler_paused']=True
    assert request(client,'POST','/admin/policies',{'policy':p,'reason':'Incident test'},'u3').status_code==201
    r=request(client,'POST','/admin/jobs/run',{},'u3');assert r.json()['paused']
    frozen=request(client,'GET',f'/contracts/{con["contract_id"]}').json()['content']['policy']
    assert frozen['scheduler_paused'] is False

def test_pending_funds_do_not_pay_out(client):
    cid,con=activate(client)
    with Session(client.app.state.ctx.engine) as db,db.begin():
        bank=db.scalar(select(Bank).where(Bank.user_id=='u0'))
        bank.encrypted_token=client.app.state.ctx.vault.seal('sandbox-pending-u0')
    request(client,'POST','/admin/jobs/run',{'as_of':(date.today()+timedelta(days=32)).isoformat()},'u3')
    dues=request(client,'GET',f'/circles/{cid}/schedule').json()
    assert not any(d['kind']=='payout' and d['status']=='Settled' for d in dues)
    assert any(d['status']=='Pending' for d in dues)

def test_reversal_append_only(client):
    cid,_=activate(client)
    request(client,'POST','/admin/jobs/run',{},'u3')
    dues=request(client,'GET',f'/circles/{cid}/schedule').json()
    d=next(d for d in dues if d['kind']=='contribution' and d['status']=='Settled')
    body={'status':'Reversed','event_id':'return-12345','reason':'Sandbox bank return'}
    assert request(client,'POST',f'/admin/payments/{d["id"]}/reconcile',body,'u3').status_code==200
    assert request(client,'POST',f'/admin/payments/{d["id"]}/reconcile',body,'u3').status_code==200
    assert request(client,'GET',f'/circles/{cid}').json()['state']=='Disputed'
    with Session(client.app.state.ctx.engine) as db: assert sum(p.amount_minor for p in db.scalars(select(Posting)))==0

def test_complaint_transition_and_penalty_once(client):
    cid,_=activate(client)
    r=request(client,'POST','/complaints',{'circle_id':cid,'target_id':'u1','category':'other','description':'Test report for investigation'})
    rid=r.json()['id']
    for state in ['Triaged','UnderInvestigation','ActionTaken']:
        body={'status':state,'reason':'Documented sandbox review','trust_delta':-2 if state=='ActionTaken' else 0}
        assert request(client,'POST',f'/admin/complaints/{rid}/resolve',body,'u3').status_code==200
    assert request(client,'POST',f'/admin/complaints/{rid}/resolve',body,'u3').status_code==409
    assert request(client,'GET','/me',user='u1').json()['trust_score']==-2

def test_contract_freeze_and_unanimity(client):
    cid=new_circle(client)
    for u in ['u1','u2']: request(client,'POST',f'/circles/{cid}/join',{},u)
    con=request(client,'POST',f'/circles/{cid}/finalize',{'payout_order':['u0','u1','u2']}).json()
    assert request(client,'POST',f'/contracts/{con["contract_id"]}/sign',{'contract_hash':'stale','typed_name':'Test Person','accepted':True}).status_code==409
    request(client,'POST',f'/contracts/{con["contract_id"]}/sign',{'contract_hash':con['hash'],'typed_name':'Test Person','accepted':True})
    assert request(client,'GET',f'/circles/{cid}').json()['state']=='PendingSignatures'
    assert request(client,'POST',f'/circles/{cid}/leave',{},'u1').status_code==409
    assert request(client,'POST',f'/circles/{cid}/cancel',{'reason':'Unilateral cancellation'}).status_code==409

def test_random_order_proof(client):
    cid=new_circle(client,payout_order_mode='random')
    for u in ['u1','u2']: request(client,'POST',f'/circles/{cid}/join',{},u)
    con=request(client,'POST',f'/circles/{cid}/finalize',{}).json()
    content=request(client,'GET',f'/contracts/{con["contract_id"]}').json()['content']
    from app.platform.security import digest
    assert digest(content['proof']['seed'])==content['proof']['commitment']
    assert [m['id'] for m in content['members']]==sorted(['u0','u1','u2'],key=lambda i:digest(content['proof']['seed']+':'+i))
