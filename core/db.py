from django.conf import settings
from django.db.backends.signals import connection_created
from django.dispatch import receiver


@receiver(connection_created, dispatch_uid='core.configurar_sqlite')
def configurar_sqlite(sender, connection, **kwargs) -> None:
    """Aplica SQLITE_JOURNAL_MODE (padrão WAL: leituras durante a escrita do job).

    Use DELETE se o banco estiver em sistema de arquivos de rede (NFS), onde WAL não funciona.
    O valor é validado em settings contra uma lista fixa.
    """
    if connection.vendor != 'sqlite':
        return
    with connection.cursor() as cursor:
        cursor.execute(f'PRAGMA journal_mode={settings.SQLITE_JOURNAL_MODE};')
