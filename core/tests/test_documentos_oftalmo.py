"""Templates de oftalmologia (docs/specs/templates-oftalmologia.md). Somente dados sintéticos."""
import io
import json
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import CommandError, call_command
from django.urls import reverse
from PyPDF2 import PdfReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas as rl_canvas

from core.documentos import engine
from core.documentos.engine import desenhar_texto, gerar_pdf, resolver_valores
from core.documentos.fontes import ContextoDocumento, resolver_valor
from core.documentos.formulario import data_atendimento_padrao
from core.documentos.instalacao import instalar_templates
from core.documentos.layouts import bpai, prescricao_oculos, receituario_colirios
from core.documentos.sigtap import importar_procedimentos
from core.models import (
    Agendamento, CampoPreenchidoDocumento, CampoTemplateDocumento, Documento, Medico, Paciente, Procedimento,
    TemplateDocumento,
)

pytestmark = pytest.mark.django_db

BRT = ZoneInfo('America/Sao_Paulo')
CALAZIO = '04.05.01.007-9'


@pytest.fixture(autouse=True)
def media(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path / 'media')
    return tmp_path / 'media'


@pytest.fixture
def paciente():
    return Paciente.objects.create(
        nome='PACIENTE SINTETICO', data_nascimento=date(1950, 2, 1), cpf='000.123.456-78', cns='700000000000001',
        codigo_cidadao='1234567', sexo='F', celular='(27) 90000-0000', telefone='(27) 3000-0000', origem='soulmv',
    )


@pytest.fixture
def medico():
    return Medico.objects.create(nome='MEDICO FICTICIO', crm='00000-ES / 11111-MG', cns='7000 0000 0000 002',
                                 rqe='999', cpf='12345678909')


@pytest.fixture
def contexto(paciente, medico):
    return ContextoDocumento(paciente=paciente, medico=medico, data_atendimento=date(2026, 11, 16),
                             hoje=date(2026, 11, 13))


@pytest.fixture
def instalado():
    importar_procedimentos()
    instalar_templates()
    return {t.nome: t for t in TemplateDocumento.objects.all()}


def _ids(template):
    return {c.nome_campo: str(c.id) for c in template.campos.all()}


def _pdf(template, digitados_por_nome, contexto, manter_vazios=()):
    ids = _ids(template)
    valores = resolver_valores(template.campos.all(), {ids[k]: v for k, v in digitados_por_nome.items()},
                               contexto, {ids[n] for n in manter_vazios})
    return PdfReader(gerar_pdf(template, valores))


# --- resolver_valor ------------------------------------------------------------------------------

@pytest.mark.parametrize('chave, esperado', [
    ('nome', 'PACIENTE SINTETICO'),
    ('paciente.nome', 'PACIENTE SINTETICO'),
    ('data_nascimento', '01/02/1950'),
    ('paciente.data_nascimento', '01/02/1950'),
    ('paciente.nascimento_curto', '01/02/50'),
    ('paciente.telefone_contato', '(27) 90000-0000'),
    ('paciente.cns', '700000000000001'),
    ('paciente.sexo', 'F'),
    ('paciente.rg', ''),
    ('paciente.nome_mae', ''),
    ('paciente.inexistente', ''),
    ('paciente._state', ''),
    ('paciente.delete', ''),
    ('medico.nome', 'MEDICO FICTICIO'),
    ('medico.crm', '00000-ES / 11111-MG'),
    ('medico.cns', '700000000000002'),
    ('medico.cbo', '225265'),
    ('medico.rqe', '999'),
    ('medico.especialidade_exibicao', 'Médico(a) Oftalmologista'),
    ('medico.assinatura', 'Dr(a). MEDICO FICTICIO\nCRM: 00000-ES / 11111-MG'),
    ('estabelecimento.nome', 'CRE- METROPOLITANO'),
    ('estabelecimento.cnes', '5604613'),
    ('estabelecimento.nucleo', 'Núcleo Regional de Especialidade de Vitória'),
    ('estabelecimento.unidade', 'Unidade de Oftalmologia'),
    ('estabelecimento.outro', ''),
    ('atendimento.data', '16/11/2026'),
    ('atendimento.mes_ano', '11/2026'),
    ('atendimento.outro', ''),
    ('sistema.hoje', '13/11/2026'),
    ('sistema.outro', ''),
    ('desconhecida.nome', ''),
    ('', ''),
    (None, ''),
])
def test_resolver_valor(contexto, chave, esperado):
    assert resolver_valor(chave, contexto) == esperado


