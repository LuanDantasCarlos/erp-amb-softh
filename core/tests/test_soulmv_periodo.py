from datetime import date

import pytest

from core.integracao.soulmv.periodo import periodo_ate_fim_do_mes


@pytest.mark.parametrize(
    ('hoje', 'fim'),
    [
        (date(2026, 1, 15), date(2026, 1, 31)),
        (date(2026, 4, 10), date(2026, 4, 30)),
        (date(2026, 2, 3), date(2026, 2, 28)),
        (date(2028, 2, 3), date(2028, 2, 29)),
        (date(2028, 2, 29), date(2028, 2, 29)),
        (date(2026, 12, 31), date(2026, 12, 31)),
        (date(2026, 11, 1), date(2026, 11, 30)),
    ],
)
def test_periodo_hoje_ate_fim_do_mes(hoje, fim):
    assert periodo_ate_fim_do_mes(hoje) == (hoje, fim)


def test_periodo_padrao_usa_data_local(settings, monkeypatch):
    from core.integracao.soulmv import periodo

    monkeypatch.setattr(periodo.timezone, 'localdate', lambda: date(2026, 11, 13))
    assert periodo_ate_fim_do_mes() == (date(2026, 11, 13), date(2026, 11, 30))
