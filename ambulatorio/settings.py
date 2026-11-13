"""
Django settings for ambulatorio project.

Toda configuração sensível ou dependente de ambiente vem de variáveis de ambiente
(opcionalmente carregadas de um arquivo .env na raiz). Ver .env.example.
"""

import importlib.util
import os
from datetime import timedelta
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None
if load_dotenv is not None:
    load_dotenv(BASE_DIR / '.env')


def env_bool(nome: str, padrao: bool = False) -> bool:
    valor = os.environ.get(nome)
    if valor is None or valor.strip() == '':
        return padrao
    return valor.strip().lower() in ('1', 'true', 'yes', 'on', 'sim')


def env_list(nome: str, padrao: str = '') -> list:
    return [item.strip() for item in os.environ.get(nome, padrao).split(',') if item.strip()]


def env_int(nome: str, padrao: int) -> int:
    valor = os.environ.get(nome, '').strip()
    return int(valor) if valor else padrao


DEBUG = env_bool('DEBUG', False)

SECRET_KEY = os.environ.get('SECRET_KEY', '').strip()
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured('SECRET_KEY é obrigatório quando DEBUG=False.')
    SECRET_KEY = 'django-insecure-somente-desenvolvimento'

ALLOWED_HOSTS = env_list('ALLOWED_HOSTS', 'localhost,127.0.0.1' if DEBUG else '')
CSRF_TRUSTED_ORIGINS = env_list('CSRF_TRUSTED_ORIGINS')

DEBUG_TOOLBAR = DEBUG and importlib.util.find_spec('debug_toolbar') is not None

# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Third-party apps
    'rest_framework',
    'rest_framework_simplejwt',
    'django_filters',
    'drf_yasg',
    # Local apps
    'core',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

if DEBUG_TOOLBAR:
    INSTALLED_APPS.append('debug_toolbar')
    MIDDLEWARE.append('debug_toolbar.middleware.DebugToolbarMiddleware')
    INTERNAL_IPS = ['127.0.0.1']

ROOT_URLCONF = 'ambulatorio.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'ambulatorio.wsgi.application'

# Database: SQLite (o MySQL do servidor é 5.7, incompatível com Django 5.2).
SQLITE_JOURNAL_MODE = os.environ.get('SQLITE_JOURNAL_MODE', 'WAL').strip().upper()
if SQLITE_JOURNAL_MODE not in ('WAL', 'DELETE', 'TRUNCATE', 'PERSIST'):
    raise ImproperlyConfigured('SQLITE_JOURNAL_MODE deve ser WAL, DELETE, TRUNCATE ou PERSIST.')

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.environ.get('SQLITE_PATH') or BASE_DIR / 'db.sqlite3',
        # Espera até 30 s por lock de escrita (job horário + uso web concorrente).
        # journal_mode é aplicado em core.db.configurar_sqlite (sinal connection_created).
        'OPTIONS': {'timeout': 30},
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'pt-br'
TIME_ZONE = 'America/Sao_Paulo'
USE_I18N = True
USE_TZ = True

# Static (whitenoise) e media (servido pelo Django só com DEBUG; em produção, pelo Apache)
STATIC_URL = 'static/'
STATIC_ROOT = os.environ.get('STATIC_ROOT') or os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static')]

MEDIA_URL = '/media/'
MEDIA_ROOT = os.environ.get('MEDIA_ROOT') or os.path.join(BASE_DIR, 'media')

STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'},
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(days=1),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': False,
    'BLACKLIST_AFTER_ROTATION': True,
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
}

DOCUMENT_STORAGE_PATH = os.path.join(MEDIA_ROOT, 'documentos')

# Integração Soul MV (docs/specs/job-importacao-soulmv.md)
SOULMV_EXTRATOR = os.environ.get('SOULMV_EXTRATOR', 'arquivo_local')
# Pasta de entrada dos CSVs: deve ficar fora de public_html/MEDIA_ROOT/static (LGPD).
SOULMV_INBOX_DIR = os.environ.get('SOULMV_INBOX_DIR') or None
SOULMV_LOCK_FILE = os.environ.get('SOULMV_LOCK_FILE') or None  # padrão: <INBOX_DIR>/.job_pacientes_soulmv.lock
SOULMV_RETENCAO_DIAS = env_int('SOULMV_RETENCAO_DIAS', 7)
SOULMV_LIMITE_EXECUCAO_MIN = 50
SOULMV_UPLOAD_MAX_BYTES = 10 * 1024 * 1024
# Cliente HTTP (SOULMV_EXTRATOR=http). Credenciais só por env, nunca no código.
SOULMV_USUARIO = os.environ.get('SOULMV_USUARIO', '').strip()
SOULMV_SENHA = os.environ.get('SOULMV_SENHA', '')
SOULMV_API_URL = os.environ.get('SOULMV_API_URL', '').strip() or 'https://regulacao.saude.es.gov.br/consultas-exames/api/'
SOULMV_PERFIL = os.environ.get('SOULMV_PERFIL', '').strip() or 'COORDENADOR DE UNIDADE CMCE'
SOULMV_UNIDADE_SOLICITANTE = (
    os.environ.get('SOULMV_UNIDADE_SOLICITANTE', '').strip() or 'NUCLEO ESPECIAL DE REGULACAO DE CONSULTAS E EXAMES'
)
SOULMV_UNIDADE_EXECUTANTE = os.environ.get('SOULMV_UNIDADE_EXECUTANTE', '').strip() or 'RCS SOLUCOES MEDICAS S/A'

# Produção
if not DEBUG:
    # O Apache/Passenger do cPanel termina o TLS e repassa X-Forwarded-Proto.
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = env_bool('SECURE_SSL_REDIRECT', True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    # HSTS só depois de confirmar HTTPS estável no domínio (ex.: 3600, depois 31536000).
    SECURE_HSTS_SECONDS = env_int('SECURE_HSTS_SECONDS', 0)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool('SECURE_HSTS_INCLUDE_SUBDOMAINS', False)

    LOG_DIR = Path(os.environ.get('LOG_DIR') or BASE_DIR / 'logs')
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    LOGGING = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'padrao': {'format': '%(asctime)s %(levelname)s %(name)s [%(process)d] %(message)s'},
        },
        'handlers': {
            'arquivo': {
                'class': 'logging.handlers.RotatingFileHandler',
                'filename': str(LOG_DIR / 'app.log'),
                'maxBytes': 5 * 1024 * 1024,
                'backupCount': 5,
                'encoding': 'utf-8',
                'formatter': 'padrao',
            },
            'console': {'class': 'logging.StreamHandler', 'formatter': 'padrao'},
        },
        'root': {'handlers': ['arquivo', 'console'], 'level': 'WARNING'},
        'loggers': {
            'core': {'handlers': ['arquivo', 'console'], 'level': 'INFO', 'propagate': False},
            # Bots com Host inválido geram traceback a cada request; a resposta 400 basta.
            'django.security.DisallowedHost': {'handlers': [], 'level': 'CRITICAL', 'propagate': False},
        },
    }
