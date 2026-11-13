from __future__ import annotations

import calendar
from datetime import date

from django.utils import timezone


def periodo_ate_fim_do_mes(hoje: date | None = None) -> tuple[date, date]:
    """Período do filtro do Soul MV: hoje → último dia do mês corrente (spec §2, passo 7)."""
    hoje = hoje or timezone.localdate()
    ultimo_dia = calendar.monthrange(hoje.year, hoje.month)[1]
    return hoje, hoje.replace(day=ultimo_dia)
