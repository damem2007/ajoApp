from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from tests.legacy_reference.api import create_app
from app.domain import allocate


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(f"sqlite:///{tmp_path}/test.db", demo_mode=True)) as c:
        yield c


def post(c, path, body=None, user="demo-1"):
    return c.post('/api/schemes'+path, json=body or {}, headers={"X-Demo-User": user})


def scheme(c):
    r = post(c, '', {"name": "Test circle", "target_minor": 10001, "planned_members": 3})
    assert r.status_code == 201
    return r.json()['id']


def activate(c):
    sid = scheme(c)
    for u in ['demo-2', 'demo-3']:
        assert post(c, f'/{sid}/join', user=u).status_code == 200
    r = post(c, f'/{sid}/finalize', {"payout_order": ['demo-3', 'demo-1', 'demo-2']})
    assert r.status_code == 200
    digest = r.json()['contract_hash']
    for u in ['demo-1', 'demo-2', 'demo-3']:
        r = post(c, f'/{sid}/sign', {"contract_hash": digest}, user=u)
    assert r.json()['state'] == 'Active'
    return sid


def test_rounding_conserves_pool_and_equal_lifetime_obligations():
    for n in range(2, 51):
        for target in [n, 10001, 100_000_000]:
            rows = [allocate(target, n, p) for p in range(n)]
            assert all(sum(row) == target for row in rows)
            assert all(sum(row[i] for row in rows) == target for i in range(n))


def test_rotation_and_idempotency(client):
    sid = activate(client)
    for p in range(3):
        first = post(client, f'/{sid}/simulate-period', {'period': p})
        assert first.status_code == 200
        assert post(client, f'/{sid}/simulate-period', {'period': p}).json() == first.json()
        assert first.json()['pool_minor'] == 0
    result = first.json()
    assert result['state'] == 'Completed'
    for member in result['members']:
        assert member['contributed_minor'] == member['collected_minor'] == 10001
        assert member['remaining_obligation_minor'] == member['net_position_minor'] == 0


def test_auth_kyc_caps_and_early_finalization(client):
    assert client.get('/api/schemes').status_code == 401
    assert post(client, '', {'name':'Test', 'target_minor':100, 'planned_members':2}, user='demo-4').status_code == 403
    sid = scheme(client)
    assert post(client, '', {'name':'Test', 'target_minor':100, 'planned_members':2}).status_code == 409
    assert post(client, f'/{sid}/finalize', {'payout_order':['demo-1']}).status_code == 409
    assert post(client, f'/{sid}/simulate-period', {'period':0}).status_code == 409
    assert client.get(f'/api/schemes/{sid}/audit', headers={'X-Demo-User':'demo-2'}).status_code == 403


def test_unsupported_policy_rejected(client):
    base = {'name':'Test', 'target_minor':100, 'planned_members':2}
    for extra in [{'allow_overflow':True}, {'contribution_frequency':'weekly'}, {'target_minor':1.5}, {'target_minor':True}, {'target_minor':1}]:
        assert post(client, '', {**base, **extra}).status_code == 422


def test_locking_signatures_and_order(client):
    sid = scheme(client)
    for u in ['demo-2','demo-3']:
        post(client, f'/{sid}/join', user=u)
    assert post(client, f'/{sid}/finalize', {'payout_order':['demo-1']*3}).status_code == 422
    r = post(client, f'/{sid}/finalize', {'payout_order':['demo-1','demo-2','demo-3']})
    assert post(client, f'/{sid}/sign', {'contract_hash':'stale'}).status_code == 409
    r = post(client, f'/{sid}/sign', {'contract_hash':r.json()['contract_hash']})
    assert r.json()['state'] == 'PendingSignatures'
    assert post(client, f'/{sid}/simulate-period', {'period':0}).status_code == 409
    assert post(client, f'/{sid}/finalize', {'payout_order':['demo-3','demo-2','demo-1']}).status_code == 409


def test_concurrent_replay(client):
    sid = activate(client)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _:post(client, f'/{sid}/simulate-period', {'period':0}), range(4)))
    assert all(r.status_code == 200 and r.json()['period'] == 1 for r in results)


def test_default_app_fails_closed(tmp_path):
    with TestClient(create_app(f'sqlite:///{tmp_path}/disabled.db', demo_mode=False)) as c:
        assert c.get('/health').json()['real_payments_enabled'] is False
        assert c.get('/api/demo/users').status_code == 503
