"""Cliente HTTP do Soul MV Regulação (Central de Marcação), sem navegador.

Fluxo confirmado no servidor em 13/11/2026 (spec, "Fase 2 — spike com login — CONFIRMADO"):
1. `GET {API}oauth2/login` sem seguir redirect → 204 + `Location` (authorize do CAS);
2. `GET <Location>` seguindo redirects → página de login do CAS;
3. `POST` do formulário sem seguir redirects; os 302 são seguidos à mão até o `Location` trazer
   `#access_token=AT-…`;
4. Daí em diante: `Authorization: Bearer <token>` e, na listagem, `MVFor-Profile: base64(JSON)`.

Senha, token e ticket do CAS nunca entram em mensagens de erro nem em log.
"""
from __future__ import annotations

import base64
import json
import logging
import os
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, urljoin, urlsplit
from zoneinfo import ZoneInfo

import requests

from .exportacao_csv import registros_para_csv
from .extrator import ExtracaoError

logger = logging.getLogger(__name__)

API_PADRAO = 'https://regulacao.saude.es.gov.br/consultas-exames/api/'
FUSO_MV = ZoneInfo('America/Sao_Paulo')
FORMATO_PERIODO = '%Y-%m-%dT%H:%M:%S.000Z'
TIPO_DATA_AGENDAMENTO = 1
PRIORIDADE_TODAS = 5
MAX_REDIRECTS = 10
TIMEOUT_PADRAO = 30
TIMEOUT_LISTAGEM = 240
USER_AGENT = 'erp-ambulatorial/soulmv'

PERFIL_PADRAO = 'COORDENADOR DE UNIDADE CMCE'
UNIDADE_SOLICITANTE_PADRAO = 'NUCLEO ESPECIAL DE REGULACAO DE CONSULTAS E EXAMES'
UNIDADE_EXECUTANTE_PADRAO = 'RCS SOLUCOES MEDICAS S/A'


def normalizar_descricao(valor: Any) -> str:
    """Compara descrições do MV ignorando caixa e espaços repetidos ("EXECUTANTE  CMCE")."""
    return ' '.join(str(valor or '').split()).upper()


def periodo_utc(dia: date) -> str:
    """00:00 de `dia` em America/Sao_Paulo, em UTC, como o `Date.toISOString()` do front."""
    local = datetime.combine(dia, time(0, 0), tzinfo=FUSO_MV)
    return local.astimezone(timezone.utc).strftime(FORMATO_PERIODO)


@dataclass(frozen=True)
class ContextoMV:
    user: int
    login: str
    profile: int
    company: int
    professional_bond: int
    id_unidade_executante: int

    def mvfor_profile(self) -> str:
        """Valor do header MVFor-Profile: base64 do JSON compacto (`getProfileToken` do front)."""
        dados = {
            'user': self.user,
            'profile': self.profile,
            'company': self.company,
            'professionalBond': self.professional_bond,
        }
        compacto = json.dumps(dados, separators=(',', ':'))
        return base64.b64encode(compacto.encode('utf-8')).decode('ascii')


@dataclass(frozen=True)
class FormularioLogin:
    action: str
    campos: dict[str, str]


