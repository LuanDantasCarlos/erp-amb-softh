"""Instalação idempotente dos templates de oftalmologia (command `instalar_templates_oftalmo`)."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction

from core.models import CampoPreenchidoDocumento, CampoTemplateDocumento, Documento, TemplateDocumento

from .layouts import CONSTRUTORES, LayoutGerado
from .layouts.receituario_colirios import NOME_ANTIGO

logger = logging.getLogger(__name__)

PASTA_MEDIA = 'templates/oftalmologia'


@dataclass
class ResultadoInstalacao:
    templates_criados: list[str] = field(default_factory=list)
    templates_atualizados: list[str] = field(default_factory=list)
    campos_criados: int = 0
    campos_atualizados: int = 0
    campos_excluidos: int = 0
    campos_inativados: int = 0
    avisos: list[str] = field(default_factory=list)


def campo_inativo(campo) -> bool:
    return isinstance(campo.validacoes, dict) and bool(campo.validacoes.get('inativo'))


def _gravar_pdf(layout: LayoutGerado) -> str:
    caminho = f'{PASTA_MEDIA}/{layout.arquivo}'
    if default_storage.exists(caminho):
        default_storage.delete(caminho)
    return default_storage.save(caminho, ContentFile(layout.pdf))


def _instalar_layout(layout: LayoutGerado, resultado: ResultadoInstalacao) -> TemplateDocumento:
    template = TemplateDocumento.objects.filter(nome=layout.nome).order_by('pk').first()
    if template is None:
        template = TemplateDocumento(nome=layout.nome)
        resultado.templates_criados.append(layout.nome)
    else:
        resultado.templates_atualizados.append(layout.nome)
    template.descricao = layout.descricao
    template.ativo = True
    template.arquivo_template.name = _gravar_pdf(layout)
    template.save()

    existentes = {c.nome_campo: c for c in template.campos.all()}
    for ordem, definicao in enumerate(layout.campos, start=1):
        dados = {
            'tipo_campo': definicao.tipo,
            'atributo_paciente': definicao.fonte,
            'posicao': definicao.posicao,
            'opcoes': definicao.opcoes,
            'obrigatorio': definicao.obrigatorio,
            'descricao': definicao.descricao,
            'validacoes': definicao.validacoes,
            'ordem_formulario': ordem,
            'pagina': 1,
            'visivel_se': None,
        }
        campo = existentes.pop(definicao.nome, None)
        if campo is None:
            CampoTemplateDocumento.objects.create(template=template, nome_campo=definicao.nome, **dados)
            resultado.campos_criados += 1
        else:
            for atributo, valor in dados.items():
                setattr(campo, atributo, valor)
            campo.save()
            resultado.campos_atualizados += 1

    # Campos que saíram do layout: exclui se nunca foram preenchidos; senão só inativa (histórico).
    for campo in existentes.values():
        if CampoPreenchidoDocumento.objects.filter(campo_template=campo).exists():
            if not campo_inativo(campo):
                campo.validacoes = {**(campo.validacoes or {}), 'inativo': True}
                campo.save(update_fields=['validacoes', 'updated_at'])
                resultado.campos_inativados += 1
        else:
            campo.delete()
            resultado.campos_excluidos += 1
    return template


def _desativar_template_antigo(resultado: ResultadoInstalacao) -> None:
    for antigo in TemplateDocumento.objects.filter(nome__iexact=NOME_ANTIGO, ativo=True):
        if Documento.objects.filter(template=antigo).exists():
            resultado.avisos.append(
                f'Template antigo "{antigo.nome}" (#{antigo.pk}) tem documentos emitidos: mantido como está.'
            )
        else:
            antigo.ativo = False
            antigo.save(update_fields=['ativo', 'updated_at'])
            resultado.avisos.append(f'Template antigo "{antigo.nome}" (#{antigo.pk}) desativado.')


def instalar_templates() -> ResultadoInstalacao:
    resultado = ResultadoInstalacao()
    layouts = [construir() for construir in CONSTRUTORES]
    with transaction.atomic():
        for layout in layouts:
            _instalar_layout(layout, resultado)
        _desativar_template_antigo(resultado)
    logger.info('Templates de oftalmologia instalados: %s', resultado)
    return resultado
