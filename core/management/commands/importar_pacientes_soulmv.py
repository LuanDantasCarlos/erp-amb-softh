from pathlib import Path

from django.core.management.base import BaseCommand, CommandError, CommandParser

from core.integracao.soulmv.importador import importar_arquivo
from core.models import ExecucaoImportacao


class Command(BaseCommand):
    help = 'Importa pacientes e agendamentos novos a partir do CSV exportado do Soul MV (insert-only).'

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument('--arquivo', required=True, type=Path, help='Caminho do CSV exportado.')
        parser.add_argument(
            '--forcar', action='store_true', help='Processa mesmo se o sha256 for igual ao da última importação.'
        )

    def handle(self, *args, arquivo: Path | str, forcar: bool = False, **options) -> None:
        arquivo = Path(arquivo)
        if not arquivo.is_file():
            raise CommandError(f'Arquivo não encontrado: {arquivo}')

        execucao = importar_arquivo(arquivo, forcar=forcar)
        resumo = (
            f'Execução #{execucao.pk} [{execucao.status}] linhas={execucao.linhas_lidas} '
            f'pacientes_criados={execucao.pacientes_criados} agendamentos_criados={execucao.agendamentos_criados} '
            f'rejeitadas={execucao.linhas_rejeitadas}'
        )
        if execucao.status == ExecucaoImportacao.STATUS_ERRO:
            raise CommandError(f'{resumo} erro={execucao.erro}')
        self.stdout.write(self.style.SUCCESS(resumo) if execucao.status == ExecucaoImportacao.STATUS_SUCESSO else resumo)
        if execucao.erro:
            self.stdout.write(execucao.erro)
