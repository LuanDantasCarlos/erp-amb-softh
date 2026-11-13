"""Tela "Gerar documento": leitura do POST, médico e data padrão, valores automáticos (spec §3.5)."""
from __future__ import annotations

from datetime import date
from typing import Any, Iterable, Optional

from django.utils import timezone

from core.agenda import limites_do_dia
from core.models import Agendamento, CampoTemplateDocumento, Medico, Paciente, Procedimento

from .engine import opcoes_normalizadas, valor_automatico
from .fontes import ContextoDocumento
from .instalacao import campo_inativo

SESSAO_ULTIMO_MEDICO = 'documentos_ultimo_medico_id'


def campos_ativos(template_id) -> list[CampoTemplateDocumento]:
    return [c for c in CampoTemplateDocumento.objects.filter(template_id=template_id) if not campo_inativo(c)]


def medico_inicial(request) -> Optional[Medico]:
    """Médico ligado ao usuário; senão o último usado pelo usuário (sessão); senão nenhum."""
    medico = Medico.objects.filter(usuario=request.user, ativo=True).order_by('nome').first()
    if medico is not None:
        return medico
    ultimo = request.session.get(SESSAO_ULTIMO_MEDICO)
    if ultimo:
        return Medico.objects.filter(pk=ultimo, ativo=True).first()
    return None


def data_atendimento_padrao(paciente: Optional[Paciente], hoje: Optional[date] = None) -> date:
    """Agendamento do paciente hoje; senão o próximo; senão hoje."""
    hoje = hoje or timezone.localdate()
    if paciente is None:
        return hoje
    inicio, _ = limites_do_dia(hoje)
    proximo = (Agendamento.objects.filter(paciente=paciente, data_agenda__gte=inicio)
               .order_by('data_agenda').values_list('data_agenda', flat=True).first())
    return timezone.localtime(proximo).date() if proximo else hoje


def _int(valor: Any) -> int:
    try:
        return int(valor)
    except (TypeError, ValueError):
        return 1


def ler_campos_post(campos: Iterable[CampoTemplateDocumento], post) -> tuple[dict[str, Any], set[str]]:
    """Valores digitados por campo e os ids que o usuário apagou de propósito (não recebem automático)."""
    valores: dict[str, Any] = {}
    manter_vazios: set[str] = set()
    for campo in campos:
        chave = str(campo.id)
        nome = f'campo_{chave}'
        if campo.tipo_campo == 'checkbox':
            valores[chave] = post.getlist(f'{nome}[]')
            if f'{nome}__presente' in post:
                manter_vazios.add(chave)  # formulário renderizado: desmarcado é desmarcado
        elif campo.tipo_campo == 'procedimentos':
            valores[chave] = [
                {'codigo': codigo, 'qtd': _int(post.get(f'{nome}_qtd_{codigo}', 1))}
                for codigo in post.getlist(f'{nome}[]')
            ]
        else:
            valores[chave] = post.get(nome, '')
            if nome in post and valores[chave] == '':
                manter_vazios.add(chave)
    return valores, manter_vazios


def valores_iniciais(campos: Iterable[CampoTemplateDocumento], contexto: ContextoDocumento) -> dict[str, Any]:
    """Valor automático de cada campo para pré-preencher o formulário (só os que têm valor)."""
    iniciais = {}
    for campo in campos:
        if campo.tipo_campo == 'procedimentos':
            continue
        valor = valor_automatico(campo, contexto)
        if valor in ('', None, []):
            continue
        if campo.tipo_campo in ('select', 'radio'):
            ids = {o['id'] for o in opcoes_normalizadas(campo)}
            if str(valor) not in ids:
                continue
        iniciais[str(campo.id)] = valor
    return iniciais


def catalogo_procedimentos() -> list[dict[str, Any]]:
    """Procedimentos ativos agrupados por grupo, para o campo `procedimentos`."""
    grupos: dict[str, list[dict[str, str]]] = {}
    for p in Procedimento.objects.filter(ativo=True).order_by('grupo', 'nome'):
        grupos.setdefault(p.grupo or 'Outros', []).append(
            {'codigo': p.codigo, 'nome': p.nome, 'instrumentos': p.instrumentos}
        )
    return [{'grupo': grupo, 'itens': itens} for grupo, itens in grupos.items()]
