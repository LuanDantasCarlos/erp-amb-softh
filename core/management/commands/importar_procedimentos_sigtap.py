from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from core.documentos.sigtap import CSV_PADRAO, CatalogoInvalidoError, importar_procedimentos


class Command(BaseCommand):
    help = 'Importa (upsert por código) o catálogo de procedimentos do SIGTAP a partir de um CSV.'

    def add_arguments(self, parser):
        parser.add_argument('--csv', default=str(CSV_PADRAO),
                            help='CSV codigo,nome,grupo,instrumentos (padrão: catálogo de oftalmologia 11/2026).')

    def handle(self, *args, **options):
        caminho = Path(options['csv'])
        if not caminho.is_file():
            raise CommandError(f'Arquivo não encontrado: {caminho}')
        try:
            resultado = importar_procedimentos(caminho)
        except CatalogoInvalidoError as exc:
            raise CommandError(str(exc)) from exc
        for rejeicao in resultado.rejeitados:
            self.stderr.write(f'Rejeitado: {rejeicao}')
        self.stdout.write(
            f'Procedimentos: {resultado.criados} criados, {resultado.atualizados} atualizados, '
            f'{resultado.inalterados} inalterados, {len(resultado.rejeitados)} rejeitados.'
        )
