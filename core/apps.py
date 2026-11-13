from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'
    verbose_name = 'Sistema de Gerenciamento Ambulatorial'

    def ready(self) -> None:
        from . import db  # noqa: F401  (registra o sinal connection_created)
