from __future__ import annotations

import logging

from django_q.tasks import async_task
from django.db import transaction

from .models import BVProject, BVProjectFile

logger = logging.getLogger(__name__)


def get_project_file(projekt: BVProject, nr: int, version: int | None = None) -> BVProjectFile | None:
    """Hilfsfunktion zum Abrufen einer Projektdatei.

    Gibt bei Angabe einer ``version`` die entsprechende Datei zurueck. Fehlt die
    Angabe, wird die aktive Datei mit der hoechsten Versionsnummer geliefert.
    """

    qs = projekt.anlagen.filter(anlage_nr=nr)
    if version is not None:
        return qs.filter(version=version).first()
    return qs.filter(is_active=True).order_by("-version").first()



def start_analysis_for_file(file_id: int) -> str | None:
    """Startet die Analyse f\xFCr die Projektdatei mit ``file_id``.

    Setzt den Status auf ``PROCESSING`` und plant die zugeh\xF6rigen
    Hintergrund-Tasks \u00fcber ``async_task`` ein. Die ID des ersten geplanten
    Tasks wird zur\u00fcckgegeben, nicht vorhandene Anlagen werden ignoriert.
    """

    file_obj = BVProjectFile.objects.filter(pk=file_id).first()
    if not file_obj:
        return None

    tasks = file_obj.get_analysis_tasks()
    if not tasks:
        return None

    file_obj.processing_status = BVProjectFile.PROCESSING
    file_obj.save(update_fields=["processing_status"])

    task_id: str | None = None
    try:
        for func, arg in tasks:
            tid = async_task(func, arg)
            if task_id is None:
                task_id = tid
    except Exception:  # pragma: no cover - loggen genügt
        logger.exception("Fehler beim Starten der Analyse")
    return task_id


@transaction.atomic
def update_file_status(file_id: int, status: str) -> None:
    """Aktualisiert den Verarbeitungsstatus einer Projektdatei."""

    pf = BVProjectFile.objects.get(pk=file_id)
    pf.processing_status = status
    pf.save(update_fields=["processing_status"])

