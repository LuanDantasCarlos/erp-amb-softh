"""Ponto de entrada do Phusion Passenger (cPanel → Setup Python App → Application startup file)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ambulatorio.settings')

from ambulatorio.wsgi import application  # noqa: E402,F401
