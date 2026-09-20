from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine,inspect,select,func
from app.platform.models import StaffRole,NotificationChannel


def test_empty_sqlite_migration_seeds_roles_channels_without_legacy_tables(tmp_path):
    engine=create_engine('sqlite:///'+str(tmp_path/'migration.db'))
    config=Config('alembic.ini')
    with engine.begin() as connection:
        config.attributes['connection']=connection
        command.upgrade(config,'head')
        assert connection.scalar(select(func.count()).select_from(StaffRole))==4
        assert connection.scalar(select(func.count()).select_from(NotificationChannel))==4
        assert not {'users','schemes','memberships','ledger_entries','audit_events'} & set(inspect(connection).get_table_names())
    engine.dispose()
