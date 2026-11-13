import logging
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.integracao.soulmv.extrator import obter_extrator
from core.integracao.soulmv.job import executar_job
from core.models import ExecucaoImportacao

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Job horário Soul MV: extrai o CSV (hoje → fim do mês) e importa pacientes/agendamentos novos.'

    def handle(self, *args, **options) -> None:
        if not settings.SOULMV_INBOX_DIR:
            raise CommandError('SOULMV_INBOX_DIR não configurado.')

        resultado = executar_job(
            inbox_dir=Path(settings.SOULMV_INBOX_DIR),
            extrator=obter_extrator(settings.SOULMV_EXTRATOR),
            lock_file=Path(settings.SOULMV_LOCK_FILE) if settings.SOULMV_LOCK_FILE else None,
            retencao_dias=settings.SOULMV_RETENCAO_DIAS,
            limite_execucao_min=settings.SOULMV_LIMITE_EXECUCAO_MIN,
        )

        if not resultado.executou:
            logger.info('já em execução')
            self.stdout.write('já em execução')
            return

        execucao = resultado.execucao
        resumo = (
            f'Execução #{execucao.pk} [{execucao.status}] linhas={execucao.linhas_lidas} '
            f'pacientes_criados={execucao.pacientes_criados} agendamentos_criados={execucao.agendamentos_criados} '
            f'rejeitadas={execucao.linhas_rejeitadas} csv_removidos={resultado.arquivos_removidos}'
        )
        if execucao.status == ExecucaoImportacao.STATUS_ERRO:
            raise CommandError(f'{resumo} erro={execucao.erro}')
        self.stdout.write(resumo)
