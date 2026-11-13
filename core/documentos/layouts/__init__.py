"""Layouts gerados por código (reportlab): cada módulo desenha o PDF base e devolve as posições dos campos."""
from __future__ import annotations

from typing import Callable

from . import bpai, prescricao_oculos, receituario_colirios
from .base import CampoLayout, LayoutGerado

CONSTRUTORES: tuple[Callable[[], LayoutGerado], ...] = (
    bpai.construir,
    prescricao_oculos.construir,
    receituario_colirios.construir,
)

__all__ = ['CONSTRUTORES', 'CampoLayout', 'LayoutGerado']
