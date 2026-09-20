"""Validated deployment settings shared by API, CLI workers and migrations.

Local files are loaded once, independently of the working directory. Exported
variables override file values. Credentials are never included in errors.
"""
import os
from pathlib import Path
from urllib.parse import urlsplit
from dotenv import load_dotenv
from sqlalchemy.engine import make_url

ENV_FILE = Path(__file__).resolve().parents[1] / '.env'
load_dotenv(ENV_FILE, override=False)


class ConfigurationError(ValueError):
    """An environment setting is missing or invalid."""


def setting(name, *aliases, required=True):
    for key in (name, *aliases):
        value = os.getenv(key, '').strip()
        if value:
            return value
    if required:
        raise ConfigurationError('Set ' + ' or '.join((name, *aliases)) + ' in .env or the process environment.')
    return None


def database_url():
    from .database import selected_database_url
    return selected_database_url()


def http_origin(value, name):
    try:
        url = urlsplit(value)
        valid = (url.scheme in {'http', 'https'} and url.hostname and url.port != 0
                 and not url.username and not url.password and not url.query
                 and not url.fragment and url.path in {'', '/'})
    except ValueError:
        valid = False
    if not valid:
        raise ConfigurationError(name + ' must be an HTTP(S) origin without credentials, path, query or fragment.')
    return value.rstrip('/')


def frontend_origin():
    return http_origin(setting('AJO_FRONTEND_ORIGIN', 'FRONTEND_URL'), 'FRONTEND_URL')


def cors_origins():
    configured = setting('CORS_ALLOWED_ORIGINS', required=False)
    origins = [http_origin(value.strip(), 'CORS_ALLOWED_ORIGINS') for value in configured.split(',') if value.strip()] if configured else []
    return list(dict.fromkeys([frontend_origin(), *origins]))


def simulated_providers():
    mode = setting('AJO_PROVIDER_MODE', required=False)
    if mode is not None:
        if mode not in {'simulated', 'unconfigured'}:
            raise ConfigurationError('AJO_PROVIDER_MODE must be simulated or unconfigured; live adapters are not yet configured.')
        return mode == 'simulated'
    # Compatibility for existing deployments; provider mode does not select a DB.
    legacy = setting('AJO_DEMO_MODE', required=False)
    if legacy is None:
        return False
    if legacy.lower() not in {'true', 'false'}:
        raise ConfigurationError('AJO_DEMO_MODE must be true or false.')
    return legacy.lower() == 'true'


def environment_path(name, required=True):
    value = setting(name, required=required)
    if value is None:
        return None
    path = Path(value).expanduser()
    return path if path.is_absolute() else (ENV_FILE.parent / path).resolve()


def positive_integer(name, *aliases):
    value = setting(name, *aliases)
    if not value.isdigit() or int(value) < 1:
        raise ConfigurationError(name + ' must be a positive integer.')
    return int(value)


def api_binding():
    host = setting('AJO_API_HOST')
    port = positive_integer('AJO_API_PORT')
    if port > 65535:
        raise ConfigurationError('AJO_API_PORT must be a valid TCP port.')
    return host, port


def worker_interval_seconds():
    return positive_integer('AJO_WORKER_INTERVAL_SECONDS')


def provider_name(kind):
    explicit = setting('AJO_' + kind.upper() + '_PROVIDER', required=False)
    if explicit:
        return explicit
    return 'sandbox' if simulated_providers() else 'unconfigured'


def resilience_enabled():
    value = setting('AJO_DATABASE_RESILIENCE', required=False) or 'false'
    if value not in {'true', 'false'}:
        raise ConfigurationError('AJO_DATABASE_RESILIENCE must be true or false.')
    return value == 'true'


def redis_url():
    return setting('AJO_REDIS_URL', 'REDIS_URL')


def scheduler_interval_seconds():
    value = setting('AJO_SCHEDULER_INTERVAL_SECONDS', required=False) or '30'
    if not value.isdigit() or int(value) < 1:
        raise ConfigurationError('AJO_SCHEDULER_INTERVAL_SECONDS must be a positive integer.')
    return int(value)
