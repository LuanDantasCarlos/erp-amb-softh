"""Extração do CSV do Soul MV: arquivo local (testes/Plano C) ou cliente HTTP (`cliente_http`)."""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Callable, Dict, Optional, Protocol

from django.core.exceptions import ImproperlyConfigured


class ExtracaoError(RuntimeError):
    """Falha ao obter o CSV; o job registra como execução com erro."""


class Extrator(Protocol):
    def extrair(self, inicio: date, fim: date, destino: Path) -> Path:
        """Obtém o CSV do período [inicio, fim] e devolve o caminho do arquivo dentro de `destino`."""
        ...


class ExtratorArquivoLocal:
    """Usa o CSV mais recente já depositado numa pasta (testes e Plano C).

    Não filtra por período: quem deposita o arquivo é responsável pelo filtro.
    """

    def __init__(self, origem: Optional[Path] = None, padrao: str = '*.csv') -> None:
        self.origem = Path(origem) if origem else None
        self.padrao = padrao

    def extrair(self, inicio: date, fim: date, destino: Path) -> Path:
        pasta = self.origem or Path(destino)
        if not pasta.is_dir():
            raise ExtracaoError(f'Pasta de entrada não encontrada: {pasta}')
        candidatos = [p for p in pasta.glob(self.padrao) if p.is_file()]
        if not candidatos:
            raise ExtracaoError(f'Nenhum CSV encontrado em {pasta}')
        return max(candidatos, key=lambda p: (p.stat().st_mtime, p.name))


def _extrator_http() -> Extrator:
    from .cliente_http import ExtratorHttpSoulMV  # import tardio: cliente_http importa este módulo

    return ExtratorHttpSoulMV()


EXTRATORES: Dict[str, Callable[[], Extrator]] = {
    'arquivo_local': ExtratorArquivoLocal,
    'http': _extrator_http,
}


def obter_extrator(nome: str) -> Extrator:
    try:
        fabrica = EXTRATORES[nome]
    except KeyError:
        raise ImproperlyConfigured(
            f'SOULMV_EXTRATOR inválido: {nome!r}. Opções: {", ".join(sorted(EXTRATORES))}'
        ) from None
    return fabrica()
