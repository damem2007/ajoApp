import base64
from sqlalchemy.orm import Session
from app.platform.models import Notice, Circle
from tests.test_full_platform import client, request, new_circle


def test_public_pages_and_validation_redaction(client):
    for path in ['/', '/marketplace', '/app', '/app/circles/new', '/backoffice/cms']:
        response=client.get(path,follow_redirects=False)
        assert response.status_code==307
        assert response.headers['location']=='http://frontend.test'+path
    assert 'Your people.' in client.get('/api/v1/content/home').text
    for path in ['/assets/workspace/core.js','/assets/home.html','/assets/home.js','/sw.js']:
        assert client.get(path).status_code==404
    secret='Sensitive!'
    response=client.post('/api/v1/auth/register',json={'email':'test@example.test','phone':'1','password':secret})
    assert response.status_code==422
    assert secret not in response.text and '"input"' not in response.text
    errors={e['field']:e['message'] for e in response.json()['errors']}
    assert 'country code' in errors['phone'] and '12 characters' in errors['password']


def test_mfa_setup_is_stable_and_contains_local_qr(client):
    first=request(client,'POST','/auth/mfa/setup',{}).json()
    second=request(client,'POST','/auth/mfa/setup',{}).json()
    assert first['secret']==second['secret']
    assert first['qr_data_url'].startswith('data:image/svg+xml;base64,')
    assert b'<svg' in base64.b64decode(first['qr_data_url'].split(',',1)[1])


def test_notification_deletion_requires_read_and_ownership(client):
    with Session(client.app.state.ctx.engine) as db,db.begin():
        notice=Notice(user_id='u0',channel='in-app',title='Test notice',body='A fixture notice',key='fixture-delete')
        db.add(notice);db.flush();nid=notice.id
    assert request(client,'DELETE',f'/notifications/{nid}',user='u1').status_code==404
    assert request(client,'DELETE',f'/notifications/{nid}').status_code==409
    assert request(client,'POST',f'/notifications/{nid}/read',{}).status_code==200
    assert request(client,'DELETE',f'/notifications/{nid}').status_code==200
    assert all(n['id']!=nid for n in request(client,'GET','/notifications').json())


def test_public_marketplace_excludes_private_and_premium(client):
    cid=new_circle(client,name='Visible public circle',category='Travel')
    listings=client.get('/api/v1/public/marketplace').json()
    assert [item['name'] for item in listings]==['Visible public circle']
    assert 'members' in listings[0] and 'slots' in listings[0]
    assert listings[0]['category']=='Travel' and listings[0]['id']==cid
    assert 'creator_id' not in listings[0] and 'seed' not in listings[0]
    assert client.get('/api/v1/public/marketplace?q=unmatched').json()==[]
    for config in [{'privacy':'private'},{'privacy':'public','premium':True}]:
        with Session(client.app.state.ctx.engine) as db,db.begin():
            circle=db.get(Circle,cid);circle.config={**circle.config,**config}
        assert client.get('/api/v1/public/marketplace').json()==[]


def test_fixed_member_count_even_for_older_overflow_config(client):
    cid=new_circle(client,minimum_members=2,planned_members=2,hard_cap=4)
    with Session(client.app.state.ctx.engine) as db,db.begin():
        circle=db.get(Circle,cid);circle.config={**circle.config,'allow_overflow':True,'overflow_strategy':'extend_rotation'}
    assert request(client,'POST',f'/circles/{cid}/join',{},'u1').status_code==200
    assert request(client,'POST',f'/circles/{cid}/join',{},'u2').status_code==409
    assert client.get('/api/v1/public/marketplace').json()==[]


def test_next_frontend_redirect_keeps_backend_api_independent(client, monkeypatch):
    monkeypatch.setenv('AJO_FRONTEND_ORIGIN', 'http://127.0.0.1:3000')
    response=client.get('/app?view=backoffice&module=cms',follow_redirects=False)
    assert response.status_code==307
    assert response.headers['location']=='http://127.0.0.1:3000/app?view=backoffice&module=cms'
    for path in ['/', '/marketplace', '/terms', '/privacy']:
        assert client.get(path,follow_redirects=False).headers['location']=='http://127.0.0.1:3000'+path
    assert client.get('/health').status_code==200
    assert client.get('/api/v1/public/marketplace').status_code==200
    assert request(client,'GET','/me').status_code==200
