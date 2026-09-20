"""Database selection. Change backend/.env AJO_DATABASE_MODE, then restart API/worker.

postgres uses DATABASE_URL; sqlite uses AJO_SQLITE_DATABASE_URL.
AJO_PLATFORM_DATABASE_URL remains an explicit process override for tests/tools.
Provider mode is independently selected by AJO_PROVIDER_MODE.
"""
from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from .config import setting, ConfigurationError


def selected_database_url():
    override = setting('AJO_PLATFORM_DATABASE_URL', required=False)
    mode = setting('AJO_DATABASE_MODE', required=False)
    if override:
        value = override
    elif mode == 'sqlite':
        value = setting('AJO_SQLITE_DATABASE_URL')
    elif mode in {None, 'postgres'}:
        value = setting('DATABASE_URL')
    else:
        raise ConfigurationError('AJO_DATABASE_MODE must be postgres or sqlite.')
    try:
        url = make_url(value)
    except Exception:
        raise ConfigurationError('Database URL must be a valid SQLAlchemy URL.') from None
    if url.drivername in {'postgres', 'postgresql'}:
        url = url.set(drivername='postgresql+psycopg')
    if url.get_backend_name() not in {'sqlite', 'postgresql'}:
        raise ConfigurationError('Configure a PostgreSQL or SQLite database URL.')
    if not override and mode and url.get_backend_name() != {'postgres':'postgresql','sqlite':'sqlite'}[mode]:
        raise ConfigurationError('Selected database mode does not match its configured URL.')
    return url


def make_engine(url=None):
    url = url or selected_database_url()
    is_sqlite = str(url).startswith("sqlite")
    engine = create_engine(url, connect_args={"check_same_thread": False} if is_sqlite else {})
    if is_sqlite:
        @event.listens_for(engine, "connect")
        def configure(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=10000")
    return engine
