"""Lista/detalhe de pacientes por data do atendimento (Agendamento.data_agenda). Dados sintéticos."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone

from core.agenda import limites_do_dia
from core.models import Agendamento, Paciente

pytestmark = pytest.mark.django_db

BRT = ZoneInfo('America/Sao_Paulo')
URL = reverse('paciente_list')
DIA = date(2030, 3, 15)

_seq = {'solicitacao': 9000000}


def _paciente(nome, **extra):
    return Paciente.objects.create(nome=nome, data_nascimento=date(1950, 2, 1), **extra)


def _agendar(paciente, quando, item='CONSULTA SINTETICA'):
    _seq['solicitacao'] += 1
    return Agendamento.objects.create(paciente=paciente, solicitacao=str(_seq['solicitacao']),
                                      item_agendamento=item, data_agenda=quando)


def _brt(dia, hora, minuto=0):
    return datetime(dia.year, dia.month, dia.day, hora, minuto, tzinfo=BRT)


@pytest.fixture
def cliente(client):
    client.force_login(User.objects.create_user('operador', password='x'))
    return client


def _nomes(resposta):
    return [p.nome for p in resposta.context['pacientes']]


# --- filtro por data ----------------------------------------------------------------------------

def test_limites_do_dia_no_fuso_local():
    inicio, fim = limites_do_dia(DIA)
    assert inicio == _brt(DIA, 0) and fim == _brt(DIA + timedelta(days=1), 0)
    assert inicio.astimezone(ZoneInfo('UTC')).hour == 3


def test_filtro_por_data_borda_de_fuso(cliente):
    # 23:30 BRT do dia 15 = 02:30 UTC do dia 16: deve aparecer no dia 15, não no 16.
    noite = _paciente('NOITE')
    _agendar(noite, _brt(DIA, 23, 30))
    madrugada = _paciente('MADRUGADA')
    _agendar(madrugada, _brt(DIA + timedelta(days=1), 0, 15))
    vespera = _paciente('VESPERA')
    _agendar(vespera, _brt(DIA - timedelta(days=1), 23, 59))

    assert _nomes(cliente.get(URL, {'data': DIA.isoformat()})) == ['NOITE']
    assert _nomes(cliente.get(URL, {'data': (DIA + timedelta(days=1)).isoformat()})) == ['MADRUGADA']


def test_filtro_por_data_ordena_por_horario_e_nome_sem_duplicar(cliente):
    ana = _paciente('ANA')
    _agendar(ana, _brt(DIA, 10), 'RETORNO')
    _agendar(ana, _brt(DIA, 8), 'CONSULTA ANA')  # dois no dia: aparece uma vez, com o primeiro horário
    bia = _paciente('BIA')
    _agendar(bia, _brt(DIA, 9))
    caio = _paciente('CAIO')
    _agendar(caio, _brt(DIA, 9))
    _agendar(_paciente('OUTRO DIA'), _brt(DIA + timedelta(days=2), 9))
    _paciente('SEM AGENDAMENTO')

    resposta = cliente.get(URL, {'data': DIA.isoformat()})

    pacientes = list(resposta.context['pacientes'])
    assert [p.nome for p in pacientes] == ['ANA', 'BIA', 'CAIO']
    assert resposta.context['pacientes'].paginator.count == 3
    assert timezone.localtime(pacientes[0].atendimento) == _brt(DIA, 8)
    assert pacientes[0].atendimento_item == 'CONSULTA ANA'
    html = resposta.content.decode()
    assert '15/03/2030 08:00' in html and 'CONSULTA ANA' in html
    assert '3 pacientes com atendimento em 15/03/2030' in html


def test_filtro_por_data_combina_com_busca(cliente):
    _agendar(_paciente('ANA'), _brt(DIA, 8))
    _agendar(_paciente('BIA'), _brt(DIA, 9))
    assert _nomes(cliente.get(URL, {'data': DIA.isoformat(), 'search': 'bia'})) == ['BIA']


def test_data_invalida_e_ignorada(cliente):
    _paciente('ANA')
    resposta = cliente.get(URL, {'data': '2030-02-31'})
    assert _nomes(resposta) == ['ANA']
    assert resposta.context['data_filtro'] is None
    assert 'Data do atendimento inválida' in resposta.content.decode()


# --- sem filtro ---------------------------------------------------------------------------------

def test_sem_filtro_ordem_por_nome_e_coluna_proximo_ou_ultimo(cliente):
    agora = timezone.now()
    zeca = _paciente('ZECA')
    _agendar(zeca, agora - timedelta(days=10), 'ANTIGO')
    _agendar(zeca, agora + timedelta(days=5), 'FUTURO DISTANTE')
    _agendar(zeca, agora + timedelta(days=1), 'PROXIMO')
    bruno = _paciente('BRUNO')
    _agendar(bruno, agora - timedelta(days=30), 'MAIS ANTIGO')
    _agendar(bruno, agora - timedelta(days=2), 'ULTIMO')
    _paciente('ALICE')

    pacientes = list(cliente.get(URL).context['pacientes'])

    assert [p.nome for p in pacientes] == ['ALICE', 'BRUNO', 'ZECA']
    alice, bruno_l, zeca_l = pacientes
    assert (alice.atendimento, alice.atendimento_item) == (None, None)
    assert bruno_l.atendimento_item == 'ULTIMO'
    assert zeca_l.atendimento_item == 'PROXIMO'
    assert abs(zeca_l.atendimento - (agora + timedelta(days=1))) < timedelta(seconds=1)


def test_agendamento_sem_data_nao_conta(cliente):
    paciente = _paciente('ANA')
    Agendamento.objects.create(paciente=paciente, solicitacao='9999999', item_agendamento='SEM DATA')
    pacientes = list(cliente.get(URL).context['pacientes'])
    assert pacientes[0].atendimento is None


# --- busca --------------------------------------------------------------------------------------

@pytest.mark.parametrize('termo', ['700000000000123', '0000123', '7654321', '123.456.789-09', '12345678909'])
def test_busca_por_cns_codigo_e_cpf(cliente, termo):
    _paciente('ALVO', cns='700000000000123', codigo_cidadao='7654321', cpf='123.456.789-09')
    _paciente('OUTRO', cns='700000000000999', codigo_cidadao='1111111', cpf='111.444.777-35')
    assert _nomes(cliente.get(URL, {'search': termo})) == ['ALVO']


# --- paginação e performance --------------------------------------------------------------------

def test_paginacao_25_por_pagina_mantem_filtros(cliente):
    for i in range(30):
        _agendar(_paciente(f'PACIENTE {i:02d}'), _brt(DIA, 8, i))

    resposta = cliente.get(URL, {'data': DIA.isoformat(), 'search': 'paciente'})

    assert len(resposta.context['pacientes']) == 25
    assert resposta.context['querystring'] == 'data=2030-03-15&search=paciente'
    assert '?page=2&amp;data=2030-03-15&amp;search=paciente' in resposta.content.decode()
    pagina2 = cliente.get(URL, {'data': DIA.isoformat(), 'search': 'paciente', 'page': 2})
    assert _nomes(pagina2) == [f'PACIENTE {i:02d}' for i in range(25, 30)]


def _popular(n):
    agora = timezone.now()
    for i in range(n):
        paciente = _paciente(f'P{i:03d}')
        _agendar(paciente, _brt(DIA, 8))
        _agendar(paciente, _brt(DIA, 9))
        _agendar(paciente, agora + timedelta(days=i + 1))


@pytest.mark.parametrize('params', [{}, {'data': DIA.isoformat()}, {'search': 'P0'}])
def test_lista_sem_n_mais_1(cliente, django_assert_num_queries, params):
    _popular(30)
    # sessão + usuário + count + página: constante, independente do número de pacientes/agendamentos.
    with django_assert_num_queries(4):
        resposta = cliente.get(URL, params)
    assert resposta.status_code == 200
    assert len(resposta.context['pacientes']) == 25


# --- detalhe ------------------------------------------------------------------------------------

def test_detalhe_mostra_agendamentos_ordenados_e_destaca_hoje(cliente):
    hoje = timezone.localdate()
    paciente = _paciente('ANA', cns='700000000000123', codigo_cidadao='7654321', origem=Paciente.ORIGEM_SOULMV)
    _agendar(paciente, _brt(hoje - timedelta(days=3), 9), 'PASSADO')
    _agendar(paciente, _brt(hoje, 14, 30), 'DE HOJE')
    _agendar(paciente, _brt(hoje + timedelta(days=7), 10), 'FUTURO')
    Agendamento.objects.create(paciente=paciente, solicitacao='9999998', item_agendamento='SEM DATA')

    resposta = cliente.get(reverse('paciente_detail', args=[paciente.pk]))

    itens = [a.item_agendamento for a in resposta.context['agendamentos']]
    assert itens == ['FUTURO', 'DE HOJE', 'PASSADO', 'SEM DATA']
    html = resposta.content.decode()
    assert html.count('table-warning') == 1
    linha_hoje = html[html.index('table-warning'):]
    assert f'{hoje:%d/%m/%Y} 14:30' in linha_hoje[:400] and 'DE HOJE' in linha_hoje[:600]
    for texto in ('700000000000123', '7654321', 'Soul MV', 'Agendamentos'):
        assert texto in html


def test_detalhe_sem_agendamentos(cliente):
    paciente = _paciente('ANA')
    html = cliente.get(reverse('paciente_detail', args=[paciente.pk])).content.decode()
    assert 'Nenhum agendamento registrado.' in html
    assert 'Manual' in html


# --- gerar documento ----------------------------------------------------------------------------

def test_gerar_documento_mostra_atendimento_de_hoje_no_select(cliente):
    hoje = timezone.localdate()
    ana = _paciente('ANA')
    _agendar(ana, _brt(hoje, 7, 45))
    _agendar(ana, _brt(hoje, 11))
    bia = _paciente('BIA')
    _agendar(bia, _brt(hoje + timedelta(days=1), 8))

    resposta = cliente.get(reverse('gerar_documento'))

    html = resposta.content.decode()
    assert 'ANA - sem CPF — atendimento hoje 07:45' in html
    assert 'BIA - sem CPF\n' in html.replace('\r\n', '\n')
    assert [p.nome for p in resposta.context['pacientes']] == ['ANA', 'BIA']