class _ParserFormularioCAS(HTMLParser):
    """Extrai o formulário de login do CAS (o que tem campo `password`)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.formularios: list[tuple[str, dict[str, str], bool]] = []
        self._atual: Optional[tuple[str, dict[str, str], list[bool]]] = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        a = {k.lower(): (v or '') for k, v in attrs}
        if tag == 'form':
            self._atual = (a.get('action', ''), {}, [False])
        elif tag == 'input' and self._atual is not None:
            nome = a.get('name')
            if not nome:
                return
            tipo = a.get('type', 'text').lower()
            if tipo == 'password':
                self._atual[2][0] = True
            if tipo in ('checkbox', 'radio') and 'checked' not in a:
                return
            self._atual[1][nome] = a.get('value', '')

    def handle_endtag(self, tag: str) -> None:
        if tag == 'form' and self._atual is not None:
            action, campos, tem_senha = self._atual
            self.formularios.append((action, campos, tem_senha[0]))
            self._atual = None


def extrair_formulario_login(html: str) -> Optional[FormularioLogin]:
    parser = _ParserFormularioCAS()
    parser.feed(html)
    parser.close()
    for action, campos, tem_senha in parser.formularios:
        if tem_senha or 'execution' in campos:
            return FormularioLogin(action=action or 'login', campos=campos)
    return None


def extrair_token_de_location(location: str) -> Optional[str]:
    """Token do fragmento: `…/#access_token=AT-…&…` ou `…/#/login?access_token=AT-…`."""
    fragmento = urlsplit(location).fragment
    pos = fragmento.find('access_token=')
    if pos < 0:
        return None
    valores = parse_qs(fragmento[pos:]).get('access_token')
    return valores[0] if valores and valores[0] else None


class ClienteSoulMV:
    def __init__(
        self,
        usuario: str,
        senha: str,
        session: Optional[requests.Session] = None,
        timeout: float = TIMEOUT_PADRAO,
        timeout_listagem: float = TIMEOUT_LISTAGEM,
        api: str = API_PADRAO,
        perfil: str = PERFIL_PADRAO,
        unidade_solicitante: str = UNIDADE_SOLICITANTE_PADRAO,
        unidade_executante: str = UNIDADE_EXECUTANTE_PADRAO,
    ) -> None:
        self.usuario = usuario
        self._senha = senha
        self.session = session if session is not None else requests.Session()
        self.session.headers.setdefault('User-Agent', USER_AGENT)
        self.timeout = timeout
        self.timeout_listagem = timeout_listagem
        self.api = api if api.endswith('/') else api + '/'
        self.perfil = perfil
        self.unidade_solicitante = unidade_solicitante
        self.unidade_executante = unidade_executante
        self._token: Optional[str] = None
        self.contexto: Optional[ContextoMV] = None

    def __repr__(self) -> str:  # nunca expõe senha/token
        return f'ClienteSoulMV(usuario={self.usuario!r}, autenticado={self._token is not None})'

    @property
    def autenticado(self) -> bool:
        return self._token is not None

    # --- HTTP ---------------------------------------------------------------------------------

    def _requisitar(self, metodo: str, url: str, etapa: str, **kwargs: Any) -> requests.Response:
        kwargs.setdefault('timeout', self.timeout)
        try:
            return self.session.request(metodo, url, **kwargs)
        except requests.RequestException as exc:
            # str(exc) pode conter URL com ticket do CAS: só o tipo da exceção.
            raise ExtracaoError(f'Soul MV: erro de rede em {etapa} ({type(exc).__name__})') from None

    def _cabecalhos_api(self, com_perfil: bool = False) -> dict[str, str]:
        if self._token is None:
            raise ExtracaoError('Soul MV: login não realizado')
        cabecalhos = {'Authorization': f'Bearer {self._token}', 'Accept': 'application/json'}
        if com_perfil:
            if self.contexto is None:
                raise ExtracaoError('Soul MV: contexto (perfil/vínculo) não descoberto')
            cabecalhos['MVFor-Profile'] = self.contexto.mvfor_profile()
        return cabecalhos

    def _get_json(self, caminho: str, etapa: str, params: Optional[dict[str, Any]] = None,
                  com_perfil: bool = False, timeout: Optional[float] = None) -> Any:
        resposta = self._requisitar(
            'GET', self.api + caminho, etapa,
            params=params, headers=self._cabecalhos_api(com_perfil),
            timeout=timeout or self.timeout, allow_redirects=False,
        )
        if resposta.status_code in (401, 403):
            raise ExtracaoError(f'Soul MV: acesso negado em {etapa} (HTTP {resposta.status_code})')
        if resposta.status_code != 200:
            raise ExtracaoError(f'Soul MV: {etapa} respondeu HTTP {resposta.status_code}')
        try:
            return resposta.json()
        except ValueError:
            raise ExtracaoError(f'Soul MV: {etapa} não devolveu JSON') from None

    # --- Login --------------------------------------------------------------------------------

    def login(self) -> None:
        inicio = self._requisitar('GET', self.api + 'oauth2/login', 'login (início)', allow_redirects=False)
        authorize = inicio.headers.get('Location')
        if not authorize:
            raise ExtracaoError(f'Soul MV: oauth2/login sem redirecionamento (HTTP {inicio.status_code})')

        pagina = self._requisitar('GET', urljoin(inicio.url or self.api, authorize), 'login (CAS)',
                                  allow_redirects=True)
        if pagina.status_code != 200:
            raise ExtracaoError(f'Soul MV: página de login do CAS respondeu HTTP {pagina.status_code}')
        formulario = extrair_formulario_login(pagina.text)
        if formulario is None:
            raise ExtracaoError('Soul MV: formulário de login do CAS não encontrado')

        dados = dict(formulario.campos)
        dados.update({'username': self.usuario, 'password': self._senha, '_eventId': 'submit'})
        dados.setdefault('geolocation', '')
        resposta = self._requisitar('POST', urljoin(pagina.url, formulario.action), 'login (credenciais)',
                                    data=dados, allow_redirects=False)

        for _ in range(MAX_REDIRECTS):
            if resposta.status_code not in (301, 302, 303, 307, 308):
                break
            location = resposta.headers.get('Location', '')
            token = extrair_token_de_location(location)
            if token:
                self._token = token
                logger.info('Soul MV: login realizado')
                return
            if not location:
                break
            resposta = self._requisitar('GET', urljoin(resposta.url, location), 'login (redirecionamento)',
                                        allow_redirects=False)
        else:
            raise ExtracaoError('Soul MV: excesso de redirecionamentos no login')

        if resposta.status_code == 200 and extrair_formulario_login(resposta.text) is not None:
            # O CAS devolve o formulário de novo quando a credencial é recusada.
            raise ExtracaoError('falha de login no Soul MV')
        raise ExtracaoError(f'Soul MV: login sem access_token (HTTP {resposta.status_code})')

    # --- Contexto -----------------------------------------------------------------------------

    def descobrir_contexto(self) -> ContextoMV:
        usuario = self._get_json('usuario/currentUser', 'usuario/currentUser')
        if not isinstance(usuario, dict) or 'id' not in usuario or not usuario.get('login'):
            raise ExtracaoError('Soul MV: resposta inesperada de usuario/currentUser')
        if usuario.get('senhaExpirada') or usuario.get('redefinirSenha'):
            raise ExtracaoError('senha do Soul MV expirada/precisa ser redefinida')
        login = str(usuario['login'])

        perfis = self._get_json('perfilUsuario/listarPerfilPorDescricaoUsuarioEModulo', 'lista de perfis')
        perfil = self._procurar(perfis, self.perfil, lambda p: p.get('descricao'), 'perfil')

        vinculos = self._get_json(
            'vinculoProfissionalService/listVinculoProfissionalAtivoPorDescricaoUsuario',
            'lista de vínculos', params={'descUsuario': login, 'descricao': '%%'},
        )

        def nome_estabelecimento(v: dict) -> Any:
            return (v.get('estabelecimento') or {}).get('nomeFantasia')

        solicitante = self._procurar(vinculos, self.unidade_solicitante, nome_estabelecimento, 'unidade solicitante')
        executante = self._procurar(vinculos, self.unidade_executante, nome_estabelecimento, 'unidade executante')

        try:
            contexto = ContextoMV(
                user=int(usuario['id']),
                login=login,
                profile=int(perfil['id']),
                company=int(solicitante['estabelecimento']['id']),
                professional_bond=int(solicitante['id']),
                id_unidade_executante=int(executante['estabelecimento']['id']),
            )
        except (KeyError, TypeError, ValueError):
            raise ExtracaoError('Soul MV: ids ausentes no perfil/vínculo encontrado') from None
        self.contexto = contexto
        logger.info(
            'Soul MV: contexto user=%s profile=%s company=%s bond=%s executante=%s',
            contexto.user, contexto.profile, contexto.company, contexto.professional_bond,
            contexto.id_unidade_executante,
        )
        return contexto

    @staticmethod
    def _procurar(itens: Any, descricao: str, chave: Any, rotulo: str) -> dict:
        if not isinstance(itens, list):
            raise ExtracaoError(f'Soul MV: resposta inesperada ao listar {rotulo}')
        alvo = normalizar_descricao(descricao)
        for item in itens:
            if isinstance(item, dict) and normalizar_descricao(chave(item)) == alvo:
                return item
        raise ExtracaoError(f'Soul MV: {rotulo} {descricao!r} não encontrado(a) para a conta')

    # --- Listagem -----------------------------------------------------------------------------

    def parametros_listagem(self, inicio: date, fim: date) -> dict[str, Any]:
        if self.contexto is None:
            raise ExtracaoError('Soul MV: contexto (perfil/vínculo) não descoberto')
        return {
            'idUnidadeExecutante': self.contexto.id_unidade_executante,
            'tipoData': TIPO_DATA_AGENDAMENTO,
            'periodoInicial': periodo_utc(inicio),
            'periodoFinal': periodo_utc(fim),
            'prioridade': PRIORIDADE_TODAS,
            'idUnidadeSolicitante': self.contexto.company,
            'idEstabelecimento': self.contexto.company,
        }

    def listar(self, inicio: date, fim: date) -> list[dict]:
        if self._token is None:
            self.login()
        if self.contexto is None:
            self.descobrir_contexto()
        registros = self._get_json(
            'solicitacao-procedimento/solicitacoes-consulta-regulador-com-vinculos', 'listagem',
            params=self.parametros_listagem(inicio, fim), com_perfil=True, timeout=self.timeout_listagem,
        )
        if not isinstance(registros, list):
            raise ExtracaoError('Soul MV: listagem não devolveu uma lista')
        logger.info('Soul MV: listagem %s → %s com %d registros', inicio, fim, len(registros))
        return registros


class ExtratorHttpSoulMV:
    """Extrator do job (`SOULMV_EXTRATOR=http`): login → contexto → listagem → CSV no inbox."""

    def __init__(self, cliente: Optional[ClienteSoulMV] = None) -> None:
        if cliente is None:
            from django.conf import settings
            from django.core.exceptions import ImproperlyConfigured

            usuario = getattr(settings, 'SOULMV_USUARIO', '') or ''
            senha = getattr(settings, 'SOULMV_SENHA', '') or ''
            if not usuario or not senha:
                raise ImproperlyConfigured('SOULMV_USUARIO e SOULMV_SENHA são obrigatórios para SOULMV_EXTRATOR=http.')
            cliente = ClienteSoulMV(
                usuario,
                senha,
                api=settings.SOULMV_API_URL,
                perfil=settings.SOULMV_PERFIL,
                unidade_solicitante=settings.SOULMV_UNIDADE_SOLICITANTE,
                unidade_executante=settings.SOULMV_UNIDADE_EXECUTANTE,
            )
        self.cliente = cliente

    def extrair(self, inicio: date, fim: date, destino: Path) -> Path:
        registros = self.cliente.listar(inicio, fim)
        conteudo = registros_para_csv(registros)
        destino = Path(destino)
        destino.mkdir(parents=True, exist_ok=True)
        carimbo = datetime.now(FUSO_MV).strftime('%Y%m%d%H%M%S')
        caminho = destino / f'soulmv_{carimbo}.csv'
        temporario = caminho.with_suffix('.csv.part')
        # 0o600: o CSV tem dados pessoais (LGPD). Grava em .part e renomeia (o job nunca lê arquivo pela metade).
        fd = os.open(temporario, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(fd, 'wb') as arquivo:
                arquivo.write(conteudo)
            os.replace(temporario, caminho)
        except BaseException:
            temporario.unlink(missing_ok=True)
            raise
        logger.info('Soul MV: CSV gravado (%d registros, %d bytes)', len(registros), len(conteudo))
        return caminho
