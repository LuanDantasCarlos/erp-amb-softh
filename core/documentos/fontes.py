"""Fontes de valor dos campos (`CampoTemplateDocumento.atributo_paciente`).

Chave com prefixo de fonte (`paciente.`, `medico.`, `estabelecimento.`, `atendimento.`, `sistema.`).
Sem prefixo = atributo do paciente, que é o formato dos templates antigos.
Ver docs/specs/templates-oftalmologia.md §3.4.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Optional

from django.conf import settings
from django.utils import timezone

FONTES = ('paciente', 'medico', 'estabelecimento', 'atendimento', 'sistema')


def estabelecimento_padrao() -> dict[str, str]:
    return {
        'nome': settings.ESTABELECIMENTO_NOME,
        'cnes': settings.ESTABELECIMENTO_CNES,
        'nucleo': settings.ESTABELECIMENTO_NUCLEO,
        'unidade': settings.ESTABELECIMENTO_UNIDADE,
    }


@dataclass
class ContextoDocumento:
    paciente: Any = None
    medico: Any = None
    data_atendimento: Optional[date] = None
    hoje: Optional[date] = None
    estabelecimento: dict[str, str] = field(default_factory=estabelecimento_padrao)

    @property
    def data_de_hoje(self) -> date:
        return self.hoje or timezone.localdate()


def formatar(valor: Any) -> str:
    """Converte para o texto impresso: datas em dd/mm/aaaa e None como vazio."""
    if valor is None:
        return ''
    if isinstance(valor, datetime):
        if timezone.is_aware(valor):
            valor = timezone.localtime(valor)
        return valor.strftime('%d/%m/%Y')
    if isinstance(valor, date):
        return valor.strftime('%d/%m/%Y')
    return str(valor)


def separar_chave(chave: str) -> tuple[str, str]:
    """'medico.nome' → ('medico', 'nome'); 'nome' → ('paciente', 'nome')."""
    chave = (chave or '').strip()
    if '.' in chave:
        fonte, _, atributo = chave.partition('.')
        return fonte, atributo
    return 'paciente', chave


def _paciente(atributo: str, paciente: Any) -> Any:
    if paciente is None:
        return None
    if atributo == 'nascimento_curto':
        nascimento = getattr(paciente, 'data_nascimento', None)
        return nascimento.strftime('%d/%m/%y') if nascimento else None
    if atributo == 'telefone_contato':
        return getattr(paciente, 'celular', None) or getattr(paciente, 'telefone', None)
    return getattr(paciente, atributo, None)


def _medico(atributo: str, medico: Any) -> Any:
    if medico is None:
        return None
    return getattr(medico, atributo, None)


def _atendimento(atributo: str, contexto: ContextoDocumento) -> Any:
    data = contexto.data_atendimento
    if data is None:
        return None
    if atributo == 'data':
        return data
    if atributo == 'mes_ano':
        return data.strftime('%m/%Y')
    return None


def resolver_valor(chave: Optional[str], contexto: ContextoDocumento) -> str:
    """Valor automático de um campo. Chave desconhecida ou sem dado resulta em ''."""
    if not chave:
        return ''
    fonte, atributo = separar_chave(chave)
    if not atributo or atributo.startswith('_'):
        return ''
    if fonte == 'paciente':
        valor = _paciente(atributo, contexto.paciente)
    elif fonte == 'medico':
        valor = _medico(atributo, contexto.medico)
    elif fonte == 'estabelecimento':
        valor = (contexto.estabelecimento or {}).get(atributo)
    elif fonte == 'atendimento':
        valor = _atendimento(atributo, contexto)
    elif fonte == 'sistema':
        valor = contexto.data_de_hoje if atributo == 'hoje' else None
    else:
        valor = None
    if callable(valor):
        return ''
    return formatar(valor)


def usa_fonte(campos, fonte: str) -> bool:
    """True se algum campo do template usa a fonte (ex.: 'medico')."""
    return any(separar_chave(c.atributo_paciente)[0] == fonte for c in campos if c.atributo_paciente)
