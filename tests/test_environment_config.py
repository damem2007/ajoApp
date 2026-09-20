from app.config import database_url, frontend_origin


def test_database_configuration_precedence_and_postgres_driver(monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'postgresql://fixture:password@localhost/ajo')
    monkeypatch.delenv('AJO_PLATFORM_DATABASE_URL', raising=False)
    assert database_url().drivername == 'postgresql+psycopg'
    assert database_url().database == 'ajo'
    monkeypatch.setenv('AJO_PLATFORM_DATABASE_URL', 'sqlite:///:memory:')
    assert database_url().drivername == 'sqlite'


def test_frontend_url_alias_and_override(monkeypatch):
    monkeypatch.delenv('AJO_FRONTEND_ORIGIN', raising=False)
    monkeypatch.setenv('FRONTEND_URL', 'http://localhost:9520/')
    assert frontend_origin() == 'http://localhost:9520'
    monkeypatch.setenv('AJO_FRONTEND_ORIGIN', 'http://localhost:3000')
    assert frontend_origin() == 'http://localhost:3000'


def test_database_is_required_and_errors_do_not_expose_credentials(monkeypatch):
    import pytest
    from app.config import ConfigurationError
    monkeypatch.delenv('DATABASE_URL', raising=False)
    monkeypatch.delenv('AJO_PLATFORM_DATABASE_URL', raising=False)
    with pytest.raises(ConfigurationError, match='DATABASE_URL'):
        database_url()
    monkeypatch.setenv('DATABASE_URL', 'not-a-url:private-password')
    with pytest.raises(ConfigurationError) as error:
        database_url()
    assert 'private-password' not in str(error.value)


def test_frontend_origin_is_required_and_validated(monkeypatch):
    import pytest
    from app.config import ConfigurationError
    monkeypatch.delenv('AJO_FRONTEND_ORIGIN', raising=False)
    monkeypatch.delenv('FRONTEND_URL', raising=False)
    with pytest.raises(ConfigurationError, match='FRONTEND_URL'):
        frontend_origin()
    for value in ['file:///private', 'https://private:password@example.test', 'https://example.test/other', 'https://example.test/?target=other']:
        monkeypatch.setenv('FRONTEND_URL', value)
        with pytest.raises(ConfigurationError):
            frontend_origin()


def test_runtime_bindings_and_sandbox_paths_are_environment_driven(monkeypatch, tmp_path):
    import pytest
    from app.config import api_binding, environment_path, ConfigurationError, simulated_providers, worker_interval_seconds
    monkeypatch.setenv('AJO_API_HOST', '127.0.0.1')
    monkeypatch.setenv('AJO_API_PORT', '19020')
    assert api_binding() == ('127.0.0.1', 19020)
    monkeypatch.setenv('AJO_API_PORT', '99999')
    with pytest.raises(ConfigurationError):
        api_binding()
    monkeypatch.setenv('AJO_DATA_DIR', str(tmp_path))
    assert environment_path('AJO_DATA_DIR') == tmp_path
    monkeypatch.delenv('AJO_PROVIDER_MODE', raising=False)
    monkeypatch.setenv('AJO_DEMO_MODE', 'false')
    assert simulated_providers() is False
    monkeypatch.setenv('AJO_DEMO_MODE', 'yes')
    with pytest.raises(ConfigurationError):
        simulated_providers()
    monkeypatch.setenv('AJO_WORKER_INTERVAL_SECONDS', '7')
    assert worker_interval_seconds() == 7
