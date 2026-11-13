"""Ponto de entrada do Phusion Passenger (cPanel → Application Manager).

O Passenger do servidor compartilhado inicia com o Python do sistema (3.9). Se existir o
virtualenv do projeto (.venv) ou PASSENGER_VENV_PYTHON, o processo é reexecutado com ele
antes de importar o Django (que exige Python >= 3.10).
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INTERP = os.environ.get('PASSENGER_VENV_PYTHON') or os.path.join(BASE_DIR, '.venv', 'bin', 'python')

if os.path.isfile(INTERP) and os.path.realpath(sys.executable) != os.path.realpath(INTERP):
    os.execl(INTERP, INTERP, *sys.argv)

sys.path.insert(0, BASE_DIR)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ambulatorio.settings')

from ambulatorio.wsgi import application  # noqa: E402,F401
