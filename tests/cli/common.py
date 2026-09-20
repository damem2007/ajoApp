"""Shared safety and HTTP helpers for AJo test-data CLI utilities."""
from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import UUID, uuid4

import httpx

RUN_DIR=Path('.ajo-test-runs')


def require_non_production():
    env=os.getenv('APP_ENV','').lower()
    if env not in {'development','test'}:
        raise RuntimeError('Set APP_ENV=development or APP_ENV=test. Test-data generation is disabled otherwise.')
    return env


def base_url():
    return os.getenv('AJO_TEST_BASE_URL','http://127.0.0.1:9020').rstrip('/')


def client():
    require_non_production()
    return httpx.Client(base_url=base_url(),timeout=30.0)


def auth(token):
    return {'Authorization':'Bearer '+token}


def test_headers(run_id):
    UUID(str(run_id))
    return {'X-Ajo-Test-Run-Id':str(run_id)}


def new_run_id():
    return str(uuid4())


def manifest_path(run_id):
    UUID(str(run_id))
    RUN_DIR.mkdir(exist_ok=True)
    return RUN_DIR/(str(run_id)+'.json')


def load_manifest(run_id):
    return json.loads(manifest_path(run_id).read_text())


def save_manifest(data):
    manifest_path(data['test_run_id']).write_text(json.dumps(data,indent=2,sort_keys=True)+'\n')


def request_json(http,method,path,*,token=None,json_body=None,headers=None,files=None):
    merged=dict(headers or {})
    if token: merged.update(auth(token))
    response=http.request(method,path,json=json_body,headers=merged,files=files)
    response.raise_for_status()
    return response.json() if response.content else {}


def login(http,email,password):
    return request_json(http,'POST','/api/v1/auth/login',json_body={'email':email,'password':password})
