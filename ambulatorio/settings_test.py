"""Settings para pytest: produção (DEBUG=False) com chave fixa, sem HTTPS forçado e sem manifest de static."""
import os
import tempfile

os.environ.setdefault('SECRET_KEY', 'insecure-somente-testes')
os.environ.setdefault('LOG_DIR', os.path.join(tempfile.gettempdir(), 'erp-amb-testes-logs'))
os.environ['SECURE_SSL_REDIRECT'] = 'false'

from .settings import *  # noqa: E402,F401,F403
from .settings import STORAGES  # noqa: E402

STORAGES = {**STORAGES, 'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}}
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
