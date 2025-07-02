from django.apps import AppConfig
import logging


logger = logging.getLogger(__name__)


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        """Registriert Signal-Handler."""
        from . import signals  # noqa: F401

