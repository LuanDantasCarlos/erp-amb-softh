"""Importação do catálogo de procedimentos do SIGTAP (CSV `codigo,nome,grupo,instrumentos`)."""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from pathlib import Path

from django.db import transaction

from core.models import Procedimento

CSV_PADRAO = Path(__file__).resolve().parent / 'dados' / 'procedimentos_oftalmo_sigtap_202611.csv'
COLUNAS = ('codigo', 'nome', 'grupo', 'instrumentos')
RE_CODIGO = re.compile(r'^\d{2}\.\d{2}\.\d{2}\.\d{3}-\d$')


class CatalogoInvalidoError(ValueError):
    pass


@dataclass
class ResultadoSigtap:
    criados: int = 0
    atualizados: int = 0
    inalterados: int = 0
    rejeitados: list[str] = field(default_factory=list)


def formatar_codigo(valor: str) -> str:
    """'0405010079' ou '04.05.01.007-9' → '04.05.01.007-9'."""
    digitos = ''.join(ch for ch in valor if ch.isdigit())
    if len(digitos) != 10:
        return valor.strip()
    return f'{digitos[:2]}.{digitos[2:4]}.{digitos[4:6]}.{digitos[6:9]}-{digitos[9]}'


def importar_procedimentos(caminho: Path = CSV_PADRAO) -> ResultadoSigtap:
    """Upsert por código. Não apaga nem desativa procedimentos ausentes do CSV."""
    texto = Path(caminho).read_bytes().decode('utf-8-sig')
    leitor = csv.DictReader(io.StringIO(texto, newline=''))
    if tuple(c.strip() for c in (leitor.fieldnames or ())) != COLUNAS:
        raise CatalogoInvalidoError(f'Cabeçalho esperado: {",".join(COLUNAS)}')

    resultado = ResultadoSigtap()
    existentes = {p.codigo: p for p in Procedimento.objects.all()}
    with transaction.atomic():
        for numero, linha in enumerate(leitor, start=2):
            codigo = formatar_codigo(linha['codigo'] or '')
            nome = (linha['nome'] or '').strip()
            if not RE_CODIGO.match(codigo) or not nome:
                resultado.rejeitados.append(f'linha {numero}: código ou nome inválido')
                continue
            dados = {
                'nome': nome[:255],
                'grupo': ' '.join((linha['grupo'] or '').split())[:150],
                'instrumentos': (linha['instrumentos'] or '').strip()[:100],
            }
            atual = existentes.get(codigo)
            if atual is None:
                existentes[codigo] = Procedimento.objects.create(codigo=codigo, ativo=True, **dados)
                resultado.criados += 1
            elif any(getattr(atual, k) != v for k, v in dados.items()):
                for k, v in dados.items():
                    setattr(atual, k, v)
                atual.save()
                resultado.atualizados += 1
            else:
                resultado.inalterados += 1
    return resultado
