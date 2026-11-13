"""Cliente HTTP do Soul MV: 100% mockado (o MV não é alcançável fora do servidor).

Todos os dados são sintéticos.
"""
import base64
import json
import logging
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
import requests
from django.core.exceptions import ImproperlyConfigured
from requests.structures import CaseInsensitiveDict

from core.integracao.soulmv.cliente_http import (
    ClienteSoulMV,
    ContextoMV,
    ExtratorHttpSoulMV,
    extrair_token_de_location,
    normalizar_descricao,
    periodo_utc,
)
from core.integracao.soulmv.exportacao_csv import registros_para_csv
from core.integracao.soulmv.extrator import ExtracaoError, obter_extrator
from core.integracao.soulmv.importador import importar_arquivo
from core.integracao.soulmv.leitor import COLUNAS_ESPERADAS, ler_conteudo
from core.models import Agendamento, ExecucaoImportacao, Paciente

USUARIO = 'fulano.teste'
SENHA = 'S3nha-Sintetica!'
TOKEN = 'AT-999-TOKENSINTETICOxyz'
TICKET = 'ST-123-TICKETSINTETICO'

HOST = 'https://mv.test'
API = f'{HOST}/consultas-exames/api/'
AUTHORIZE = (f'{HOST}/public-health-sso/oauth2.0/authorize?response_type=token&client_id=consultasExamesOauth'
             f'&redirect_uri={HOST}/consultas-exames/%23/login&state=abc&code_challenge=xyz&code_challenge_method=S256')
PAGINA_LOGIN = f'{HOST}/public-health-sso/login?service=callback'
POST_LOGIN = f'{HOST}/public-health-sso/login'
CALLBACK = f'{HOST}/public-health-sso/oauth2.0/callbackAuthorize?ticket={TICKET}'
AUTHORIZE_HTTP = 'http://mv.test/public-health-sso/oauth2.0/authorize?response_type=token&state=abc'
AUTHORIZE_HTTPS = f'{HOST}/public-health-sso/oauth2.0/authorize?response_type=token&state=abc'
FINAL = f'{HOST}/consultas-exames/#access_token={TOKEN}&token_type=bearer&expires_in=28800'
LISTAGEM = API + 'solicitacao-procedimento/solicitacoes-consulta-regulador-com-vinculos'

HTML_LOGIN = """<!DOCTYPE html><html><body>
<form id="fm1" action="login" method="post">
  <input id="username" name="username" type="text" value="">
  <input id="password" name="password" type="password" value="">
  <input type="hidden" name="execution" value="e1s1-EXECUCAO">
  <input type="hidden" name="_eventId" value="submit">
  <input type="hidden" name="geolocation" value="">
  <input type="checkbox" name="rememberMe" value="true">
  <button name="submitBtn" type="submit">ENTRAR</button>
</form></body></html>"""

HTML_LOGIN_ERRO = HTML_LOGIN.replace('<form', '<div class="alert">Credenciais inv&aacute;lidas.</div><form')

CURRENT_USER = {'id': 14217, 'login': 'FULANO.TESTE', 'administrador': False,
                'redefinirSenha': False, 'senhaExpirada': False}
PERFIS = [
    {'id': 46, 'descricao': 'EXECUTANTE  CMCE', 'vinculoUps': False, 'tipoPerfil': 1, 'snVisivel': True},
    {'id': 57, 'descricao': 'COORDENADOR  DE UNIDADE CMCE', 'vinculoUps': False, 'tipoPerfil': 1, 'snVisivel': True},
    {'id': 68, 'descricao': 'PRESTADOR CMCE', 'vinculoUps': False, 'tipoPerfil': 1, 'snVisivel': True},
]


def _vinculo(id_vinculo, id_estab, nome):
    return {'id': id_vinculo,
            'profissionalSigas': {'id': 999, 'cidadao': {'nome': 'PESSOA SINTETICA'}},
            'estabelecimento': {'id': id_estab, 'nomeFantasia': nome, 'cnes': '9999999'},
            'ocupacao': {'id': 9, 'nome': 'OCUPACAO', 'medico': False, 'codigoCbo': '999999'}}


VINCULOS = [
    _vinculo(260001, 3001, 'FUNDAO - RCS SOLUCOES MEDICAS S/A'),
    _vinculo(260535, 2147, 'RCS SOLUCOES MEDICAS S/A'),
    _vinculo(261621, 711, 'NUCLEO ESPECIAL DE REGULACAO DE CONSULTAS E EXAMES'),
]


