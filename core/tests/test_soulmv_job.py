import json
import os
import shutil
import time
from datetime import date, timedelta
from pathlib import Path

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.core.management import CommandError, call_command
from django.utils import timezone

from core.integracao.soulmv.extrator import ExtracaoError, ExtratorArquivoLocal, obter_extrator
from core.integracao.soulmv.job import NOME_LOCK, executar_job, limpar_inbox
from core.integracao.soulmv.lock import LockOcupado, lock_arquivo
from core.models import Agendamento, ExecucaoImportacao, Paciente

FIXTURES = Path(__file__).parent / 'fixtures'
OITO_DIAS = 8 * 86400


def _envelhecer(caminho: Path, segundos: float) -> None:
    instante = time.time() - segundos
    os.utime(caminho, (instante, instante))


def _lock_com_idade(caminho: Path, segundos: float) -> None:
    caminho.write_text(json.dumps({'pid': 999999, 'timestamp': time.time() - segundos, 'token': 'outro'}))


@pytest.fixture
def inbox(tmp_path):
    pasta = tmp_path / 'inbox'
    pasta.mkdir()
    return pasta


# --- lock ---------------------------------------------------------------------------------------

def test_lock_adquire_e_libera(tmp_path):
    caminho = tmp_path / 'job.lock'
    with lock_arquivo(caminho, 60):
        dados = json.loads(caminho.read_text())
        assert dados['pid'] == os.getpid()
        with pytest.raises(LockOcupado):
            with lock_arquivo(caminho, 60):
                pass
    assert not caminho.exists()


def test_lock_ocupado(tmp_path):
    caminho = tmp_path / 'job.lock'
    _lock_com_idade(caminho, 10 * 60)

    with pytest.raises(LockOcupado):
        with lock_arquivo(caminho, 50 * 60):
            pass
    assert json.loads(caminho.read_text())['token'] == 'outro'


def test_lock_velho_e_removido(tmp_path):
    caminho = tmp_path / 'job.lock'
    _lock_com_idade(caminho, 51 * 60)

    with lock_arquivo(caminho, 50 * 60):
        assert json.loads(caminho.read_text())['pid'] == os.getpid()
    assert not caminho.exists()


def test_lock_ilegivel_usa_mtime(tmp_path):
    caminho = tmp_path / 'job.lock'
    caminho.write_text('lixo')
    with pytest.raises(LockOcupado):
        with lock_arquivo(caminho, 50 * 60):
            pass

    _envelhecer(caminho, 51 * 60)
    with lock_arquivo(caminho, 50 * 60):
        pass
    assert not caminho.exists()


def test_lock_nao_remove_lock_de_outro_processo(tmp_path):
    caminho = tmp_path / 'job.lock'
    with lock_arquivo(caminho, 60):
        _lock_com_idade(caminho, 0)  # outro processo assumiu o lock (ex.: considerou o nosso velho)
    assert caminho.exists()


# --- extrator e inbox ---------------------------------------------------------------------------

def test_extrator_arquivo_local_pega_o_mais_recente(inbox):
    antigo = inbox / 'a.csv'
    novo = inbox / 'b.csv'
    antigo.write_text('x')
    novo.write_text('y')
    (inbox / 'c.txt').write_text('z')
    _envelhecer(antigo, 3600)

    assert ExtratorArquivoLocal().extrair(date(2026, 11, 13), date(2026, 11, 30), inbox) == novo
    assert ExtratorArquivoLocal(origem=inbox).extrair(date(2026, 11, 13), date(2026, 11, 30), Path('x')) == novo


def test_extrator_sem_csv(inbox):
    with pytest.raises(ExtracaoError):
        ExtratorArquivoLocal().extrair(date(2026, 11, 13), date(2026, 11, 30), inbox)


def test_obter_extrator():
    assert isinstance(obter_extrator('arquivo_local'), ExtratorArquivoLocal)
    with pytest.raises(ImproperlyConfigured):
        obter_extrator('nao_existe')


def test_limpar_inbox_remove_so_csv_antigo(inbox):
    velho = inbox / 'velho.csv'
    velho_maiusculo = inbox / 'VELHO2.CSV'
    recente = inbox / 'recente.csv'
    lock = inbox / NOME_LOCK
    for arquivo in (velho, velho_maiusculo, recente, lock):
        arquivo.write_text('x')
    for arquivo in (velho, velho_maiusculo, lock):
        _envelhecer(arquivo, OITO_DIAS)

    assert limpar_inbox(inbox, 7) == 2
    assert sorted(p.name for p in inbox.iterdir()) == sorted([NOME_LOCK, 'recente.csv'])
    assert limpar_inbox(inbox / 'nao_existe', 7) == 0


# --- job ----------------------------------------------------------------------------------------

@pytest.mark.django_db
def test_job_ponta_a_ponta(inbox):
    shutil.copy(FIXTURES / 'soulmv_basico.csv', inbox / '20261113080000.csv')

    resultado = executar_job(inbox_dir=inbox, extrator=ExtratorArquivoLocal())

    assert resultado.executou
    assert resultado.execucao.status == ExecucaoImportacao.STATUS_SUCESSO
    assert Paciente.objects.count() == 4
    assert Agendamento.objects.count() == 9
    assert not (inbox / NOME_LOCK).exists()

    segunda = executar_job(inbox_dir=inbox, extrator=ExtratorArquivoLocal())
    assert segunda.execucao.status == ExecucaoImportacao.STATUS_IGNORADO