def test_resolver_valor_sem_medico_sem_data_e_telefone_fixo(paciente):
    paciente.celular = None
    contexto = ContextoDocumento(paciente=paciente)
    assert resolver_valor('paciente.telefone_contato', contexto) == '(27) 3000-0000'
    assert resolver_valor('medico.nome', contexto) == ''
    assert resolver_valor('atendimento.data', contexto) == ''
    assert resolver_valor('atendimento.mes_ano', contexto) == ''


def test_resolver_valor_estabelecimento_vem_dos_settings(settings, paciente):
    settings.ESTABELECIMENTO_CNES = '0000000'
    assert resolver_valor('estabelecimento.cnes', ContextoDocumento(paciente=paciente)) == '0000000'


def test_resolver_valor_datetime_aware_em_horario_local(paciente):
    paciente.created_at = datetime(2026, 11, 14, 1, 0, tzinfo=ZoneInfo('UTC'))  # 13/11 22:00 BRT
    assert resolver_valor('paciente.created_at', ContextoDocumento(paciente=paciente)) == '13/11/2026'


def test_medico_normaliza_cns_e_cpf(medico):
    medico.refresh_from_db()
    assert medico.cns == '700000000000002'
    assert medico.cpf == '123.456.789-09'


# --- engine: desenho -----------------------------------------------------------------------------

class CanvasEspiao:
    """Registra o que seria desenhado: (método, x, y, texto, fonte, tamanho)."""

    def __init__(self):
        self.chamadas = []
        self.fonte = ('Helvetica', 12)

    def setFont(self, nome, tamanho):
        self.fonte = (nome, tamanho)

    def _registrar(self, metodo, x, y, texto):
        self.chamadas.append((metodo, round(x, 2), round(y, 2), texto, *self.fonte))

    def drawString(self, x, y, texto):
        self._registrar('left', x, y, texto)

    def drawCentredString(self, x, y, texto):
        self._registrar('center', x, y, texto)

    def drawRightString(self, x, y, texto):
        self._registrar('right', x, y, texto)


def test_auto_ajuste_reduz_fonte_ate_caber():
    can = CanvasEspiao()
    texto = 'PROCEDIMENTO COM NOME BEM LONGO'
    desenhar_texto(can, texto, {'x': 10, 'y': 100, 'width': 150, 'font_size': 12}, 800)
    _, _, _, impresso, fonte, tamanho = can.chamadas[0]
    assert impresso == texto
    assert 7 <= tamanho < 12
    assert stringWidth(texto, fonte, tamanho) <= 150


def test_auto_ajuste_para_em_7pt_e_corta_sem_estourar():
    can = CanvasEspiao()
    desenhar_texto(can, 'X' * 200, {'x': 10, 'y': 100, 'width': 60, 'font_size': 10}, 800)
    _, _, _, impresso, fonte, tamanho = can.chamadas[0]
    assert tamanho == 7
    assert 0 < len(impresso) < 200
    assert stringWidth(impresso, fonte, tamanho) <= 60


def test_sem_width_mantem_comportamento_antigo():
    can = CanvasEspiao()
    desenhar_texto(can, 'X' * 200, {'x': 10, 'y': 100}, 800)
    assert can.chamadas == [('left', 10, 700, 'X' * 200, 'Helvetica', 12)]


