from datetime import date, datetime
from pathlib import Path

import pytest

from core.integracao.soulmv.leitor import (
    LayoutInvalidoError,
    LinhaInvalidaError,
    ler_arquivo,
    ler_conteudo,
    normalizar_cpf,
    parse_data_hora,
)

FIXTURES = Path(__file__).parent / 'fixtures'


@pytest.mark.parametrize(
    ('entrada', 'esperado'),
    [
        ('00012345678', '000.123.456-78'),
        ('351074643', '003.510.746-43'),
        ('000.123.456-78', '000.123.456-78'),
        ('', None),
        ('   ', None),
    ],
)
def test_normalizar_cpf(entrada, esperado):
    assert normalizar_cpf(entrada) == esperado


def test_normalizar_cpf_com_digitos_demais():
    with pytest.raises(LinhaInvalidaError):
        normalizar_cpf('123456789012')


def test_parse_data_hora_formatos():
    assert parse_data_hora('13/11/2026 08:06', 'x') == datetime(2026, 11, 13, 8, 6)
    assert parse_data_hora('30/11/2026', 'x') == datetime(2026, 11, 30)
    assert parse_data_hora('', 'x') is None
    with pytest.raises(LinhaInvalidaError):
        parse_data_hora('2026-11-13', 'x')


def test_leitura_basica():
    resultado = ler_arquivo(FIXTURES / 'soulmv_basico.csv')

    assert resultado.encoding == 'utf-8-sig'
    assert resultado.linhas_lidas == 11
    assert len(resultado.registros) == 9
    primeiro = resultado.registros[0]
    assert primeiro.solicitacao == '8000001'
    assert primeiro.codigo_cidadao == '1000001'
    assert primeiro.cpf == '000.123.456-78'
    assert primeiro.cns == '700000000000001'
    assert primeiro.nome_social is None
    assert primeiro.data_nascimento == date(1950, 2, 1)
    assert primeiro.data_agenda == datetime(2026, 11, 13, 8, 1)

    sem_cpf = next(r for r in resultado.registros if r.solicitacao == '8000006')
    assert sem_cpf.cpf is None

    com_virgula = next(r for r in resultado.registros if r.solicitacao == '8000010')
    assert com_virgula.item_agendamento == 'CONSULTA, RETORNO'
    assert com_virgula.data_agenda is None
    assert com_virgula.nome_social == 'MARIA'


def test_rejeicoes_nao_derrubam_o_lote_e_nao_expoem_dados():
    resultado = ler_arquivo(FIXTURES / 'soulmv_basico.csv')

    motivos = {r.solicitacao: r for r in resultado.rejeicoes}
    assert set(motivos) == {'8000008', '8000009'}
    assert motivos['8000008'].motivo == 'Data Nascimento inválida'
    assert motivos['8000008'].linha == 9
    assert motivos['8000009'].motivo == 'sem Código cidadão e sem CPF'
    assert '1970' not in motivos['8000008'].motivo


def test_cp1252():
    resultado = ler_arquivo(FIXTURES / 'soulmv_cp1252.csv')

    assert resultado.encoding == 'cp1252'
    assert resultado.rejeicoes == []
    (registro,) = resultado.registros
    assert registro.nome == 'JOSÉ DA CONCEIÇÃO'
    assert registro.item_agendamento == 'CONSULTA EM OFTALMOLOGIA ÓPTICA'
    assert registro.cpf == '333.444.555-06'


def test_cabecalho_invalido():
    with pytest.raises(LayoutInvalidoError, match='Nome do cidadão'):
        ler_arquivo(FIXTURES / 'soulmv_cabecalho_invalido.csv')


def test_arquivo_vazio():
    with pytest.raises(LayoutInvalidoError):
        ler_conteudo(b'')


def test_linha_com_colunas_a_menos_e_rejeitada():
    cabecalho = (FIXTURES / 'soulmv_somente_cabecalho.csv').read_bytes()
    resultado = ler_conteudo(cabecalho + '8000099,UNIDADE,123\r\n'.encode())

    assert resultado.registros == []
    assert len(resultado.rejeicoes) == 1
    assert 'quantidade de colunas' in resultado.rejeicoes[0].motivo