def _registro(**extra):
    base = {
        'idSolicitacaoProcedimento': 8000001,
        'nomeUnidadeSolicitante': '  UNIDADE SINTETICA  ',
        'idCidadao': 1234567,
        'numeroCartaoSus': '700000000000001',
        'cpf': '00012345678',
        'nomeCidadaoSocial': None,
        'nomeCidadao': 'FULANO DE TAL',
        'nascimento': '1950-02-01T00:00:00',
        'dataSolicitacao': '2026-11-01T10:20:30',
        'descricaoItemAgendamento': 'CONSULTA EM OFTALMOLOGIA, GLAUCOMA ADULTO',
        'nomeUnidadeExecutante': 'RCS SOLUCOES MEDICAS S/A',
        'nomeProfExecPorSit': None,
        'flagRealizadoForaRede': False,
        'dataAgenda': '2026-11-13T08:06:00',
        'dataAtendimento': None,
        'dataMarcacao': '2026-11-05T09:00:00',
        'situacao': 5,
        'descricaMotivoProcedNaoRealiz': None,
        'flagEmissaoGuia': True,
        'dataMarcacaoOriginal': '2026-11-05T09:00:00',
        'marcadoPor': 'OPERADOR SINTETICO',
        'tipoSolicitacao': 'CONSULTA',
        'descricaoPrioridade': 'NORMAL',
        'sexo': 'M',
        'nomeMae': 'MAE SINTETICA',
    }
    base.update(extra)
    return base


# --- dublê de requests.Session ------------------------------------------------------------------

def _resposta(status, url, *, texto='', json_=None, location=None):
    r = requests.Response()
    r.status_code = status
    r.url = url
    r.encoding = 'utf-8'
    r._content = (json.dumps(json_) if json_ is not None else texto).encode('utf-8')
    r.headers = CaseInsensitiveDict({'Location': location} if location else {})
    return r


class SessaoFalsa(requests.Session):
    """Responde por (método, URL sem query-string de `params`) e registra as chamadas."""

    def __init__(self, rotas):
        super().__init__()
        self.rotas = dict(rotas)
        self.chamadas = []

    def request(self, method, url, **kwargs):
        self.chamadas.append((method, url, kwargs))
        resposta = self.rotas.get((method, url))
        if resposta is None:
            raise AssertionError(f'chamada inesperada: {method} {url}')
        if callable(resposta):
            resposta = resposta(url, kwargs)
        if isinstance(resposta, Exception):
            raise resposta
        return resposta

    def chamada(self, method, url):
        return next(c for c in self.chamadas if c[0] == method and c[1] == url)


def _rotas_login(resposta_post=None):
    return {
        ('GET', API + 'oauth2/login'): _resposta(204, API + 'oauth2/login', location=AUTHORIZE),
        ('GET', AUTHORIZE): _resposta(200, PAGINA_LOGIN, texto=HTML_LOGIN),
        ('POST', POST_LOGIN): resposta_post or _resposta(302, POST_LOGIN, location=CALLBACK),
        ('GET', CALLBACK): _resposta(302, CALLBACK, location=AUTHORIZE_HTTP),
        ('GET', AUTHORIZE_HTTP): _resposta(302, AUTHORIZE_HTTP, location=AUTHORIZE_HTTPS),
        ('GET', AUTHORIZE_HTTPS): _resposta(302, AUTHORIZE_HTTPS, location=FINAL),
    }


def _rotas_contexto(current_user=None, perfis=None, vinculos=None):
    return {
        ('GET', API + 'usuario/currentUser'): _resposta(200, API, json_=current_user or CURRENT_USER),
        ('GET', API + 'perfilUsuario/listarPerfilPorDescricaoUsuarioEModulo'):
            _resposta(200, API, json_=PERFIS if perfis is None else perfis),
        ('GET', API + 'vinculoProfissionalService/listVinculoProfissionalAtivoPorDescricaoUsuario'):
            _resposta(200, API, json_=VINCULOS if vinculos is None else vinculos),
    }


def _cliente(rotas):
    sessao = SessaoFalsa(rotas)
    return ClienteSoulMV(USUARIO, SENHA, session=sessao, api=API), sessao