def test_texto_multilinha_centralizado():
    can = CanvasEspiao()
    desenhar_texto(can, 'Dr(a). A\nCRM: 1', {'x': 100, 'y': 50, 'width': 200, 'font_size': 10, 'align': 'center'}, 800)
    assert [(c[0], c[1], c[2], c[3]) for c in can.chamadas] == [
        ('center', 200, 750, 'Dr(a). A'), ('center', 200, 738, 'CRM: 1'),
    ]


class CampoFalso:
    def __init__(self, tipo, opcoes=None, posicao=None, pagina=1, nome='campo'):
        self.id = 1
        self.tipo_campo = tipo
        self.opcoes = opcoes
        self.posicao = posicao or {'x': 10, 'y': 10}
        self.pagina = pagina
        self.nome_campo = nome
        self.atributo_paciente = None
        self.validacoes = None


def test_checkbox_marca_todas_as_posicoes_da_opcao():
    pos = [{'x': 10, 'y': 10}, {'x': 400, 'y': 10}]
    campo = CampoFalso('checkbox', [{'id': 'od', 'texto': 'OD', 'posicao': pos}, {'id': 'oe', 'texto': 'OE',
                                                                                   'posicao': [{'x': 50, 'y': 10}]}])
    can = CanvasEspiao()
    engine._desenhar_checkbox(can, campo, ['od'], 800, 1)
    assert [(c[1], c[2], c[3]) for c in can.chamadas] == [(10, 790, 'X'), (400, 790, 'X')]


def test_checkbox_legado_opcao_com_posicao_dict():
    campo = CampoFalso('checkbox', [{'id': 'a', 'texto': 'A', 'posicao': {'x': 30, 'y': 40, 'font_size': 9}}])
    can = CanvasEspiao()
    engine._desenhar_checkbox(can, campo, ['a'], 800, 1)
    assert can.chamadas == [('left', 30, 760, 'X', 'Helvetica', 9)]
    can = CanvasEspiao()
    engine._desenhar_checkbox(can, campo, ['a'], 800, 2)  # outra página: nada
    assert can.chamadas == []


def test_implica_marca_a_opcao_implicada(contexto):
    campo = CampoFalso('checkbox', [{'id': 'usar', 'texto': 'Usar'}, {'id': 'od', 'texto': 'OD', 'implica': ['usar']}])
    assert resolver_valores([campo], {'1': ['od']}, contexto) == {'1': ['od', 'usar']}


@pytest.mark.parametrize('tipo', ['select', 'radio'])
def test_select_e_radio_imprimem_texto_da_opcao(tipo):
    campo = CampoFalso(tipo, [{'id': '01', 'texto': '01 - Eletivo'}, {'id': '02', 'texto': '02 - Urgência'}])
    can = CanvasEspiao()
    engine._desenhar_campo(can, campo, '02', {'x': 10, 'y': 10}, 800, 1, None)
    assert can.chamadas[0][3] == '02 - Urgência'


def test_select_legado_com_opcoes_em_string_imprime_texto():
    campo = CampoFalso('select', ['Sim', 'Não'])
    can = CanvasEspiao()
    engine._desenhar_campo(can, campo, '2', {'x': 10, 'y': 10}, 800, 1, None)
    assert can.chamadas[0][3] == 'Não'
    can = CanvasEspiao()
    engine._desenhar_campo(can, campo, 'Sim', {'x': 10, 'y': 10}, 800, 1, None)  # valor já em texto
    assert can.chamadas[0][3] == 'Sim'


def test_radio_com_posicao_na_opcao_marca_x():
    campo = CampoFalso('radio', [{'id': 'M', 'texto': 'M', 'posicao': {'x': 5, 'y': 5}},
                                 {'id': 'F', 'texto': 'F', 'posicao': {'x': 50, 'y': 5}}])
    can = CanvasEspiao()
    engine._desenhar_campo(can, campo, 'F', {'x': 100, 'y': 5}, 800, 1, None)
    assert [(c[1], c[3]) for c in can.chamadas] == [(50, 'X')]


