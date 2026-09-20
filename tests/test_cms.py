import copy
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.platform.models import Account, Audit
from tests.test_full_platform import client, request


def test_cms_access_draft_publication_and_rollback(client):
    initial=client.get('/api/v1/content/home').json()
    assert client.get('/api/v1/admin/content/home').status_code==401
    assert request(client,'GET','/admin/content/home').status_code==403
    state=request(client,'GET','/admin/content/home',user='u3').json()
    content=copy.deepcopy(state['draft']['content']);content['hero']['lines'][0]='Our community.'
    save={'content':content,'expected_draft':state['draft']['id'],'reason':'Update hero copy'}
    draft=request(client,'PUT','/admin/content/home/draft',save,'u3')
    assert draft.status_code==200,draft.text
    did=draft.json()['draft']['id']
    assert client.get('/api/v1/content/home').json()==initial
    assert 'Our community.' not in client.get('/api/v1/content/home').text
    assert 'Our community.' in request(client,'GET','/admin/content/home/preview',user='u3').text
    assert request(client,'PUT','/admin/content/home/draft',save,'u3').status_code==409
    publish={'revision_id':did,'expected_published':initial['revision_id'],'reason':'Approve updated hero'}
    with Session(client.app.state.ctx.engine) as db,db.begin():
        from app.platform.rbac import assign
        assign(db,db.get(Account,'u2'),'ops',db.get(Account,'u3'))
    assert request(client,'GET','/admin/content/home',user='u2').status_code==200
    assert request(client,'POST','/admin/content/home/publish',publish,'u2').status_code==403
    assert request(client,'POST','/admin/content/home/publish',publish,'u3').status_code==200
    assert 'Our community.' in client.get('/api/v1/content/home').text
    assert request(client,'POST','/admin/content/home/publish',publish,'u3').status_code==409
    history=request(client,'GET','/admin/content/home/revisions',user='u3').json()
    assert len(history)==2
    restore={'revision_id':initial['revision_id'],'expected_published':did,'reason':'Restore original copy'}
    response=request(client,'POST','/admin/content/home/restore',restore,'u3')
    assert response.status_code==200,response.text
    assert response.json()['published']['id']!=initial['revision_id']
    assert client.get('/api/v1/content/home').json()['content']==initial['content']
    with Session(client.app.state.ctx.engine) as db:
        actions=set(db.scalars(select(Audit.action)))
        assert {'content_draft_saved','content_published','content_restored'}<=actions


def test_cms_preview_returns_authorized_json_and_structure_is_validated(client):
    state=request(client,'GET','/admin/content/home',user='u3').json()
    content=copy.deepcopy(state['draft']['content']);content['hero']['body']='<script>alert("test")</script>'
    response=request(client,'PUT','/admin/content/home/draft',{'content':content,'expected_draft':state['draft']['id'],'reason':'Check safe text rendering'},'u3')
    assert response.status_code==200,response.text
    preview=request(client,'GET','/admin/content/home/preview',user='u3')
    assert preview.headers['content-type'].startswith('application/json')
    assert preview.json()['content']['hero']['body']==content['hero']['body']
    assert request(client,'GET','/admin/content/home/preview-data',user='u3').json()==preview.json()
    assert request(client,'GET','/admin/content/home/preview').status_code==403
    invalid=copy.deepcopy(content);invalid['hero']['lines']=[]
    assert request(client,'PUT','/admin/content/home/draft',{'content':invalid,'expected_draft':response.json()['draft']['id'],'reason':'Invalid structure'},'u3').status_code==422
    for path in ['/', '/marketplace','/terms','/privacy']:
        response=client.get(path,follow_redirects=False);assert response.status_code==307,response.text
