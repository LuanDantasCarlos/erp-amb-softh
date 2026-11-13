import importlib.util
from pathlib import Path

import dotenv
import pytest
from django.core.exceptions import ImproperlyConfigured
from django.db import connection
from django.db.backends.sqlite3.base import DatabaseWrapper

SETTINGS = Path(__file__).resolve().parents[2] / 'ambulatorio' / 'settings.py'
VARIAVEIS = (
    'DEBUG', 'SECRET_KEY', 'ALLOWED_HOSTS', 'CSRF_TRUSTED_ORIGINS', 'SQLITE_PATH', 'SQLITE_JOURNAL_MODE',
    'LOG_DIR', 'SECURE_SSL_REDIRECT', 'SECURE_HSTS_SECONDS',
)


@pytest.fixture
def carregar(monkeypatch, tmp_path):
    """Importa settings.py isolado, com ambiente controlado e sem ler o .env local."""
    monkeypatch.setattr(dotenv, 'load_dotenv', lambda *a, **k: False)
    for nome in VARIAVEIS:
        monkeypatch.delenv(nome, raising=False)
    monkeypatch.setenv('LOG_DIR', str(tmp_path / 'logs'))

    def _carregar(**env):
        for nome, valor in env.items():
            monkeypatch.setenv(nome, valor)
        spec = importlib.util.spec_from_file_location('settings_sonda', SETTINGS)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        return modulo

    return _carregar


def test_debug_padrao_false_exige_secret_key(carregar):
    with pytest.raises(ImproperlyConfigured, match='SECRET_KEY'):
        carregar()


def test_producao(carregar, tmp_path):
    s = carregar(
        SECRET_KEY='x' * 50,
        ALLOWED_HOSTS='exemplo.com.br, www.exemplo.com.br',
        CSRF_TRUSTED_ORIGINS='https://exemplo.com.br',
        SQLITE_PATH=str(tmp_path / 'prod.sqlite3'),
    )
    assert s.DEBUG is False
    assert s.ALLOWED_HOSTS == ['exemplo.com.br', 'www.exemplo.com.br']
    assert s.CSRF_TRUSTED_ORIGINS == ['https://exemplo.com.br']
    assert s.DATABASES['default']['NAME'] == str(tmp_path / 'prod.sqlite3')
    assert 'debug_toolbar' not in s.INSTALLED_APPS
    assert not any('debug_toolbar' in m for m in s.MIDDLEWARE)
    assert s.MIDDLEWARE[1] == 'whitenoise.middleware.WhiteNoiseMiddleware'
    assert s.STORAGES['staticfiles']['BACKEND'] == 'whitenoise.storage.CompressedManifestStaticFilesStorage'
    assert s.SECURE_PROXY_SSL_HEADER == ('HTTP_X_FORWARDED_PROTO', 'https')
    assert s.SESSION_COOKIE_SECURE and s.CSRF_COOKIE_SECURE
    assert s.LOGGING['handlers']['arquivo']['filename'] == str(tmp_path / 'logs' / 'app.log')
    assert (tmp_path / 'logs').is_dir()


def test_producao_sem_hosts_nao_usa_curinga_nem_replit(carregar):
    s = carregar(SECRET_KEY='x')
    assert s.ALLOWED_HOSTS == []
    assert s.CSRF_TRUSTED_ORIGINS == []


def test_desenvolvimento(carregar):
    s = carregar(DEBUG='True')
    assert s.DEBUG is True
    assert s.SECRET_KEY.startswith('django-insecure')
    assert s.ALLOWED_HOSTS == ['localhost', '127.0.0.1']
    assert s.DEBUG_TOOLBAR == (importlib.util.find_spec('debug_toolbar') is not None)
    assert ('debug_toolbar' in s.INSTALLED_APPS) == s.DEBUG_TOOLBAR
    assert not hasattr(s, 'LOGGING')


def test_journal_mode(carregar):
    assert carregar(SECRET_KEY='x').SQLITE_JOURNAL_MODE == 'WAL'
    assert carregar(SECRET_KEY='x', SQLITE_JOURNAL_MODE='delete').SQLITE_JOURNAL_MODE == 'DELETE'
    with pytest.raises(ImproperlyConfigured, match='SQLITE_JOURNAL_MODE'):
        carregar(SECRET_KEY='x', SQLITE_JOURNAL_MODE='WAL; DROP TABLE x')


@pytest.mark.django_db
@pytest.mark.parametrize('modo', ['WAL', 'DELETE'])
def test_sqlite_journal_mode_aplicado(settings, tmp_path, modo):
    settings.SQLITE_JOURNAL_MODE = modo
    assert connection.settings_dict['OPTIONS']['timeout'] == 30
    wrapper = DatabaseWrapper({**connection.settings_dict, 'NAME': str(tmp_path / 'j.sqlite3')}, alias='jm_teste')
    try:
        with wrapper.cursor() as cursor:
            cursor.execute('PRAGMA journal_mode')
            assert cursor.fetchone()[0] == modo.lower()
    finally:
        wrapper.close()


def test_passenger_wsgi():
    import passenger_wsgi

    assert callable(passenger_wsgi.application)