def _sem_segredos(texto):
    for segredo in (SENHA, TOKEN, TICKET):
        assert segredo not in texto


CONTEXTO = ContextoMV(user=14217, login='FULANO.TESTE', profile=57, company=711,
                      professional_bond=261621, id_unidade_executante=2147)


# --- login ----------------------------------------------------------------------------------------

def test_login_ok_segue_redirects_manualmente_e_extrai_token(caplog):
    caplog.set_level(logging.DEBUG)
    cliente, sessao = _cliente(_rotas_login())

    cliente.login()

    assert cliente.autenticado
    assert cliente._token == TOKEN
    metodos_urls = [(m, u) for m, u, _ in sessao.chamadas]
    assert metodos_urls == [
        ('GET', API + 'oauth2/login'), ('GET', AUTHORIZE), ('POST', POST_LOGIN),
        ('GET', CALLBACK), ('GET', AUTHORIZE_HTTP), ('GET', AUTHORIZE_HTTPS),
    ]
    assert sessao.chamada('GET', API + 'oauth2/login')[2]['allow_redirects'] is False
    assert sessao.chamada('GET', AUTHORIZE)[2]['allow_redirects'] is True
    post = sessao.chamada('POST', POST_LOGIN)[2]
    assert post['allow_redirects'] is False
    assert post['data'] == {'username': USUARIO, 'password': SENHA, 'execution': 'e1s1-EXECUCAO',
                            '_eventId': 'submit', 'geolocation': ''}
    assert all(c[2]['allow_redirects'] is False for c in sessao.chamadas[3:])
    _sem_segredos(caplog.text)
    _sem_segredos(repr(cliente))


def test_login_credencial_errada_cas_devolve_formulario():
    rotas = _rotas_login(_resposta(200, POST_LOGIN, texto=HTML_LOGIN_ERRO))
    cliente, _ = _cliente(rotas)

    with pytest.raises(ExtracaoError) as exc:
        cliente.login()

    assert str(exc.value) == 'falha de login no Soul MV'
    assert not cliente.autenticado


def test_login_sem_location_no_inicio():
    rotas = _rotas_login()
    rotas[('GET', API + 'oauth2/login')] = _resposta(200, API + 'oauth2/login', texto='ok')
    cliente, _ = _cliente(rotas)
    with pytest.raises(ExtracaoError, match='sem redirecionamento'):
        cliente.login()


def test_login_loop_de_redirects_e_interrompido():
    rotas = _rotas_login()
    rotas[('GET', AUTHORIZE_HTTPS)] = _resposta(302, AUTHORIZE_HTTPS, location=CALLBACK)
    cliente, _ = _cliente(rotas)
    with pytest.raises(ExtracaoError, match='excesso de redirecionamentos') as exc:
        cliente.login()
    _sem_segredos(str(exc.value))


def test_erro_de_rede_nao_vaza_url_com_ticket(caplog):
    rotas = _rotas_login()
    rotas[('GET', CALLBACK)] = requests.ConnectionError(f'falhou {CALLBACK} senha={SENHA}')
    cliente, _ = _cliente(rotas)

    with pytest.raises(ExtracaoError) as exc:
        cliente.login()

    assert 'ConnectionError' in str(exc.value)
    _sem_segredos(str(exc.value))
    _sem_segredos(caplog.text)
    assert exc.value.__cause__ is None and exc.value.__suppress_context__


@pytest.mark.parametrize('fragmento, esperado', [
    ('#access_token=AT-1&token_type=bearer&expires_in=28800', 'AT-1'),
    ('#/login?access_token=AT-2&token_type=bearer', 'AT-2'),
    ('#/login?state=x', None),
    ('', None),
])
def test_extrair_token_de_location(fragmento, esperado):
    assert extrair_token_de_location(f'{HOST}/consultas-exames/{fragmento}') == esperado


# --- contexto -------------------------------------------------------------------------------------

def _cliente_logado(rotas):
    cliente, sessao = _cliente(rotas)
    cliente._token = TOKEN
    return cliente, sessao