# --- engine: valores ------------------------------------------------------------------------------

def test_valor_digitado_vence_o_automatico_e_vazio_proposital_fica_vazio(contexto):
    campo = CampoFalso('text')
    campo.atributo_paciente = 'paciente.nome'
    assert resolver_valores([campo], {'1': 'OUTRO NOME'}, contexto) == {'1': 'OUTRO NOME'}
    assert resolver_valores([campo], {'1': ''}, contexto) == {'1': 'PACIENTE SINTETICO'}
    assert resolver_valores([campo], {'1': ''}, contexto, manter_vazios={'1'}) == {'1': ''}
    assert resolver_valores([campo], {}, contexto) == {'1': 'PACIENTE SINTETICO'}


def test_padrao_e_copiar_de(contexto):
    origem = CampoFalso('text', nome='CID-10')
    origem.id = 1
    copia = CampoFalso('text', nome='CID-10 (justificativa)')
    copia.id = 2
    copia.validacoes = {'copiar_de': 'CID-10'}
    padrao = CampoFalso('textarea', nome='Resumo')
    padrao.id = 3
    padrao.validacoes = {'padrao': 'BAV: '}
    campos = [origem, copia, padrao]
    assert resolver_valores(campos, {'1': 'H00.1'}, contexto) == {'1': 'H00.1', '2': 'H00.1', '3': 'BAV: '}
    assert resolver_valores(campos, {'1': 'H00.1', '2': 'H01.0'}, contexto)['2'] == 'H01.0'


def test_procedimentos_normaliza_e_ignora_codigo_desconhecido(contexto):
    importar_procedimentos()
    campo = CampoFalso('procedimentos')
    valores = resolver_valores([campo], {'1': [{'codigo': CALAZIO, 'qtd': '3'}, {'codigo': '99.99.99.999-9'},
                                                {'codigo': CALAZIO}]}, contexto)
    assert valores['1'] == [{'codigo': CALAZIO, 'qtd': 3,
                             'nome': 'EXÉRESE DE CALAZIO E OUTRAS PEQUENAS LESOES DA PALPEBRA E SUPERCILIOS'}]
    # JSON gravado em CampoPreenchidoDocumento também é aceito (regeração do documento)
    assert resolver_valores([campo], {'1': json.dumps(valores['1'])}, contexto)['1'] == valores['1']


def _pdf_base(paginas=1):
    buffer = io.BytesIO()
    pdf = rl_canvas.Canvas(buffer)
    for _ in range(paginas):
        pdf.drawString(10, 10, ' ')
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def test_template_antigo_posicao_lista_e_atributo_sem_prefixo(paciente):
    usuario = User.objects.create_user('u', password='x')
    template = TemplateDocumento.objects.create(
        nome='Antigo', criado_por=usuario,
        arquivo_template=SimpleUploadedFile('t.pdf', _pdf_base(2), content_type='application/pdf'))
    CampoTemplateDocumento.objects.create(template=template, nome_campo='nome', atributo_paciente='nome',
                                          posicao=[{'x': 50, 'y': 100}, {'x': 50, 'y': 100, 'pagina': 2}])
    CampoTemplateDocumento.objects.create(template=template, nome_campo='obs', tipo_campo='text',
                                          posicao={'x': 50, 'y': 200})
    from core.utils import gerar_documento_pdf

    leitor = PdfReader(gerar_documento_pdf(paciente, template, {}))
    assert len(leitor.pages) == 2
    assert all('PACIENTE SINTETICO' in p.extract_text() for p in leitor.pages)


# --- layouts + engine (PDF real) ------------------------------------------------------------------

