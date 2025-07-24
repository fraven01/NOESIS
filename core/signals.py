import logging
from django.conf import settings
from django.db import DatabaseError
from django.db.models.signals import post_migrate, post_save
from django.dispatch import receiver
import google.generativeai as genai

from django_q.tasks import async_task

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

    task_map: dict[int, list[tuple[str, int]]] = {
        1: [("core.llm_tasks.check_anlage1", instance.projekt.pk)],
        2: [
            ("core.llm_tasks.worker_run_anlage2_analysis", instance.pk),
            ("core.llm_tasks.run_conditional_anlage2_check", instance.pk),
        ],
        3: [("core.llm_tasks.analyse_anlage3", instance.projekt.pk)],
        4: [("core.llm_tasks.analyse_anlage4_async", instance.projekt.pk)],
        5: [("core.llm_tasks.check_anlage5", instance.projekt.pk)],
    }

    tasks = task_map.get(instance.anlage_nr)
    if not tasks:
        return

    if instance.anlage_nr == 2:
        instance.processing_status = BVProjectFile.PROCESSING
        instance.save(update_fields=["processing_status"])

    for func, arg in tasks:
        try:
            async_task(func, arg)
        except Exception:
            logger.exception("Fehler beim Starten der Auto-Analyse")

