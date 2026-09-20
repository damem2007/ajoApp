from __future__ import annotations

import argparse
from datetime import date, timedelta

from .common import client, load_manifest, save_manifest, request_json, test_headers, login


def create_circles(*,run_id,count,members_per_circle,activate=True):
    data=load_manifest(run_id)
    if members_per_circle<2 or members_per_circle>len(data['clients']):
        raise ValueError('members_per_circle must be between 2 and the number of generated clients')
    with client() as http:
        logged=[login(http,c['email'],c['password']) for c in data['clients']]
        for index in range(count):
            members=logged[:members_per_circle]
            creator=members[0]['access_token']
            circle=request_json(http,'POST','/api/v1/circles',token=creator,headers=test_headers(run_id),json_body={
                'name':f'Ajo Test Circle {index+1}',
                'contribution_minor':5000,
                'minimum_members':members_per_circle,
                'planned_members':members_per_circle,
                'hard_cap':members_per_circle,
                'start_date':(date.today()+timedelta(days=7)).isoformat(),
                'currency':'CAD',
                'contribution_frequency':'monthly',
                'collection_frequency':'monthly',
            })
            cid=circle['id']
            request_json(http,'POST',f'/api/v1/circles/{cid}/publish',token=creator,json_body={})
            for member in members[1:]:
                request_json(http,'POST',f'/api/v1/circles/{cid}/join',token=member['access_token'],json_body={})
            contract_id=None
            if activate:
                request_json(http,'POST',f'/api/v1/circles/{cid}/close-recruitment',token=creator,json_body={})
                ids=[member['user']['id'] for member in members]
                contract=request_json(http,'POST',f'/api/v1/circles/{cid}/finalize',token=creator,
                    json_body={'payout_order':ids})
                contract_id=contract['contract_id']
                for member in members:
                    request_json(http,'POST',f"/api/v1/contracts/{contract_id}/sign",token=member['access_token'],
                        json_body={'contract_hash':contract['hash'],'typed_name':'Ajo Test Client','accepted':True})
            data['circles'].append({'id':cid,'contract_id':contract_id})
    save_manifest(data)
    return data


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--run-id',required=True)
    parser.add_argument('--circles',type=int,default=1)
    parser.add_argument('--members-per-circle',type=int,default=3)
    parser.add_argument('--no-activate',action='store_true')
    args=parser.parse_args()
    data=create_circles(run_id=args.run_id,count=args.circles,members_per_circle=args.members_per_circle,activate=not args.no_activate)
    print('test_run_id:',data['test_run_id'])
    for item in data['circles']: print(item['id'],item.get('contract_id') or 'recruiting')


if __name__=='__main__': main()
