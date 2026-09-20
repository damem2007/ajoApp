import pytest
from app.platform.calendar import schedule
from app.platform.schemas import CircleInput,PolicyInput


def test_contribution_first_mixed_calendar_has_one_debit_amount():
    config=CircleInput(name='Fixed weekly plan',start_date='2026-09-16',contribution_minor=20000,
                       contribution_frequency='weekly',collection_frequency='monthly').model_dump(mode='json')
    assert config['target_minor']==260000
    result=schedule(config,['a','b','c'],PolicyInput(fee_mode='none').model_dump())
    debits=[r for r in result if r['kind']=='contribution']
    assert {r['amount_minor'] for r in debits}=={20000}
    assert [sum(r['window']==w and r['user_id']=='a' for r in debits) for w in range(3)]==[5,4,4]
    for user in ['a','b','c']:
        assert sum(r['amount_minor'] for r in debits if r['user_id']==user)==260000
    assert sum(r['amount_minor'] for r in debits)==sum(r['amount_minor'] for r in result if r['kind']=='payout')


def test_matching_frequencies_derive_payout_from_contribution_and_members():
    config=CircleInput(name='Three member plan',start_date='2028-01-31',contribution_minor=3333).model_dump(mode='json')
    assert config['target_minor']==9999
    assert {r['amount_minor'] for r in schedule(config,['a','b','c'],PolicyInput(fee_mode='none').model_dump()) if r['kind']=='contribution'}=={3333}
    with pytest.raises(ValueError):CircleInput(name='Incorrect target',start_date='2028-01-31',contribution_minor=3333,target_minor=10000)


def test_contribution_first_rejects_unfunded_payout_dates():
    config=CircleInput(name='Underfunded first payout',start_date='2027-02-01',contribution_minor=20000,
                       contribution_frequency='weekly',collection_frequency='monthly').model_dump(mode='json')
    with pytest.raises(ValueError,match='earlier than sufficient'):schedule(config,['a','b','c'],PolicyInput(fee_mode='none').model_dump())

from tests.test_full_platform import client,request,activate


def test_fixed_plan_preview_and_signed_rotation(client):
    payload=dict(name='Contribution first plan',start_date='2028-01-31',contribution_minor=20000,
                 contribution_frequency='weekly',collection_frequency='monthly')
    preview=request(client,'POST','/circles/preview',payload)
    assert preview.status_code==200,preview.text
    assert preview.json()['target_minor']==260000
    assert len(preview.json()['debit_dates'])==13
    bad={**payload,'start_date':'2027-02-01'}
    assert request(client,'POST','/circles/preview',bad).status_code==422
    assert request(client,'POST','/circles',bad).status_code==422
    cid,contract=activate(client,**payload,target_minor=None)
    frozen=request(client,'GET','/contracts/'+contract['contract_id']).json()
    contributions=[r for r in frozen['content']['schedule'] if r['kind']=='contribution']
    assert {row['amount_minor'] for row in contributions}=={20000}
    result=request(client,'POST','/admin/jobs/run',{'as_of':'2028-05-01'},'u3')
    assert result.status_code==200,result.text
    assert request(client,'GET','/circles/'+cid).json()['state']=='Completed'
    for user in ['u0','u1','u2']:
        obligation=request(client,'GET','/circles/'+cid,user=user).json()['obligation']
        assert obligation['contributed_minor']==obligation['collected_minor']==260000
        assert obligation['remaining_obligation_minor']==0
