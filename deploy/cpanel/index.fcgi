#!/home1/softhcom/apps/erp-amb-softh/.venv/bin/python
"""Entrada FastCGI (Apache mod_fcgid) para hospedagem compartilhada cPanel sem Passenger.

Copiado para o document root do subdomínio pelo deploy (permissão 755). O shebang aponta
para o virtualenv do projeto; APP_DIR pode ser sobrescrito por variável de ambiente.
"""
import os
import sys

APP_DIR = os.environ.get('APP_DIR', '/home1/softhcom/apps/erp-amb-softh')
sys.path.insert(0, APP_DIR)
os.chdir(APP_DIR)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ambulatorio.settings')

from django.core.wsgi import get_wsgi_application  # noqa: E402
from flup.server.fcgi import WSGIServer  # noqa: E402

_django = get_wsgi_application()


def application(environ, start_response):
    # O .htaccess reescreve /caminho -> /index.fcgi/caminho; sem isto o Django geraria
    # URLs com o prefixo /index.fcgi.
    environ['SCRIPT_NAME'] = ''
    return _django(environ, start_response)


if __name__ == '__main__':
    WSGIServer(application).run()
