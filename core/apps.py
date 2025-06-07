from django.apps import AppConfig
import logging
import google.generativeai as genai


logger = logging.getLogger(__name__)


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        from django.conf import settings
        from django.db import DatabaseError
        from .models import LLMConfig

        try:
            cfg, _ = LLMConfig.objects.get_or_create(
                pk=1,
                defaults={
                    "default_model": settings.GOOGLE_LLM_MODEL,
                    "gutachten_model": settings.GOOGLE_LLM_MODEL,
                    "anlagen_model": settings.GOOGLE_LLM_MODEL,
                },
            )

            if not cfg.available_models:
                models = []
                try:
                    if settings.GOOGLE_API_KEY:
                        genai.configure(api_key=settings.GOOGLE_API_KEY)
                        models = [m.name for m in genai.list_models()]
                except Exception:
                    logger.exception("Failed to fetch model list")
                    models = settings.GOOGLE_AVAILABLE_MODELS
                if not models:
                    models = settings.GOOGLE_AVAILABLE_MODELS
                cfg.available_models = models
                cfg.save()
        except DatabaseError:
            # Datenbanktabellen existieren noch nicht (Migrationen)
            logger.debug("LLMConfig table not ready")
