import json
import time
from datetime import date
from pathlib import Path

import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from core.models import Agendamento, ExecucaoImportacao, Paciente

FIXTURES = Path(__file__).parent / 'fixtures'
URL = '/api/integracao/soulmv/importar/'

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def lock_isolado(settings, tmp_path):
    settings.SOULMV_LOCK_FILE = str(tmp_path / 'job.lock')
    settings.SOULMV_INBOX_DIR = None
    return Path(settings.SOULMV_LOCK_FILE)


def _cliente(usuario=None) -> APIClient:
    cliente = APIClient()
    if usuario is not None:
        cliente.credentials(HTTP_AUTHORIZATION=f'Bearer {AccessToken.for_user(usuario)}')
    return cliente


def _csv(nome='soulmv_basico.csv'):
    return SimpleUploadedFile(nome, (FIXTURES / nome).read_bytes(), content_type='text/csv')


@pytest.fixture
def admin():
    return User.objects.create_user('admin', password='x', is_staff=True)


def test_url():
    assert reverse('soulmv_importar') == URL


def test_sem_token_401():
    resposta = _cliente().post(URL, {'arquivo': _csv()}, format='multipart')
    assert resposta.status_code == 401
    assert not ExecucaoImportacao.objects.exists()


def test_sessao_sem_jwt_nao_autentica(admin):
    cliente = APIClient()
    cliente.force_login(admin)
    assert cliente.post(URL, {'arquivo': _csv()}, format='multipart').status_code == 401


def test_nao_admin_403():
    usuario = User.objects.create_user('comum', password='x')
    resposta = _cliente(usuario).post(URL, {'arquivo': _csv()}, format='multipart')
    assert resposta.status_code == 403
    assert not ExecucaoImportacao.objects.exists()


def test_admin_importa_200(admin):
    resposta = _cliente(admin).post(URL, {'arquivo': _csv()}, format='multipart')

    assert resposta.status_code == 200
    assert resposta.json() == {
        'execucao': ExecucaoImportacao.objects.get().pk,
        'status': 'sucesso',
        'linhas_lidas': 11,
        'pacientes_criados': 4,
        'agendamentos_criados': 9,
        'linhas_rejeitadas': 2,
        'erro': '',
    }
    assert ExecucaoImportacao.objects.get().arquivo == 'api:soulmv_basico.csv'

    repetida = _cliente(admin).post(URL, {'arquivo': _csv()}, format='multipart')
    assert repetida.status_code == 200
    assert repetida.json()['status'] == 'ignorado'


def test_cabecalho_invalido_422(admin):
    resposta = _cliente(admin).post(URL, {'arquivo': _csv('soulmv_cabecalho_invalido.csv')}, format='multipart')
    assert resposta.status_code == 422
    assert resposta.json()['status'] == 'erro'
    assert not Paciente.objects.exists()


def test_sem_arquivo_400(admin):
    assert _cliente(admin).post(URL, {}, format='multipart').status_code == 400


def test_arquivo_grande_413(admin, settings):
    settings.SOULMV_UPLOAD_MAX_BYTES = 100
    resposta = _cliente(admin).post(URL, {'arquivo': _csv()}, format='multipart')
    assert resposta.status_code == 413
    assert not ExecucaoImportacao.objects.exists()


def test_limite_padrao_10mb(settings):
    assert settings.SOULMV_UPLOAD_MAX_BYTES == 10 * 1024 * 1024


def test_lock_ocupado_409(admin, lock_isolado):
    lock_isolado.write_text(json.dumps({'pid': 1, 'timestamp': time.time(), 'token': 'job'}))
    resposta = _cliente(admin).post(URL, {'arquivo': _csv()}, format='multipart')
    assert resposta.status_code == 409
    assert not Paciente.objects.exists()


# --- DELETE de paciente com agendamento (PROTECT) ----------------------------------------------

def test_delete_paciente_com_agendamento_409(admin):
    paciente = Paciente.objects.create(nome='P', data_nascimento=date(1950, 1, 1))
    Agendamento.objects.create(paciente=paciente, solicitacao='1', item_agendamento='CONSULTA')
    cliente = APIClient()
    cliente.force_authenticate(admin)

    resposta = cliente.delete(f'/api/pacientes/{paciente.pk}/')

    assert resposta.status_code == 409
    assert 'agendamentos' in resposta.json()['error']
    assert Paciente.objects.filter(pk=paciente.pk).exists()


def test_delete_paciente_sem_agendamento_204(admin):
    paciente = Paciente.objects.create(nome='P', data_nascimento=date(1950, 1, 1))
    cliente = APIClient()
    cliente.force_authenticate(admin)

    assert cliente.delete(f'/api/pacientes/{paciente.pk}/').status_code == 204


# --- admin --------------------------------------------------------------------------------------

def test_admin_execucao_somente_leitura(client):
    superuser = User.objects.create_superuser('root', password='x')
    ExecucaoImportacao.objects.create(arquivo='a.csv', status='sucesso')
    client.force_login(superuser)

    assert client.get('/admin/core/execucaoimportacao/').status_code == 200
    assert client.get('/admin/core/execucaoimportacao/add/').status_code == 403
    assert client.get('/admin/core/agendamento/').status_code == 200
