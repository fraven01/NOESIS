import logging
import sys

from django.apps import AppConfig
from django.conf import settings


logger = logging.getLogger(__name__)


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        """Registriert Signal-Handler."""
        from . import signals  # noqa: F401

        # Beim Start des qcluster-Workers einmal die Langfuse-Konfiguration ausgeben.
        if "qcluster" in sys.argv:
            logger.info(
                "Langfuse cfg host=%r pk_len=%s sk_len=%s",
                getattr(settings, "LANGFUSE_HOST", None),
                len(getattr(settings, "LANGFUSE_PUBLIC_KEY", "") or ""),
                len(getattr(settings, "LANGFUSE_SECRET_KEY", "") or ""),
            )

