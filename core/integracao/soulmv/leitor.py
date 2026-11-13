"""Leitura e validação do CSV exportado pela Central de Marcação do Soul MV (spec §3)."""
from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

COLUNAS_ESPERADAS: tuple[str, ...] = (
    'Solicitação',
    'Unidade solicitante',
    'Código cidadão',
    'CNS do cidadão',
    'CPF do cidadão',
    'Nome social',
    'Nome do cidadão',
    'Data Nascimento',
    'Data da solicitação',
    'Item agendamento',
    'Unidade executante',
    'Profissional executante',
    'Data da agenda',
    'Data de marcação',
    'Situação',
    'Motivo',
    'Emissão guia',
    'Data da marcação original',
    'Marcado por',
    'T. solicitação',
    'Prioridade',
)

ENCODINGS: tuple[str, ...] = ('utf-8-sig', 'cp1252')

MAX_NOME = 255
MAX_ITEM = 255
MAX_SOLICITACAO = 20
MAX_CODIGO_CIDADAO = 20
MAX_CNS = 15


class LayoutInvalidoError(ValueError):
    """Cabeçalho divergente do layout esperado: a importação deve abortar sem gravar."""


class LinhaInvalidaError(ValueError):
    """Linha que não pode ser importada; o motivo vai para o log da execução."""


@dataclass(frozen=True)
class RegistroSoulMV:
    linha: int
    solicitacao: str
    codigo_cidadao: str | None
    cns: str | None
    cpf: str | None
    nome_social: str | None
    nome: str
    data_nascimento: date
    item_agendamento: str
    data_agenda: datetime | None  # naive, horário local do Soul MV


@dataclass(frozen=True)
class Rejeicao:
    linha: int
    motivo: str
    solicitacao: str = ''

    def as_dict(self) -> dict[str, object]:
        return {'linha': self.linha, 'solicitacao': self.solicitacao, 'motivo': self.motivo}


@dataclass
class ResultadoLeitura:
    sha256: str
    encoding: str
    registros: list[RegistroSoulMV] = field(default_factory=list)
    rejeicoes: list[Rejeicao] = field(default_factory=list)

    @property
    def linhas_lidas(self) -> int:
        return len(self.registros) + len(self.rejeicoes)


def sha256_bytes(conteudo: bytes) -> str:
    return hashlib.sha256(conteudo).hexdigest()


def decodificar(conteudo: bytes) -> tuple[str, str]:
    for encoding in ENCODINGS:
        try:
            return conteudo.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise LayoutInvalidoError('Não foi possível decodificar o arquivo (utf-8 / cp1252).')


def _remover_colunas_vazias_finais(valores: list[str]) -> list[str]:
    while valores and valores[-1].strip() == '':
        valores = valores[:-1]
    return valores


def validar_cabecalho(cabecalho: list[str]) -> None:
    colunas = [c.strip() for c in _remover_colunas_vazias_finais(cabecalho)]
    if tuple(colunas) != COLUNAS_ESPERADAS:
        faltando = [c for c in COLUNAS_ESPERADAS if c not in colunas]
        sobrando = [c for c in colunas if c not in COLUNAS_ESPERADAS]
        detalhe = []
        if faltando:
            detalhe.append(f'faltando: {faltando}')
        if sobrando:
            detalhe.append(f'inesperadas: {sobrando}')
        if not detalhe:
            detalhe.append('ordem das colunas divergente')
        raise LayoutInvalidoError('Cabeçalho do CSV divergente do layout Soul MV (' + '; '.join(detalhe) + ').')


def normalizar_cpf(valor: str) -> str | None:
    digitos = ''.join(ch for ch in valor if ch.isdigit())
    if not digitos:
        return None
    if len(digitos) > 11:
        raise LinhaInvalidaError('CPF com mais de 11 dígitos')
    digitos = digitos.zfill(11)
    return f'{digitos[:3]}.{digitos[3:6]}.{digitos[6:9]}-{digitos[9:]}'


def normalizar_cns(valor: str) -> str | None:
    digitos = ''.join(ch for ch in valor if ch.isdigit())
    if not digitos:
        return None
    if len(digitos) > MAX_CNS:
        raise LinhaInvalidaError('CNS com mais de 15 dígitos')
    return digitos


