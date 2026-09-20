"""Additional boundary tests reuse the full-platform fixture."""
import io
from datetime import date,timedelta
from sqlalchemy import select,text
from sqlalchemy.orm import Session
import pytest
from tests.test_full_platform import client,request,new_circle,activate,PASSWORD
from app.platform.models import Account,IdentityCase,Posting,Policy,Due
from app.platform.security import totp

def test_kyc_upload_review_and_duplicate_flag(client):
    r=client.post('/api/v1/auth/register',json={'email':'onboard@example.test','phone':'+15555559999','password':PASSWORD})
    client.tokens['new']=r.json()['access_token']
    for item in request(client,'GET','/auth/sandbox-inbox',user='new').json():
        request(client,'POST','/auth/verify',{'channel':item['channel'],'code':item['code']},'new')
    docs=[]
    for kind in ['identity','selfie']:
        r=client.post('/api/v1/documents?kind='+kind,files={'file':('test.png',b'\x89PNG\r\n\x1a\nTEST FIXTURE','image/png')},headers={'Authorization':'Bearer '+client.tokens['new']})
        assert r.status_code==201,r.text;docs.append(r.json()['id'])
    payload={'document_id':docs[0],'selfie_id':docs[1],'id_type':'passport','id_number':'TEST12345',
             'country':'CA','province':'BC','expiry':(date.today()+timedelta(days=365)).isoformat(),'dob':'1990-01-01',
             'legal_name':'Fictional Test Member','device_fingerprint':'test-device-12345'}
    r=request(client,'POST','/kyc',payload,'new');assert r.status_code==201,r.text
    kid=r.json()['id']
    assert request(client,'GET',f'/admin/kyc/{kid}',user='new').status_code==403
    assert request(client,'POST',f'/admin/kyc/{kid}/review',{'decision':'Approved','reason':'Sandbox manual fixture validation'},'u3').status_code==200
    assert request(client,'GET','/me',user='new').json()['kyc_status']=='Approved'
    with Session(client.app.state.ctx.engine) as db:
        encrypted=db.get(IdentityCase,kid).encrypted_data
        assert 'TEST12345' not in encrypted and 'Fictional' not in encrypted

def test_otp_limit_persists_on_failure(client):
    pair=client.post('/api/v1/auth/register',json={'email':'otp@example.test','phone':'+15555558888','password':PASSWORD}).json()
    client.tokens['otp']=pair['access_token']
    original=request(client,'GET','/auth/sandbox-inbox',user='otp').json()[0]
    wrong='000000' if original['code']!='000000' else '111111'
    for _ in range(5): assert request(client,'POST','/auth/verify',{'channel':original['channel'],'code':wrong},'otp').status_code==400
    assert request(client,'POST','/auth/verify',{'channel':original['channel'],'code':original['code']},'otp').status_code==409

def test_mfa_revokes_old_sessions_and_prevents_code_reuse(client):
    secret=request(client,'POST','/auth/mfa/setup',{}).json()['secret']
    code=totp(secret)
    assert request(client,'POST','/auth/mfa/enable',{'code':code}).status_code==200
    assert request(client,'GET','/me').status_code==401
    assert client.post('/api/v1/auth/login',json={'email':'u0@example.test','password':PASSWORD,'totp':code}).status_code==401

def test_database_rejects_editing_financial_evidence(client):
    cid,_=activate(client)
    request(client,'POST','/admin/jobs/run',{},'u3')
    with client.app.state.ctx.engine.begin() as connection:
        with pytest.raises(Exception,match='append-only'):
            connection.execute(text('UPDATE ledger_postings SET amount_minor=0'))

def test_contract_version_preserved_and_requires_resigning(client):
    cid=new_circle(client)
    for u in ['u1','u2']: request(client,'POST',f'/circles/{cid}/join',{},u)
    old=request(client,'POST',f'/circles/{cid}/finalize',{'payout_order':['u0','u1','u2']}).json()
    request(client,'POST',f'/contracts/{old["contract_id"]}/sign',{'contract_hash':old['hash'],'typed_name':'Test Member','accepted':True})
    assert request(client,'POST',f'/circles/{cid}/request-revision',{'reason':'Review payout order'}).status_code==200
    new=request(client,'POST',f'/circles/{cid}/finalize',{'payout_order':['u2','u1','u0']}).json()
    assert new['version']==2 and new['hash']!=old['hash']
    assert request(client,'GET',f'/contracts/{old["contract_id"]}').json()['signed_by']==['u0']
    assert request(client,'GET',f'/contracts/{new["contract_id"]}').json()['signed_by']==[]

def test_fees_do_not_fund_the_pool(client):
    p=request(client,'GET','/admin/policies',user='u3').json()[-1]['data']
    p.update(fee_mode='per_contribution',fee_flat_minor=100,fee_bps=100)
    request(client,'POST','/admin/policies',{'policy':p,'reason':'Test separate fee accounting'},'u3')
    cid,_=activate(client)
    request(client,'POST','/admin/jobs/run',{},'u3')
    detail=request(client,'GET',f'/circles/{cid}').json()
    assert detail['pool_minor']==10001
    assert detail['obligation']['fees_minor']>0

def test_concurrent_worker_replay(client):
    from concurrent.futures import ThreadPoolExecutor
    cid,_=activate(client)
    with ThreadPoolExecutor(max_workers=3) as pool:
        results=list(pool.map(lambda _:request(client,'POST','/admin/jobs/run',{},'u3'),range(3)))
    assert all(r.status_code==200 for r in results)
    assert sum(r.json()['processed'] for r in results)==3

def test_unresolved_policy_blocks_finalization(client):
    p=request(client,'GET','/admin/policies',user='u3').json()[-1]['data'];p['calendar_policy']=None
    request(client,'POST','/admin/policies',{'policy':p,'reason':'Policy not yet approved'},'u3')
    cid=new_circle(client)
    for u in ['u1','u2']: request(client,'POST',f'/circles/{cid}/join',{},u)
    r=request(client,'POST',f'/circles/{cid}/finalize',{'payout_order':['u0','u1','u2']})
    assert r.status_code==409 and 'calendar_policy' in r.text

def test_member_export_excludes_credentials(client):
    r=request(client,'GET','/me/export');assert r.status_code==200
    assert 'password' not in r.text and 'refresh_token' not in r.text and 'encrypted_token' not in r.text