def test_bpai_uma_pagina_por_procedimento_com_dados_automaticos(instalado, contexto):
    template = instalado[bpai.NOME]
    codigos = [CALAZIO, '02.11.06.002-0', '02.11.06.003-8']
    leitor = _pdf(template, {'Procedimentos': [{'codigo': c, 'qtd': 1} for c in codigos], 'CID-10': 'H00.1'},
                  contexto)

    assert len(leitor.pages) == 3
    textos = [p.extract_text() for p in leitor.pages]
    for codigo, texto in zip(codigos, textos):
        assert codigo in texto
        assert sum(c in texto for c in codigos) == 1
        for esperado in ('11/2026', '16/11/2026', 'CRE- METROPOLITANO', '5604613', '700000000000002', '225265',
                         'PACIENTE SINTETICO', '700000000000001', '01/02/50', 'MEDICO FICTICIO', 'H00.1', '01 - Eletivo',
                         'BAV:'):
            assert esperado in texto, esperado
    assert 'EXÉRESE DE CALAZIO' in textos[0]
    assert textos[0].count('H00.1') == 2  # CID da justificativa copiado do solicitado


def test_bpai_sem_procedimento_gera_uma_pagina(instalado, contexto):
    assert len(_pdf(instalado[bpai.NOME], {}, contexto).pages) == 1


def _marcas_x(template, valores):
    """Posições (x, y) dos "X" desenhados no PDF, via espião no canvas da engine."""
    marcas = []
    original = rl_canvas.Canvas.drawCentredString

    def espiao(self, x, y, texto, *args, **kwargs):
        if texto == 'X':
            marcas.append((round(x, 1), round(y, 1)))
        return original(self, x, y, texto, *args, **kwargs)

    rl_canvas.Canvas.drawCentredString = espiao
    try:
        gerar_pdf(template, valores)
    finally:
        rl_canvas.Canvas.drawCentredString = original
    return sorted(marcas)


def test_receituario_marca_x_nas_duas_vias(instalado, contexto):
    template = instalado[receituario_colirios.NOME]
    ids = _ids(template)
    timolol = receituario_colirios.nome_campo_medicamento(1, 'Maleato de Timolol 0,5%')
    dorzolamida = receituario_colirios.nome_campo_medicamento(6, 'Dorzolamida 2%')
    valores = resolver_valores(template.campos.all(), {ids[timolol]: ['od', 'oe'], ids[dorzolamida]: ['oe']},
                               contexto)
    assert valores[ids[timolol]] == ['od', 'oe', 'usar']
    assert valores[ids[dorzolamida]] == ['oe', 'usar']

    layout = receituario_colirios.construir()
    altura = 595.28
    esperadas = []
    for campo in layout.campos:
        for opcao in campo.opcoes or []:
            marcado = (campo.nome == timolol) or (campo.nome == dorzolamida and opcao['id'] in ('usar', 'oe'))
            if marcado:
                for pos in opcao['posicao']:
                    esperadas.append((round(pos['x'] + pos['width'] / 2, 1), round(altura - pos['y'], 1)))
    assert len(esperadas) == 10  # (3 + 2 marcas) x 2 vias
    vias = {x < 421 for x, _ in esperadas}
    assert vias == {True, False}
    assert _marcas_x(template, valores) == sorted(esperadas)


def test_bpai_sexo_marca_x_na_caixa_do_paciente(instalado, contexto):
    template = instalado[bpai.NOME]
    valores = resolver_valores(template.campos.all(), {}, contexto)
    campo = template.campos.get(nome_campo='Sexo')
    pos_f = next(o for o in campo.opcoes if o['id'] == 'F')['posicao']
    assert (round(pos_f['x'] + pos_f['width'] / 2, 1), round(841.89 - pos_f['y'], 1)) in _marcas_x(template, valores)