def parse_data(valor: str, coluna: str) -> date:
    try:
        return datetime.strptime(valor, '%d/%m/%Y').date()
    except ValueError:
        raise LinhaInvalidaError(f'{coluna} inválida') from None


def parse_data_hora(valor: str, coluna: str) -> datetime | None:
    if not valor:
        return None
    for formato in ('%d/%m/%Y %H:%M', '%d/%m/%Y %H:%M:%S', '%d/%m/%Y'):
        try:
            return datetime.strptime(valor, formato)
        except ValueError:
            continue
    raise LinhaInvalidaError(f'{coluna} inválida')


def _texto(valor: str, coluna: str, max_len: int, obrigatorio: bool = False) -> str | None:
    valor = valor.strip()
    if not valor:
        if obrigatorio:
            raise LinhaInvalidaError(f'{coluna} vazio')
        return None
    if len(valor) > max_len:
        raise LinhaInvalidaError(f'{coluna} excede {max_len} caracteres')
    return valor


def converter_linha(numero: int, dados: dict[str, str]) -> RegistroSoulMV:
    solicitacao = _texto(dados['Solicitação'], 'Solicitação', MAX_SOLICITACAO, obrigatorio=True)
    codigo_cidadao = _texto(dados['Código cidadão'], 'Código cidadão', MAX_CODIGO_CIDADAO)
    cpf = normalizar_cpf(dados['CPF do cidadão'])
    if codigo_cidadao is None and cpf is None:
        raise LinhaInvalidaError('sem Código cidadão e sem CPF')
    nome = _texto(dados['Nome do cidadão'], 'Nome do cidadão', MAX_NOME, obrigatorio=True)
    nascimento_txt = dados['Data Nascimento'].strip()
    if not nascimento_txt:
        raise LinhaInvalidaError('Data Nascimento vazia')
    return RegistroSoulMV(
        linha=numero,
        solicitacao=solicitacao,  # type: ignore[arg-type]
        codigo_cidadao=codigo_cidadao,
        cns=normalizar_cns(dados['CNS do cidadão']),
        cpf=cpf,
        nome_social=_texto(dados['Nome social'], 'Nome social', MAX_NOME),
        nome=nome,  # type: ignore[arg-type]
        data_nascimento=parse_data(nascimento_txt, 'Data Nascimento'),
        item_agendamento=_texto(dados['Item agendamento'], 'Item agendamento', MAX_ITEM) or '',
        data_agenda=parse_data_hora(dados['Data da agenda'].strip(), 'Data da agenda'),
    )


def ler_conteudo(conteudo: bytes) -> ResultadoLeitura:
    """Converte o CSV em registros validados. Levanta LayoutInvalidoError se o cabeçalho divergir."""
    texto, encoding = decodificar(conteudo)
    resultado = ResultadoLeitura(sha256=sha256_bytes(conteudo), encoding=encoding)

    leitor = csv.reader(io.StringIO(texto, newline=''), delimiter=',')
    try:
        cabecalho = next(leitor)
    except StopIteration:
        raise LayoutInvalidoError('Arquivo vazio (sem cabeçalho).') from None
    validar_cabecalho(cabecalho)
    total_colunas = len(COLUNAS_ESPERADAS)

    for numero, valores in enumerate(leitor, start=2):
        if not any(v.strip() for v in valores):
            continue
        if len(valores) > total_colunas:
            valores = valores[:total_colunas] + _remover_colunas_vazias_finais(valores[total_colunas:])
        if len(valores) != total_colunas:
            resultado.rejeicoes.append(
                Rejeicao(numero, f'quantidade de colunas inválida ({len(valores)}, esperado {total_colunas})')
            )
            continue
        dados = dict(zip(COLUNAS_ESPERADAS, valores))
        try:
            resultado.registros.append(converter_linha(numero, dados))
        except LinhaInvalidaError as exc:
            resultado.rejeicoes.append(Rejeicao(numero, str(exc), dados['Solicitação'].strip()))
    return resultado


def ler_arquivo(caminho: str | Path) -> ResultadoLeitura:
    return ler_conteudo(Path(caminho).read_bytes())
