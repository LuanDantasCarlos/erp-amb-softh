"""Orquestração do job horário: lock → limpeza do inbox → extração → importação (spec §5, Fase 3)."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from core.models import ExecucaoImportacao

from .extrator import ExtracaoError, Extrator
from .importador import importar_arquivo, marcar_execucoes_expiradas, registrar_falha
from .lock import LockOcupado, lock_arquivo
from .periodo import periodo_ate_fim_do_mes

logger = logging.getLogger(__name__)

NOME_LOCK = '.job_pacientes_soulmv.lock'


@dataclass(frozen=True)
class ResultadoJob:
    executou: bool
    execucao: Optional[ExecucaoImportacao] = None
    arquivos_removidos: int = 0


def limpar_inbox(pasta: Path, retencao_dias: int, agora: Optional[float] = None) -> int:
    """Remove CSVs com mais de `retencao_dias` (LGPD). Outros arquivos (ex.: o lock) são preservados."""
    pasta = Path(pasta)
    if not pasta.is_dir():
        return 0
    limite = (agora if agora is not None else time.time()) - retencao_dias * 86400
    removidos = 0
    for arquivo in pasta.iterdir():
        if arquivo.is_file() and arquivo.suffix.lower() == '.csv' and arquivo.stat().st_mtime < limite:
            try:
                arquivo.unlink()
                removidos += 1
            except OSError:
                logger.warning('Não foi possível remover %s do inbox', arquivo.name)
    return removidos


def executar_job(
    *,
    inbox_dir: Path,
    extrator: Extrator,
    lock_file: Optional[Path] = None,
    retencao_dias: int = 7,
    limite_execucao_min: int = 50,
    hoje: Optional[date] = None,
) -> ResultadoJob:
    inbox_dir = Path(inbox_dir)
    inbox_dir.mkdir(parents=True, exist_ok=True)
    lock_file = Path(lock_file) if lock_file else inbox_dir / NOME_LOCK
    limite = timedelta(minutes=limite_execucao_min)

    try:
        with lock_arquivo(lock_file, limite.total_seconds()):
            expiradas = marcar_execucoes_expiradas(limite)
            if expiradas:
                logger.warning('%s execução(ões) anteriores marcadas como erro por timeout', expiradas)
            removidos = limpar_inbox(inbox_dir, retencao_dias)
            inicio, fim = periodo_ate_fim_do_mes(hoje)

            try:
                arquivo = extrator.extrair(inicio, fim, inbox_dir)
            except ExtracaoError as exc:
                logger.error('Extração Soul MV falhou: %s', exc)
                return ResultadoJob(True, registrar_falha('', f'Extração falhou: {exc}'), removidos)
            except Exception as exc:
                logger.exception('Extração Soul MV falhou')
                erro = f'Extração falhou: {type(exc).__name__} (detalhes no log do servidor).'
                return ResultadoJob(True, registrar_falha('', erro), removidos)

            return ResultadoJob(True, importar_arquivo(arquivo), removidos)
    except LockOcupado as exc:
        logger.info('Job Soul MV já em execução (%s)', exc)
        return ResultadoJob(False)
