"""Consultas de pacientes por data de atendimento (Agendamento.data_agenda).

Tudo por subquery correlacionada usando o índice (paciente, data_agenda): sem N+1 e sem duplicar
paciente com mais de um agendamento.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Optional

from django.db.models import Exists, OuterRef, QuerySet, Subquery
from django.db.models.functions import Coalesce
from django.utils import timezone

from .models import Agendamento


def limites_do_dia(dia: date) -> tuple[datetime, datetime]:
    """[00:00, 00:00 do dia seguinte) no fuso local (TIME_ZONE), como datetimes aware.

    Usa intervalo em vez de `data_agenda__date` para aproveitar o índice.
    """
    inicio = timezone.make_aware(datetime.combine(dia, time.min))
    fim = timezone.make_aware(datetime.combine(dia + timedelta(days=1), time.min))
    return inicio, fim


def _agendamentos_do_paciente() -> QuerySet:
    return Agendamento.objects.filter(paciente=OuterRef('pk'), data_agenda__isnull=False)


def filtrar_atendimento_no_dia(pacientes: QuerySet, dia: date) -> QuerySet:
    """Só pacientes com agendamento no dia, anotados com o primeiro horário/item do dia.

    Ordem: horário do primeiro agendamento do dia, depois nome.
    """
    return anotar_atendimento_no_dia(pacientes, dia, apenas_com_atendimento=True).order_by('atendimento', 'nome')


def anotar_atendimento_no_dia(pacientes: QuerySet, dia: date, apenas_com_atendimento: bool = False) -> QuerySet:
    """Anota `atendimento` e `atendimento_item` com o primeiro agendamento do dia (ou None)."""
    inicio, fim = limites_do_dia(dia)
    do_dia = _agendamentos_do_paciente().filter(data_agenda__gte=inicio, data_agenda__lt=fim).order_by('data_agenda', 'pk')
    if apenas_com_atendimento:
        pacientes = pacientes.filter(Exists(do_dia))
    return pacientes.annotate(
        atendimento=Subquery(do_dia.values('data_agenda')[:1]),
        atendimento_item=Subquery(do_dia.values('item_agendamento')[:1]),
    )


def anotar_proximo_atendimento(pacientes: QuerySet, agora: Optional[datetime] = None) -> QuerySet:
    """Anota o próximo agendamento a partir de `agora`; sem próximo, o último anterior."""
    agora = agora or timezone.now()
    proximo = _agendamentos_do_paciente().filter(data_agenda__gte=agora).order_by('data_agenda', 'pk')
    ultimo = _agendamentos_do_paciente().filter(data_agenda__lt=agora).order_by('-data_agenda', '-pk')
    return pacientes.annotate(
        atendimento=Coalesce(Subquery(proximo.values('data_agenda')[:1]), Subquery(ultimo.values('data_agenda')[:1])),
        atendimento_item=Coalesce(
            Subquery(proximo.values('item_agendamento')[:1]), Subquery(ultimo.values('item_agendamento')[:1])
        ),
    )