def test_descobrir_contexto_ok(caplog):
    caplog.set_level(logging.DEBUG)
    cliente, sessao = _cliente_logado(_rotas_contexto())

    contexto = cliente.descobrir_contexto()

    assert contexto == CONTEXTO
    assert cliente.contexto == contexto
    _, _, kwargs = sessao.chamada(
        'GET', API + 'vinculoProfissionalService/listVinculoProfissionalAtivoPorDescricaoUsuario')
    assert kwargs['params'] == {'descUsuario': 'FULANO.TESTE', 'descricao': '%%'}
    assert kwargs['headers']['Authorization'] == f'Bearer {TOKEN}'
    _, _, kwargs_perfis = sessao.chamada('GET', API + 'perfilUsuario/listarPerfilPorDescricaoUsuarioEModulo')
    assert kwargs_perfis['params'] is None
    assert 'PESSOA SINTETICA' not in caplog.text


def test_descobrir_contexto_perfil_inexistente():
    perfis = [p for p in PERFIS if p['id'] != 57]
    cliente, _ = _cliente_logado(_rotas_contexto(perfis=perfis))
    with pytest.raises(ExtracaoError, match="perfil 'COORDENADOR DE UNIDADE CMCE' não encontrado"):
        cliente.descobrir_contexto()
    assert cliente.contexto is None


def test_descobrir_contexto_unidade_executante_exige_nome_exato():
    vinculos = [v for v in VINCULOS if v['id'] != 260535]  # sobra só a variante "FUNDAO - RCS ..."
    cliente, _ = _cliente_logado(_rotas_contexto(vinculos=vinculos))
    with pytest.raises(ExtracaoError, match='unidade executante'):
        cliente.descobrir_contexto()


def test_descobrir_contexto_descricoes_configuraveis():
    rotas = _rotas_contexto()
    sessao = SessaoFalsa(rotas)
    cliente = ClienteSoulMV(USUARIO, SENHA, session=sessao, api=API, perfil='prestador cmce',
                            unidade_executante='FUNDAO - RCS SOLUCOES MEDICAS S/A')
    cliente._token = TOKEN
    contexto = cliente.descobrir_contexto()
    assert (contexto.profile, contexto.id_unidade_executante) == (68, 3001)


@pytest.mark.parametrize('flag', ['senhaExpirada', 'redefinirSenha'])
def test_descobrir_contexto_senha_expirada(flag):
    cliente, _ = _cliente_logado(_rotas_contexto(current_user={**CURRENT_USER, flag: True}))
    with pytest.raises(ExtracaoError, match='senha do Soul MV expirada/precisa ser redefinida'):
        cliente.descobrir_contexto()


def test_descobrir_contexto_token_recusado():
    rotas = _rotas_contexto()
    rotas[('GET', API + 'usuario/currentUser')] = _resposta(401, API, json_={'error': 'invalid_token'})
    cliente, _ = _cliente_logado(rotas)
    with pytest.raises(ExtracaoError, match='HTTP 401') as exc:
        cliente.descobrir_contexto()
    _sem_segredos(str(exc.value))


def test_normalizar_descricao():
    assert normalizar_descricao('  executante   cmce ') == normalizar_descricao('EXECUTANTE  CMCE') == 'EXECUTANTE CMCE'
    assert normalizar_descricao(None) == ''


# --- listagem ------------------------------------------------------------------------------------

def test_periodo_utc_meia_noite_de_sao_paulo():
    assert periodo_utc(date(2026, 11, 13)) == '2026-11-13T03:00:00.000Z'
    assert periodo_utc(date(2026, 11, 30)) == '2026-11-30T03:00:00.000Z'


def test_mvfor_profile_base64_de_json_compacto():
    valor = CONTEXTO.mvfor_profile()
    assert base64.b64decode(valor).decode() == '{"user":14217,"profile":57,"company":711,"professionalBond":261621}'


def test_listar_fluxo_completo_confere_params_e_headers():
    registros = [_registro(), _registro(idSolicitacaoProcedimento=8000002)]
    rotas = {**_rotas_login(), **_rotas_contexto(), ('GET', LISTAGEM): _resposta(200, LISTAGEM, json_=registros)}
    cliente, sessao = _cliente(rotas)

    resultado = cliente.listar(date(2026, 11, 13), date(2026, 11, 30))

    assert resultado == registros
    _, _, kwargs = sessao.chamada('GET', LISTAGEM)
    assert kwargs['params'] == {
        'idUnidadeExecutante': 2147,
        'tipoData': 1,
        'periodoInicial': '2026-11-13T03:00:00.000Z',
        'periodoFinal': '2026-11-30T03:00:00.000Z',
        'prioridade': 5,
        'idUnidadeSolicitante': 711,
        'idEstabelecimento': 711,
    }
    assert kwargs['timeout'] == 240
    assert kwargs['headers']['Authorization'] == f'Bearer {TOKEN}'
    perfil = json.loads(base64.b64decode(kwargs['headers']['MVFor-Profile']))
    assert perfil == {'user': 14217, 'profile': 57, 'company': 711, 'professionalBond': 261621}
    # query string final, como o requests a montaria
    preparada = requests.Request('GET', LISTAGEM, params=kwargs['params']).prepare()
    assert parse_qs(urlsplit(preparada.url).query)['periodoInicial'] == ['2026-11-13T03:00:00.000Z']


