"""Lock entre processos baseado em arquivo (O_CREAT|O_EXCL), portável entre Linux e Windows."""
from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional


class LockOcupado(RuntimeError):
    pass


def _idade_segundos(caminho: Path) -> Optional[float]:
    """Idade do lock pelo timestamp gravado; cai para o mtime se o conteúdo estiver ilegível."""
    try:
        dados = json.loads(caminho.read_text(encoding='utf-8'))
        return time.time() - float(dados['timestamp'])
    except FileNotFoundError:
        return None
    except (ValueError, KeyError, TypeError, OSError):
        try:
            return time.time() - caminho.stat().st_mtime
        except FileNotFoundError:
            return None


def _criar(caminho: Path, token: str) -> bool:
    try:
        fd = os.open(str(caminho), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        json.dump({'pid': os.getpid(), 'timestamp': time.time(), 'token': token}, f)
    return True


@contextmanager
def lock_arquivo(caminho: Path, validade_segundos: float) -> Iterator[Path]:
    """Adquire o lock sem bloquear. Lock com mais de `validade_segundos` é considerado morto e removido.

    Levanta LockOcupado se outro processo detém um lock válido.
    """
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    token = f'{os.getpid()}-{time.time_ns()}'

    if not _criar(caminho, token):
        idade = _idade_segundos(caminho)
        if idade is not None and idade <= validade_segundos:
            raise LockOcupado(f'Lock ocupado: {caminho} (idade {int(idade)} s)')
        try:
            caminho.unlink()
        except FileNotFoundError:
            pass
        if not _criar(caminho, token):
            raise LockOcupado(f'Lock ocupado: {caminho}')

    try:
        yield caminho
    finally:
        try:
            dados = json.loads(caminho.read_text(encoding='utf-8'))
            if dados.get('token') == token:
                caminho.unlink()
        except (FileNotFoundError, ValueError, OSError):
            pass