@pytest.mark.django_db
def test_job_limpa_inbox_antes_de_extrair(inbox):
    velho = inbox / '20261101080000.csv'
    shutil.copy(FIXTURES / 'soulmv_segunda_carga.csv', velho)
    _envelhecer(velho, OITO_DIAS)
    shutil.copy(FIXTURES / 'soulmv_basico.csv', inbox / '20261113080000.csv')

    resultado = executar_job(inbox_dir=inbox, extrator=ExtratorArquivoLocal())

    assert resultado.arquivos_removidos == 1
    assert not velho.exists()
    assert resultado.execucao.arquivo.endswith('20261113080000.csv')


@pytest.mark.django_db
def test_job_com_lock_ocupado_nao_executa(inbox):
    shutil.copy(FIXTURES / 'soulmv_basico.csv', inbox / 'a.csv')
    _lock_com_idade(inbox / NOME_LOCK, 60)

    resultado = executar_job(inbox_dir=inbox, extrator=ExtratorArquivoLocal())

    assert not resultado.executou
    assert not ExecucaoImportacao.objects.exists()
    assert not Paciente.objects.exists()


@pytest.mark.django_db
def test_job_com_lock_velho_executa_e_marca_execucao_presa(inbox):
    shutil.copy(FIXTURES / 'soulmv_basico.csv', inbox / 'a.csv')
    _lock_com_idade(inbox / NOME_LOCK, 51 * 60)
    presa = ExecucaoImportacao.objects.create(arquivo='x', iniciado_em=timezone.now() - timedelta(minutes=55))
    recente = ExecucaoImportacao.objects.create(arquivo='y', iniciado_em=timezone.now() - timedelta(minutes=5))

    resultado = executar_job(inbox_dir=inbox, extrator=ExtratorArquivoLocal())

    assert resultado.execucao.status == ExecucaoImportacao.STATUS_SUCESSO
    presa.refresh_from_db()
    recente.refresh_from_db()
    assert presa.status == ExecucaoImportacao.STATUS_ERRO
    assert 'excedeu 50 min' in presa.erro
    assert recente.status == ExecucaoImportacao.STATUS_EXECUTANDO


@pytest.mark.django_db
def test_job_falha_de_extracao_e_registrada(inbox):
    resultado = executar_job(inbox_dir=inbox, extrator=ExtratorArquivoLocal())

    assert resultado.execucao.status == ExecucaoImportacao.STATUS_ERRO
    assert 'Nenhum CSV' in resultado.execucao.erro


@pytest.mark.django_db
def test_job_excecao_inesperada_do_extrator(inbox):
    class ExtratorQuebrado:
        def extrair(self, inicio, fim, destino):
            raise ConnectionError('segredo-na-url')

    resultado = executar_job(inbox_dir=inbox, extrator=ExtratorQuebrado())

    assert resultado.execucao.status == ExecucaoImportacao.STATUS_ERRO
    assert 'ConnectionError' in resultado.execucao.erro
    assert 'segredo' not in resultado.execucao.erro


@pytest.mark.django_db
def test_job_passa_periodo_hoje_ate_fim_do_mes(inbox):
    chamadas = []

    class ExtratorEspiao:
        def extrair(self, inicio, fim, destino):
            chamadas.append((inicio, fim, destino))
            alvo = destino / 'x.csv'
            shutil.copy(FIXTURES / 'soulmv_basico.csv', alvo)
            return alvo

    executar_job(inbox_dir=inbox, extrator=ExtratorEspiao(), hoje=date(2028, 2, 10))

    assert chamadas == [(date(2028, 2, 10), date(2028, 2, 29), inbox)]


# --- command ------------------------------------------------------------------------------------

@pytest.mark.django_db
def test_command_job(settings, inbox, capsys):
    settings.SOULMV_INBOX_DIR = str(inbox)
    settings.SOULMV_LOCK_FILE = None
    shutil.copy(FIXTURES / 'soulmv_basico.csv', inbox / 'a.csv')

    call_command('job_pacientes_soulmv')
    assert '[sucesso]' in capsys.readouterr().out

    _lock_com_idade(inbox / NOME_LOCK, 60)
    call_command('job_pacientes_soulmv')
    assert 'já em execução' in capsys.readouterr().out


@pytest.mark.django_db
def test_command_job_erro_sai_com_codigo_diferente_de_zero(settings, inbox):
    settings.SOULMV_INBOX_DIR = str(inbox)
    settings.SOULMV_LOCK_FILE = None
    with pytest.raises(CommandError, match='erro'):
        call_command('job_pacientes_soulmv')


def test_command_job_sem_inbox_configurado(settings):
    settings.SOULMV_INBOX_DIR = None
    with pytest.raises(CommandError, match='SOULMV_INBOX_DIR'):
        call_command('job_pacientes_soulmv')
