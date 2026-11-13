import io
from datetime import date, datetime
from pathlib import Path

import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import CommandError, call_command
from django.forms.models import model_to_dict
from django.utils import timezone
from PyPDF2 import PdfReader
from reportlab.pdfgen import canvas

from core.integracao.soulmv.importador import importar_arquivo, importar_conteudo
from core.models import (
    Agendamento,
    CampoTemplateDocumento,
    Documento,
    ExecucaoImportacao,
    Paciente,
    TemplateDocumento,
)
from core.utils import gerar_documento_pdf

FIXTURES = Path(__file__).parent / 'fixtures'
BASICO = FIXTURES / 'soulmv_basico.csv'
SEGUNDA = FIXTURES / 'soulmv_segunda_carga.csv'

pytestmark = pytest.mark.django_db


@pytest.fixture
def paciente_manual():
    return Paciente.objects.create(
        nome='BELTRANO MANUAL',
        data_nascimento=date(1970, 10, 10),
        cpf='987.654.321-00',
        sexo='M',
        celular='(27) 90000-0000',
    )


def _snapshot(paciente: Paciente) -> dict:
    paciente.refresh_from_db()
    return {**model_to_dict(paciente), 'updated_at': paciente.updated_at}


def test_importacao_basica():
    execucao = importar_arquivo(BASICO)

    assert execucao.status == ExecucaoImportacao.STATUS_SUCESSO
    assert execucao.linhas_lidas == 11
    assert execucao.linhas_rejeitadas == 2
    assert execucao.pacientes_criados == 4
    assert execucao.agendamentos_criados == 9
    assert execucao.finalizado_em is not None
    assert len(execucao.sha256) == 64
    assert {d['solicitacao'] for d in execucao.detalhes_rejeicao} == {'8000008', '8000009'}
    assert Paciente.objects.count() == 4
    assert Agendamento.objects.count() == 9
    assert not Paciente.objects.filter(nome__in=['DATA INVALIDA', 'SEM CHAVE']).exists()


def test_paciente_repetido_gera_um_paciente_e_n_agendamentos():
    importar_arquivo(BASICO)

    fulano = Paciente.objects.get(codigo_cidadao='1000001')
    assert fulano.agendamentos.count() == 5
    assert fulano.origem == Paciente.ORIGEM_SOULMV
    assert fulano.sexo is None and fulano.celular is None


def test_cpf_com_zero_a_esquerda_e_cpf_vazio():
    importar_arquivo(BASICO)

    assert Paciente.objects.get(codigo_cidadao='1000001').cpf == '000.123.456-78'
    sem_cpf = Paciente.objects.get(codigo_cidadao='1000002')
    assert sem_cpf.cpf is None
    assert Paciente.objects.filter(cpf__isnull=True).count() == 1
    assert not Paciente.objects.filter(cpf='').exists()


def test_data_agenda_em_horario_local():
    importar_arquivo(BASICO)

    ag = Agendamento.objects.get(solicitacao='8000001')
    assert timezone.localtime(ag.data_agenda).replace(tzinfo=None) == datetime(2026, 11, 13, 8, 1)
    assert Agendamento.objects.get(solicitacao='8000010').data_agenda is None


def test_paciente_manual_casado_por_cpf_so_recebe_codigo(paciente_manual):
    antes = _snapshot(paciente_manual)

    execucao = importar_arquivo(BASICO)

    assert execucao.pacientes_criados == 3
    depois = _snapshot(paciente_manual)
    assert depois.pop('codigo_cidadao') == '1000003'
    antes.pop('codigo_cidadao')
    assert depois == antes
    assert paciente_manual.agendamentos.get().solicitacao == '8000007'


def test_paciente_manual_com_codigo_diferente_nao_e_alterado(paciente_manual):
    Paciente.objects.filter(pk=paciente_manual.pk).update(codigo_cidadao='5550000')
    antes = _snapshot(paciente_manual)

    importar_arquivo(BASICO)

    assert _snapshot(paciente_manual) == antes
    assert paciente_manual.agendamentos.get().solicitacao == '8000007'


def test_paciente_existente_nao_e_alterado_e_recebe_agendamento_novo():
    importar_arquivo(BASICO)
    fulano = Paciente.objects.get(codigo_cidadao='1000001')
    antes = _snapshot(fulano)
    agendamento_antigo = Agendamento.objects.get(solicitacao='8000001')

    execucao = importar_arquivo(SEGUNDA)

    assert execucao.status == ExecucaoImportacao.STATUS_SUCESSO
    assert execucao.pacientes_criados == 1
    assert execucao.agendamentos_criados == 2
    assert _snapshot(fulano) == antes
    novo = Agendamento.objects.get(solicitacao='8000020')
    assert novo.paciente_id == fulano.pk
    assert novo.item_agendamento == 'EXAME DE RETORNO'
    agendamento_antigo_depois = Agendamento.objects.get(solicitacao='8000001')
    assert agendamento_antigo_depois.updated_at == agendamento_antigo.updated_at
    assert fulano.agendamentos.count() == 6


