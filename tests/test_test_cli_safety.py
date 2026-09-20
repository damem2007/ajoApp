import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.platform.models import Base, Account
from tests.cli.common import require_non_production


def test_test_cli_refuses_production(monkeypatch):
    monkeypatch.setenv('APP_ENV','production')
    with pytest.raises(RuntimeError): require_non_production()


def test_superadmin_is_not_test_account_by_default():
    user=Account(email='admin@example.test',phone='+15555550123',password='hash',role='admin')
    assert user.is_test_account is None or user.is_test_account is False
    assert user.test_run_id is None