def test_prescricao_valores_centralizados_e_assinatura(instalado, contexto):
    template = instalado[prescricao_oculos.NOME]
    tabela = {c.nome_campo: c for c in template.campos.all() if c.nome_campo.startswith(('Longe', 'Perto'))}
    assert len(tabela) == 12
    assert all(c.posicao['align'] == 'center' and c.posicao['width'] > 0 for c in tabela.values())
    leitor = _pdf(template, {nome: f'{i:+.2f}' for i, nome in enumerate(tabela)}, contexto)
    texto = leitor.pages[0].extract_text()
    assert 'Dr(a). MEDICO FICTICIO' in texto
    assert 'CRM: 00000-ES / 11111-MG' in texto
    assert 'Médico(a) Oftalmologista' in texto
    assert '+11.00' in texto and '16/11/2026' in texto


def test_campos_dos_layouts_tem_posicoes_dentro_da_pagina():
    for construir in (bpai.construir, prescricao_oculos.construir, receituario_colirios.construir):
        layout = construir()
        largura, altura = PdfReader(io.BytesIO(layout.pdf)).pages[0].mediabox.upper_right
        for campo in layout.campos:
            posicoes = list(campo.posicoes)
            for opcao in campo.opcoes or []:
                posicoes += opcao['posicao'] if isinstance(opcao.get('posicao'), list) else (
                    [opcao['posicao']] if opcao.get('posicao') else [])
            assert posicoes, campo.nome
            for pos in posicoes:
                assert 0 <= pos['x'] and pos['x'] + pos.get('width', 0) <= float(largura), campo.nome
                assert 0 < pos['y'] < float(altura), campo.nome


# --- commands ------------------------------------------------------------------------------------

def test_instalar_templates_idempotente(capsys):
    call_command('instalar_templates_oftalmo')
    estado = sorted(CampoTemplateDocumento.objects.values_list('pk', 'template_id', 'nome_campo'))
    templates = sorted(TemplateDocumento.objects.values_list('pk', 'nome', 'ativo'))
    call_command('instalar_templates_oftalmo')

    assert sorted(CampoTemplateDocumento.objects.values_list('pk', 'template_id', 'nome_campo')) == estado
    assert sorted(TemplateDocumento.objects.values_list('pk', 'nome', 'ativo')) == templates
    assert [n for _, n, ativo in templates if ativo] == sorted([bpai.NOME, prescricao_oculos.NOME,
                                                                receituario_colirios.NOME])
    assert 'Campos: 0 criados' in capsys.readouterr().out
    for template in TemplateDocumento.objects.all():
        assert template.arquivo_template.storage.exists(template.arquivo_template.name)


def test_instalar_trata_campo_removido_do_layout(paciente):
    resultado = instalar_templates()
    template = TemplateDocumento.objects.get(nome=prescricao_oculos.NOME)
    usado = CampoTemplateDocumento.objects.create(template=template, nome_campo='Antigo usado', posicao={'x': 1, 'y': 1})
    livre = CampoTemplateDocumento.objects.create(template=template, nome_campo='Antigo livre', posicao={'x': 1, 'y': 1})
    documento = Documento.objects.create(paciente=paciente, template=template, nome='doc')
    CampoPreenchidoDocumento.objects.create(documento=documento, campo_template=usado, valor='x')

    resultado = instalar_templates()

    assert (resultado.campos_excluidos, resultado.campos_inativados) == (1, 1)
    assert not CampoTemplateDocumento.objects.filter(pk=livre.pk).exists()
    usado.refresh_from_db()
    assert usado.validacoes == {'inativo': True}
    assert Documento.objects.filter(pk=documento.pk).exists()


