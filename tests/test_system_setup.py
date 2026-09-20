from datetime import date
import pytest
from tests.test_full_platform import client, request


def test_database_switch_is_independent_of_provider_mode(monkeypatch):
    from app.config import database_url, simulated_providers
    monkeypatch.delenv('AJO_PLATFORM_DATABASE_URL', raising=False)
    monkeypatch.setenv('AJO_DATABASE_MODE', 'sqlite')
    monkeypatch.setenv('AJO_SQLITE_DATABASE_URL', 'sqlite:///:memory:')
    monkeypatch.setenv('AJO_PROVIDER_MODE', 'unconfigured')
    assert database_url().get_backend_name() == 'sqlite'
    assert simulated_providers() is False
    monkeypatch.setenv('AJO_DATABASE_MODE', 'postgres')
    monkeypatch.setenv('DATABASE_URL', 'postgresql://fixture:password@example.test/ajo')
    monkeypatch.setenv('AJO_PROVIDER_MODE', 'simulated')
    assert database_url().get_backend_name() == 'postgresql'
    assert simulated_providers() is True


def test_backoffice_setup_controls_preview_create_and_edit(client):
    c = client
    current = request(c, 'GET', '/admin/policies', user='u3').json()[-1]['data']
    current['circle_setup'] = {**current['circle_setup'], 'members_max':4, 'name_min_length':5,
        'contribution_frequencies':['monthly'], 'collection_frequencies':['monthly'], 'amount_max_minor':100000}
    saved = request(c, 'POST', '/admin/policies', {'policy':current, 'reason':'Configure cycle limits'}, user='u3')
    assert saved.status_code == 201
    assert c.get('/api/v1/public/circle-setup').json()['members_max'] == 4
    body = dict(name='Valid circle', contribution_minor=1000, minimum_members=3, planned_members=3, hard_cap=3, start_date=date.today().isoformat())
    created = request(c, 'POST', '/circles', body)
    assert created.status_code == 201
    for invalid in [{**body,'name':'Tiny'}, {**body,'hard_cap':5,'planned_members':5}, {**body,'contribution_frequency':'weekly'}, {**body,'contribution_minor':50000}]:
        assert request(c,'POST','/circles/preview', invalid).status_code == 422
        assert request(c,'POST','/circles', invalid).status_code == 422
        assert request(c,'PUT','/circles/'+created.json()['id'], invalid).status_code == 422
    assert request(c,'POST','/admin/policies', {'policy':current,'reason':'Unauthorized setting change'}).status_code == 403


def test_setup_rejects_overflow_and_disabled_defaults():
    from app.platform.schemas import CircleSetup
    with pytest.raises(ValueError): CircleSetup(allow_overflow=True)
    with pytest.raises(ValueError): CircleSetup(contribution_frequencies=['weekly'])


def test_participant_config_is_admin_only_versioned_and_controls_cap(client):
    from sqlalchemy.orm import Session
    from app.platform.models import Account, Policy
    from app.platform.services import cap
    c = client
    assert request(c,'GET','/admin/participant-config').status_code == 403
    initial = request(c,'GET','/admin/participant-config',user='u3').json()
    tiers = [{'score':0,'cap':2},{'score':10,'cap':4}]
    assert request(c,'POST','/admin/participant-config',{'tiers':tiers,'reason':'Configure participant caps'}).status_code == 403
    response = request(c,'POST','/admin/participant-config',{'tiers':tiers,'reason':'Configure participant caps'},user='u3')
    assert response.status_code == 201
    with Session(c.app.state.ctx.engine) as db:
        previous = db.get(Policy, initial['policy_version'])
        current = db.get(Policy, response.json()['policy_version'])
        assert {k:v for k,v in current.data.items() if k!='tiers'} == {k:v for k,v in previous.data.items() if k!='tiers'}
        assert cap(db, db.get(Account,'u0')) == 2
    for invalid in [[{'score':5,'cap':2}],[{'score':0,'cap':0}],[{'score':0,'cap':2},{'score':0,'cap':3}]]:
        assert request(c,'POST','/admin/participant-config',{'tiers':invalid,'reason':'Invalid tier example'},user='u3').status_code == 422