def test_reimportacao_do_mesmo_arquivo_e_ignorada():
    importar_arquivo(BASICO)

    execucao = importar_arquivo(BASICO)

    assert execucao.status == ExecucaoImportacao.STATUS_IGNORADO
    assert execucao.pacientes_criados == 0 and execucao.agendamentos_criados == 0
    assert Paciente.objects.count() == 4
    assert Agendamento.objects.count() == 9


def test_reimportacao_forcada_nao_duplica():
    importar_arquivo(BASICO)

    execucao = importar_arquivo(BASICO, forcar=True)

    assert execucao.status == ExecucaoImportacao.STATUS_SUCESSO
    assert execucao.pacientes_criados == 0 and execucao.agendamentos_criados == 0
    assert Paciente.objects.count() == 4
    assert Agendamento.objects.count() == 9


def test_idempotencia_compara_com_ultima_execucao_com_sucesso():
    importar_arquivo(BASICO)
    importar_arquivo(SEGUNDA)

    execucao = importar_arquivo(BASICO)

    assert execucao.status == ExecucaoImportacao.STATUS_SUCESSO
    assert execucao.pacientes_criados == 0 and execucao.agendamentos_criados == 0


def test_cabecalho_invalido_nao_grava_nada(paciente_manual):
    execucao = importar_arquivo(FIXTURES / 'soulmv_cabecalho_invalido.csv')

    assert execucao.status == ExecucaoImportacao.STATUS_ERRO
    assert 'Cabeçalho' in execucao.erro
    assert list(Paciente.objects.all()) == [paciente_manual]
    assert not Agendamento.objects.exists()
    paciente_manual.refresh_from_db()
    assert paciente_manual.codigo_cidadao is None


def test_csv_sem_linhas_e_erro():
    execucao = importar_arquivo(FIXTURES / 'soulmv_somente_cabecalho.csv')

    assert execucao.status == ExecucaoImportacao.STATUS_ERRO
    assert execucao.linhas_lidas == 0


def test_cp1252():
    execucao = importar_arquivo(FIXTURES / 'soulmv_cp1252.csv')

    assert execucao.status == ExecucaoImportacao.STATUS_SUCESSO
    assert Paciente.objects.get(codigo_cidadao='1000010').nome == 'JOSÉ DA CONCEIÇÃO'


def test_falha_na_persistencia_faz_rollback(monkeypatch):
    def explode(*args, **kwargs):
        raise RuntimeError('falha simulada')

    monkeypatch.setattr(Agendamento.objects, 'bulk_create', explode)

    execucao = importar_arquivo(BASICO)

    assert execucao.status == ExecucaoImportacao.STATUS_ERRO
    assert execucao.erro.startswith('RuntimeError:')
    assert 'falha simulada' not in execucao.erro
    assert not Paciente.objects.exists()


def test_nada_e_deletado(paciente_manual):
    usuario = User.objects.create_user('medico', password='x')
    fora_do_csv = Paciente.objects.create(nome='FORA DO CSV', data_nascimento=date(1990, 1, 1), cpf='111.444.777-35')
    doc = Documento.objects.create(paciente=paciente_manual, nome='Receita', emitido_por=usuario)

    importar_arquivo(BASICO)
    importar_arquivo(SEGUNDA)

    assert Paciente.objects.filter(pk__in=[paciente_manual.pk, fora_do_csv.pk], ativo=True).count() == 2
    assert Documento.objects.filter(pk=doc.pk).exists()


def test_command(capsys):
    call_command('importar_pacientes_soulmv', arquivo=str(BASICO))
    assert 'sucesso' in capsys.readouterr().out

    with pytest.raises(CommandError):
        call_command('importar_pacientes_soulmv', arquivo=str(FIXTURES / 'soulmv_cabecalho_invalido.csv'))
    with pytest.raises(CommandError):
        call_command('importar_pacientes_soulmv', arquivo=str(FIXTURES / 'nao_existe.csv'))


def test_importar_conteudo_registra_nome_do_arquivo():
    execucao = importar_conteudo(BASICO.read_bytes(), 'upload.csv')
    assert execucao.arquivo == 'upload.csv'


def _pdf_em_branco() -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(595, 842))
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def test_documento_de_paciente_importado_preenche_nome_cpf_nascimento(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    importar_arquivo(BASICO)
    paciente = Paciente.objects.get(codigo_cidadao='1000001')
    usuario = User.objects.create_user('medico', password='x')
    template = TemplateDocumento.objects.create(
        nome='Teste',
        criado_por=usuario,
        arquivo_template=SimpleUploadedFile('t.pdf', _pdf_em_branco(), content_type='application/pdf'),
    )
    for ordem, atributo in enumerate(['nome', 'cpf', 'data_nascimento', 'sexo', 'celular']):
        CampoTemplateDocumento.objects.create(
            template=template,
            nome_campo=atributo,
            atributo_paciente=atributo,
            posicao={'x': 50, 'y': 100 + ordem * 30},
        )

    buffer = gerar_documento_pdf(paciente, template, {})

    assert buffer is not None
    texto = PdfReader(buffer).pages[0].extract_text()
    assert 'FULANO DE TAL' in texto
    assert '000.123.456-78' in texto
    assert '01/02/1950' in texto  # spec templates-oftalmologia §3.4: datas em dd/mm/aaaa
    assert 'None' not in texto
