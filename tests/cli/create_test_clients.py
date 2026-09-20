from __future__ import annotations

import argparse
import os
from datetime import date, timedelta

from .common import client, new_run_id, save_manifest, request_json, test_headers, login


PNG=b'\x89PNG\r\n\x1a\n'+b'ajo-test-fixture'


def create_clients(*,count,test_run_id=None,password='Ajo-Test-Password-42'):
    run_id=test_run_id or new_run_id()
    records=[]
    with client() as http:
        admin_email=os.getenv('SUPERADMIN_EMAIL')
        admin_password=os.getenv('SUPERADMIN_PASSWORD')
        if not admin_email or not admin_password:
            raise RuntimeError('SUPERADMIN_EMAIL and SUPERADMIN_PASSWORD are required for sandbox KYC approval')
        admin=login(http,admin_email,admin_password)
        for index in range(count):
            email=f'ajo-test-{run_id[:8]}-{index}@example.test'
            phone=f'+1555{int(run_id.replace("-","")[:6],16)%1000000:06d}{index%10}'
            registered=request_json(http,'POST','/api/v1/auth/register',
                json_body={'email':email,'phone':phone,'password':password},headers=test_headers(run_id))
            token=registered['access_token']
            inbox=request_json(http,'GET','/api/v1/auth/sandbox-inbox',token=token)
            latest={}
            for item in inbox: latest[item['channel']]=item['code']
            for channel in ('email','sms'):
                request_json(http,'POST','/api/v1/auth/verify',token=token,
                    json_body={'channel':channel,'code':latest[channel]})
            identity=request_json(http,'POST','/api/v1/documents?kind=identity',token=token,
                files={'file':('identity.png',PNG,'image/png')})
            selfie=request_json(http,'POST','/api/v1/documents?kind=selfie',token=token,
                files={'file':('selfie.png',PNG,'image/png')})
            kyc=request_json(http,'POST','/api/v1/kyc',token=token,json_body={
                'document_id':identity['id'],'selfie_id':selfie['id'],'id_type':'passport',
                'id_number':f'TEST-{run_id[:8]}-{index}','country':'CA','province':'BC',
                'expiry':(date.today()+timedelta(days=3650)).isoformat(),
                'legal_name':f'Ajo Test Client {index}','dob':'1990-01-01',
                'device_fingerprint':f'test-cli-{run_id}-{index}',
            })
            request_json(http,'POST',f"/api/v1/admin/kyc/{kyc['id']}/review",token=admin['access_token'],
                json_body={'decision':'Approved','reason':'Explicit local test-data CLI fixture','duplicate_reviewed':True})
            request_json(http,'POST','/api/v1/banks',token=token,
                json_body={'provider_token':f'sandbox-ok-{run_id[:8]}-{index}','mandate_accepted':True})
            records.append({'email':email,'phone':phone,'password':password,'access_token':token})
    manifest={'test_run_id':run_id,'clients':records,'circles':[]}
    save_manifest(manifest)
    return manifest


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--count',type=int,default=3)
    parser.add_argument('--run-id')
    parser.add_argument('--password',default='Ajo-Test-Password-42')
    args=parser.parse_args()
    if args.count<1 or args.count>100: parser.error('--count must be between 1 and 100')
    data=create_clients(count=args.count,test_run_id=args.run_id,password=args.password)
    print('test_run_id:',data['test_run_id'])
    for item in data['clients']: print(item['email'],item['password'])


if __name__=='__main__': main()