def test_listar_erro_http_nao_vaza_token(caplog):
    rotas = {('GET', LISTAGEM): _resposta(500, LISTAGEM, texto=f'erro interno {TOKEN}')}
    cliente, _ = _cliente_logado(rotas)
    cliente.contexto = CONTEXTO
    with pytest.raises(ExtracaoError, match='HTTP 500') as exc:
        cliente.listar(date(2026, 11, 13), date(2026, 11, 30))
    _sem_segredos(str(exc.value))
    _sem_segredos(caplog.text)


def test_listar_resposta_nao_lista():
    rotas = {('GET', LISTAGEM): _resposta(200, LISTAGEM, json_={'content': []})}
    cliente, _ = _cliente_logado(rotas)
    cliente.contexto = CONTEXTO
    with pytest.raises(ExtracaoError, match='não devolveu uma lista'):
        cliente.listar(date(2026, 11, 13), date(2026, 11, 30))


# --- CSV ------------------------------------------------------------------------------------------

def test_registros_para_csv_formato_do_front():
    conteudo = registros_para_csv([_registro()])

    assert conteudo.startswith(b'\xef\xbb\xbf')
    linhas = conteudo.decode('utf-8-sig').split('\r\n')
    assert linhas[0] == ','.join(COLUNAS_ESPERADAS) + ','
    assert linhas[1] == (
        '8000001,UNIDADE SINTETICA,1234567,700000000000001,00012345678,,FULANO DE TAL,01/02/1950,'
        '01/11/2026,"CONSULTA EM OFTALMOLOGIA, GLAUCOMA ADULTO",RCS SOLUCOES MEDICAS S/A,,'
        '13/11/2026 08:06,05/11/2026,5,,Sim,05/11/2026 09:00,OPERADOR SINTETICO,CONSULTA,NORMAL,'
    )
    assert linhas[2] == ''


def test_registros_para_csv_mesmo_cabecalho_do_export_da_tela():
    fixture = (Path(__file__).parent / 'fixtures' / 'soulmv_basico.csv').read_bytes()
    gerado = registros_para_csv([])
    assert gerado.splitlines()[0] == fixture.splitlines()[0]


def test_registros_para_csv_realizado_fora_da_rede_usa_data_atendimento():
    conteudo = registros_para_csv([_registro(flagRealizadoForaRede=True, dataAgenda='2026-11-20T10:00:00',
                                             dataAtendimento='2026-11-14T15:45:00')])
    resultado = ler_conteudo(conteudo)
    assert resultado.registros[0].data_agenda.strftime('%d/%m/%Y %H:%M') == '14/11/2026 15:45'


def test_registros_para_csv_ponta_a_ponta_com_leitor():
    registros = [
        _registro(),
        _registro(idSolicitacaoProcedimento=8000002, dataAgenda='2026-11-20T14:30:00.000'),
        _registro(idSolicitacaoProcedimento=8000003, idCidadao=7654321, cpf=None, numeroCartaoSus=None,
                  nomeCidadao='BELTRANA "BEL" SILVA', nomeCidadaoSocial='BEL', dataAgenda=None,
                  descricaMotivoProcedNaoRealiz='linha1\nlinha2, com vírgula'),
        _registro(idSolicitacaoProcedimento=8000004, idCidadao=None, cpf='12345678909',
                  nascimento='1980-12-31', nomeCidadao='CICLANO ÁGUA'),
    ]

    resultado = ler_conteudo(registros_para_csv(registros))

    assert resultado.rejeicoes == []
    assert [r.solicitacao for r in resultado.registros] == ['8000001', '8000002', '8000003', '8000004']
    r1, r2, r3, r4 = resultado.registros
    assert (r1.codigo_cidadao, r1.cpf, r1.cns) == ('1234567', '000.123.456-78', '700000000000001')
    assert r1.data_nascimento == date(1950, 2, 1)
    assert r1.item_agendamento == 'CONSULTA EM OFTALMOLOGIA, GLAUCOMA ADULTO'
    assert r1.data_agenda.strftime('%d/%m/%Y %H:%M') == '13/11/2026 08:06'
    assert r2.data_agenda.strftime('%d/%m/%Y %H:%M') == '20/11/2026 14:30'
    assert (r3.cpf, r3.cns, r3.data_agenda) == (None, None, None)
    assert (r3.nome, r3.nome_social) == ('BELTRANA "BEL" SILVA', 'BEL')
    assert (r4.codigo_cidadao, r4.cpf, r4.nome) == (None, '123.456.789-09', 'CICLANO ÁGUA')
    assert r4.data_nascimento == date(1980, 12, 31)