def test_instalar_desativa_receituario_antigo_so_sem_documentos(paciente):
    sem_doc = TemplateDocumento.objects.create(nome='Receituario Colirio - Timolol')
    instalar_templates()
    sem_doc.refresh_from_db()
    assert sem_doc.ativo is False

    com_doc = TemplateDocumento.objects.create(nome='Receituario Colirio - Timolol')
    Documento.objects.create(paciente=paciente, template=com_doc, nome='doc')
    resultado = instalar_templates()
    com_doc.refresh_from_db()
    assert com_doc.ativo is True
    assert any('mantido' in aviso for aviso in resultado.avisos)


def test_importar_procedimentos_sigtap(capsys):
    call_command('importar_procedimentos_sigtap')
    assert Procedimento.objects.count() == 146
    calazio = Procedimento.objects.get(codigo=CALAZIO)
    assert calazio.instrumentos == 'AIH/APAC' and calazio.grupo == 'Pálpebras e vias lacrimais'
    assert '146 criados' in capsys.readouterr().out

    call_command('importar_procedimentos_sigtap')
    assert Procedimento.objects.count() == 146
    assert '0 criados, 0 atualizados, 146 inalterados' in capsys.readouterr().out


def test_importar_procedimentos_cabecalho_invalido(tmp_path):
    arquivo = tmp_path / 'x.csv'
    arquivo.write_text('a,b\n1,2\n', encoding='utf-8')
    with pytest.raises(CommandError, match='Cabeçalho'):
        call_command('importar_procedimentos_sigtap', '--csv', str(arquivo))


# --- tela gerar documento ------------------------------------------------------------------------

@pytest.fixture
def usuario(client):
    usuario = User.objects.create_user('operador', password='x')
    client.force_login(usuario)
    return usuario


def test_data_atendimento_padrao(paciente):
    hoje = date(2026, 11, 13)
    assert data_atendimento_padrao(paciente, hoje) == hoje
    Agendamento.objects.create(paciente=paciente, solicitacao='1', item_agendamento='X',
                               data_agenda=datetime(2026, 11, 20, 9, tzinfo=BRT))
    assert data_atendimento_padrao(paciente, hoje) == date(2026, 11, 20)
    Agendamento.objects.create(paciente=paciente, solicitacao='2', item_agendamento='X',
                               data_agenda=datetime(2026, 11, 13, 7, tzinfo=BRT))
    assert data_atendimento_padrao(paciente, hoje) == hoje
    assert data_atendimento_padrao(None, hoje) == hoje


def test_valores_automaticos_endpoint(client, usuario, instalado, paciente, medico):
    template = instalado[bpai.NOME]
    ids = _ids(template)
    resposta = client.get(reverse('valores_automaticos'), {
        'template': template.pk, 'paciente': paciente.pk, 'medico': medico.pk, 'data': '2026-11-16'})
    dados = resposta.json()
    assert dados['data_atendimento'] == '2026-11-16'
    assert dados['exige_medico'] is True
    valores = dados['valores']
    assert valores[ids['Nome do Paciente']] == 'PACIENTE SINTETICO'
    assert valores[ids['Mês/ano']] == '11/2026'
    assert valores[ids['CNS do Profissional']] == '700000000000002'
    assert valores[ids['Sexo']] == 'F'
    assert valores[ids['Car. Atend.']] == '01'
    assert valores[ids['Resumo do Exame Físico']] == 'BAV: '
    assert ids['Raça/Cor'] not in valores


def test_valores_automaticos_sem_data_usa_padrao(client, usuario, instalado, paciente):
    Agendamento.objects.create(paciente=paciente, solicitacao='1', item_agendamento='X',
                               data_agenda=datetime(2030, 1, 2, 9, tzinfo=BRT))
    dados = client.get(reverse('valores_automaticos'), {
        'template': instalado[bpai.NOME].pk, 'paciente': paciente.pk}).json()
    assert dados['data_atendimento'] == '2030-01-02'


