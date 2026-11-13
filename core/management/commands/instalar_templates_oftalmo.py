from django.core.management.base import BaseCommand

from core.documentos.instalacao import instalar_templates


class Command(BaseCommand):
    help = ('(Re)gera os PDFs base dos templates de oftalmologia (BPA-I, Prescrição de Óculos, Receituário 2 vias) '
            'e cria/atualiza os templates e campos. Idempotente.')

    def handle(self, *args, **options):
        resultado = instalar_templates()
        for nome in resultado.templates_criados:
            self.stdout.write(f'Criado: {nome}')
        for nome in resultado.templates_atualizados:
            self.stdout.write(f'Atualizado: {nome}')
        for aviso in resultado.avisos:
            self.stdout.write(f'Aviso: {aviso}')
        self.stdout.write(
            f'Campos: {resultado.campos_criados} criados, {resultado.campos_atualizados} atualizados, '
            f'{resultado.campos_excluidos} excluídos, {resultado.campos_inativados} inativados.'
        )