def test_registros_para_csv_data_com_fuso_e_convertida_para_sao_paulo():
    conteudo = registros_para_csv([_registro(dataAgenda='2026-11-13T11:06:00Z')])
    assert ler_conteudo(conteudo).registros[0].data_agenda.strftime('%H:%M') == '08:06'


def test_registros_para_csv_data_invalida_vira_vazio_sem_logar_valor(caplog):
    conteudo = registros_para_csv([_registro(nascimento='31/02/1950')])
    resultado = ler_conteudo(conteudo)
    assert [r.motivo for r in resultado.rejeicoes] == ['Data Nascimento vazia']
    assert '31/02/1950' not in caplog.text


# --- extrator ------------------------------------------------------------------------------------

class ClienteFalso:
    def __init__(self, registros):
        self.registros = registros
        self.periodos = []

    def listar(self, inicio, fim):
        self.periodos.append((inicio, fim))
        return self.registros


def test_extrator_http_grava_csv_no_destino(tmp_path):
    registros = [_registro()]
    cliente = ClienteFalso(registros)
    destino = tmp_path / 'inbox'

    caminho = ExtratorHttpSoulMV(cliente).extrair(date(2026, 11, 13), date(2026, 11, 30), destino)

    assert caminho.parent == destino
    assert caminho.name.startswith('soulmv_') and caminho.suffix == '.csv'
    assert caminho.read_bytes() == registros_para_csv(registros)
    assert list(destino.iterdir()) == [caminho]  # sem .part sobrando
    assert cliente.periodos == [(date(2026, 11, 13), date(2026, 11, 30))]


@pytest.mark.django_db
def test_extrator_http_seguido_do_importador(tmp_path):
    caminho = ExtratorHttpSoulMV(ClienteFalso([_registro(), _registro(idSolicitacaoProcedimento=8000002)])).extrair(
        date(2026, 11, 13), date(2026, 11, 30), tmp_path)

    execucao = importar_arquivo(caminho)

    assert execucao.status == ExecucaoImportacao.STATUS_SUCESSO
    assert execucao.linhas_rejeitadas == 0
    paciente = Paciente.objects.get(codigo_cidadao='1234567')
    assert (paciente.cpf, paciente.origem) == ('000.123.456-78', Paciente.ORIGEM_SOULMV)
    assert Agendamento.objects.filter(paciente=paciente).count() == 2


@pytest.mark.parametrize('usuario, senha', [('', SENHA), (USUARIO, ''), ('', '')])
def test_extrator_http_sem_credenciais(settings, usuario, senha):
    settings.SOULMV_USUARIO = usuario
    settings.SOULMV_SENHA = senha
    with pytest.raises(ImproperlyConfigured) as exc:
        obter_extrator('http')
    assert SENHA not in str(exc.value)


def test_obter_extrator_http_usa_settings(settings):
    settings.SOULMV_USUARIO = USUARIO
    settings.SOULMV_SENHA = SENHA
    settings.SOULMV_API_URL = API
    settings.SOULMV_PERFIL = 'PRESTADOR CMCE'
    extrator = obter_extrator('http')
    assert isinstance(extrator, ExtratorHttpSoulMV)
    cliente = extrator.cliente
    assert (cliente.usuario, cliente.api, cliente.perfil) == (USUARIO, API, 'PRESTADOR CMCE')
    assert cliente.unidade_executante == 'RCS SOLUCOES MEDICAS S/A'
    _sem_segredos(repr(cliente))
