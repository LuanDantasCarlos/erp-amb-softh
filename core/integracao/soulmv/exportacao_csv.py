"""Gera, a partir do JSON da listagem do Soul MV, o mesmo CSV que o front exporta.

Reproduz `corpoExportaCsv` + `toCsv` do chunk 80 do front (spec, "Fase 2 — mapeamento estático"):
BOM UTF-8, as 21 colunas de `leitor.COLUNAS_ESPERADAS`, aspas só quando necessário e vírgula
sobrando no fim de cada linha. Assim o leitor, a idempotência por sha256 e a auditoria continuam iguais.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any, Callable, Iterable, Mapping
from zoneinfo import ZoneInfo

from .leitor import COLUNAS_ESPERADAS

logger = logging.getLogger(__name__)

FUSO_MV = ZoneInfo('America/Sao_Paulo')
BOM = '﻿'
FIM_LINHA = '\r\n'

_RE_DATA = re.compile(
    r'^\s*(\d{4})-(\d{2})-(\d{2})'
    r'(?:[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?)?'
    r'\s*(Z|[+-]\d{2}:?\d{2})?\s*$'
)


def _parse_data(valor: Any) -> datetime | None:
    """`AAAA-MM-DD[THH:MM[:SS[.fff]]][Z|±HH:MM]` → datetime no horário local do MV (naive)."""
    if valor is None or valor == '':
        return None
    m = _RE_DATA.match(str(valor))
    if not m:
        return None
    ano, mes, dia, hora, minuto, segundo, fuso = m.groups()
    try:
        dt = datetime(int(ano), int(mes), int(dia), int(hora or 0), int(minuto or 0), int(segundo or 0))
    except ValueError:
        return None
    if fuso:
        texto_fuso = '+00:00' if fuso == 'Z' else fuso
        if ':' not in texto_fuso:
            texto_fuso = f'{texto_fuso[:3]}:{texto_fuso[3:]}'
        dt = datetime.fromisoformat(dt.isoformat() + texto_fuso).astimezone(FUSO_MV).replace(tzinfo=None)
    return dt


def _formatar(valor: Any, formato: str, campo: str) -> str:
    dt = _parse_data(valor)
    if dt is None:
        if valor not in (None, ''):
            # Sem o valor no log (LGPD): só o nome do campo.
            logger.warning('Soul MV: data em formato inesperado no campo %s', campo)
        return ''
    return dt.strftime(formato)


def _data(campo: str) -> Callable[[Mapping[str, Any]], str]:
    return lambda r: _formatar(r.get(campo), '%d/%m/%Y', campo)


def _data_hora(campo: str) -> Callable[[Mapping[str, Any]], str]:
    return lambda r: _formatar(r.get(campo), '%d/%m/%Y %H:%M', campo)


def _texto(campo: str) -> Callable[[Mapping[str, Any]], str]:
    return lambda r: _str(r.get(campo))


def _str(valor: Any) -> str:
    if valor is None:
        return ''
    if isinstance(valor, bool):
        return 'Sim' if valor else 'Não'
    return str(valor).strip()


def _data_agenda(r: Mapping[str, Any]) -> str:
    campo = 'dataAtendimento' if r.get('flagRealizadoForaRede') else 'dataAgenda'
    return _formatar(r.get(campo), '%d/%m/%Y %H:%M', campo)


# Ordem idêntica a COLUNAS_ESPERADAS (validada no import do módulo).
COLUNAS: tuple[tuple[str, Callable[[Mapping[str, Any]], str]], ...] = (
    ('Solicitação', _texto('idSolicitacaoProcedimento')),
    ('Unidade solicitante', _texto('nomeUnidadeSolicitante')),
    ('Código cidadão', _texto('idCidadao')),
    ('CNS do cidadão', _texto('numeroCartaoSus')),
    ('CPF do cidadão', _texto('cpf')),
    ('Nome social', _texto('nomeCidadaoSocial')),
    ('Nome do cidadão', _texto('nomeCidadao')),
    ('Data Nascimento', _data('nascimento')),
    ('Data da solicitação', _data('dataSolicitacao')),
    ('Item agendamento', _texto('descricaoItemAgendamento')),
    # Colunas abaixo não são importadas; o leitor as ignora. Preenchidas com o que vier.
    ('Unidade executante', _texto('nomeUnidadeExecutante')),
    ('Profissional executante', _texto('nomeProfExecPorSit')),
    ('Data da agenda', _data_agenda),
    ('Data de marcação', _data('dataMarcacao')),
    ('Situação', _texto('situacao')),
    ('Motivo', _texto('descricaMotivoProcedNaoRealiz')),
    ('Emissão guia', _texto('flagEmissaoGuia')),
    ('Data da marcação original', _data_hora('dataMarcacaoOriginal')),
    ('Marcado por', _texto('marcadoPor')),
    ('T. solicitação', _texto('tipoSolicitacao')),
    ('Prioridade', _texto('descricaoPrioridade')),
)
assert tuple(nome for nome, _ in COLUNAS) == COLUNAS_ESPERADAS


def _celula(valor: str) -> str:
    """Aspas só quando necessário, como o front (vírgula). Também protege aspas e quebras de linha,
    que no front quebrariam o arquivo; aspas internas são duplicadas (RFC 4180)."""
    if any(ch in valor for ch in (',', '"', '\n', '\r')):
        return '"' + valor.replace('"', '""') + '"'
    return valor


def _linha(valores: Iterable[str]) -> str:
    # Vírgula sobrando no fim, igual ao export da tela.
    return ''.join(_celula(v) + ',' for v in valores)


def registros_para_csv(registros: Iterable[Mapping[str, Any]]) -> bytes:
    """Converte os registros JSON da listagem no CSV da tela (bytes UTF-8 com BOM)."""
    linhas = [_linha(nome for nome, _ in COLUNAS)]
    for registro in registros:
        linhas.append(_linha(extrair(registro) for _, extrair in COLUNAS))
    return (BOM + FIM_LINHA.join(linhas) + FIM_LINHA).encode('utf-8')
