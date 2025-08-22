import logging
from django.conf import settings
from django.db import DatabaseError
from django.db.models.signals import post_migrate, post_save
from django.dispatch import receiver
import google.generativeai as genai

from .utils import start_analysis_for_file

from .models import LLMConfig, BVProjectFile

logger = logging.getLogger(__name__)


@receiver(post_migrate)
def init_llm_config(sender, **kwargs) -> None:
    """Erzeugt oder aktualisiert die LLM-Konfiguration."""
    try:
        cfg, _ = LLMConfig.objects.get_or_create(
            pk=1,
            defaults={
                "default_model": settings.GOOGLE_LLM_MODEL,
                "gutachten_model": settings.GOOGLE_LLM_MODEL,
                "anlagen_model": settings.GOOGLE_LLM_MODEL,
                "vision_model": settings.GOOGLE_VISION_MODEL,
            },
        )

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

        if models != (cfg.available_models or []):
            cfg.available_models = models
            cfg.models_changed = True
            cfg.save()
    except DatabaseError:
        logger.debug("LLMConfig table not ready")


@receiver(post_save, sender=BVProjectFile)
def auto_start_analysis(sender, instance: BVProjectFile, created: bool, **kwargs) -> None:
    """Startet nach dem Upload automatisch die Analyse."""
    if not created:
        return

    task_id = start_analysis_for_file(instance.pk)
    if task_id:
        instance.verification_task_id = task_id
        instance.save(update_fields=["verification_task_id"])