def test_campos_template_json_inclui_catalogo_e_opcoes(client, usuario, instalado):
    campos = client.get(reverse('campos_template_json', args=[instalado[bpai.NOME].pk])).json()
    procedimentos = next(c for c in campos if c['tipo'] == 'procedimentos')
    grupos = {g['grupo']: g['itens'] for g in procedimentos['catalogo']}
    assert sum(len(i) for i in grupos.values()) == 146
    assert any(i['codigo'] == CALAZIO for i in grupos['Pálpebras e vias lacrimais'])
    sexo = next(c for c in campos if c['nome'] == 'Sexo')
    assert [o['id'] for o in sexo['opcoes']] == ['M', 'F'] and 'posicao' not in sexo['opcoes'][0]
    cid = next(c for c in campos if c['nome'] == 'CID-10 (justificativa)')
    assert cid['validacoes'] == {'copiar_de': 'CID-10'}


def _post_bpai(template, paciente, medico=None, **campos_por_nome):
    ids = _ids(template)
    dados = {'paciente_id': paciente.pk, 'template_id': template.pk, 'nome_documento': 'BPA-I',
             'data_atendimento': '2026-11-16', f'campo_{ids["Procedimentos"]}[]': [CALAZIO],
             f'campo_{ids["Procedimentos"]}_qtd_{CALAZIO}': '2'}
    if medico:
        dados['medico_id'] = medico.pk
    for nome, valor in campos_por_nome.items():
        dados[f'campo_{ids[nome]}'] = valor
    return dados


def test_gerar_documento_exige_medico(client, usuario, instalado, paciente):
    resposta = client.post(reverse('gerar_documento'), _post_bpai(instalado[bpai.NOME], paciente))
    assert resposta.status_code == 200
    assert 'Selecione o médico' in resposta.content.decode()
    assert not Documento.objects.exists()


def test_gerar_documento_valor_editado_vence_e_grava_tudo(client, usuario, instalado, paciente, medico):
    template = instalado[bpai.NOME]
    ids = _ids(template)
    dados = _post_bpai(template, paciente, medico, **{'Nome do Paciente': 'NOME EDITADO NA TELA', 'Telefone': ''})

    resposta = client.post(reverse('gerar_documento'), dados)

    assert resposta.status_code == 200 and resposta['Content-Type'] == 'application/pdf'
    texto = PdfReader(io.BytesIO(b''.join(resposta.streaming_content))).pages[0].extract_text()
    assert 'NOME EDITADO NA TELA' in texto and 'PACIENTE SINTETICO' not in texto
    assert '(27) 90000-0000' not in texto  # apagado de propósito
    assert 'MEDICO FICTICIO' in texto and CALAZIO in texto and '16/11/2026' in texto
    documento = Documento.objects.get()
    assert (documento.medico, documento.data_atendimento) == (medico, date(2026, 11, 16))
    gravados = {cp.campo_template.nome_campo: cp.valor for cp in documento.campos_preenchidos.all()}
    assert gravados['Nome do Paciente'] == 'NOME EDITADO NA TELA'
    assert gravados['CNES'] == '5604613'
    assert json.loads(gravados['Procedimentos'])[0]['qtd'] == 2
    assert client.session['documentos_ultimo_medico_id'] == medico.pk
    assert str(ids['Procedimentos']) in [str(cp.campo_template_id) for cp in documento.campos_preenchidos.all()]


def test_tela_preseleciona_medico_do_usuario_ou_ultimo_usado(client, usuario, instalado, medico):
    outro = Medico.objects.create(nome='OUTRO FICTICIO', crm='22222-ES')
    resposta = client.get(reverse('gerar_documento'))
    assert resposta.context['medico_id_selecionado'] == ''
    session = client.session
    session['documentos_ultimo_medico_id'] = outro.pk
    session.save()
    assert client.get(reverse('gerar_documento')).context['medico_id_selecionado'] == str(outro.pk)
    medico.usuario = usuario
    medico.save()
    assert client.get(reverse('gerar_documento')).context['medico_id_selecionado'] == str(medico.pk)
