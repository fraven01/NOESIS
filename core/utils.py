from __future__ import annotations

import logging

from django_q.tasks import async_task

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



def start_analysis_for_file(file_obj: BVProjectFile) -> None:
    """Startet die Analyse f\xFCr ``file_obj``.

    Setzt den Status auf ``PROCESSING`` und plant die zugeh\xF6rigen
    Hintergrund-Tasks. Nicht vorhandene Anlagen werden ignoriert.
    """

    task_map: dict[int, list[tuple[str, int]]] = {
        1: [("core.llm_tasks.check_anlage1", file_obj.projekt.pk)],
        2: [
            ("core.llm_tasks.worker_run_anlage2_analysis", file_obj.pk),
            ("core.llm_tasks.run_conditional_anlage2_check", file_obj.pk),
        ],
        3: [("core.llm_tasks.analyse_anlage3", file_obj.projekt.pk)],
        4: [("core.llm_tasks.analyse_anlage4_async", file_obj.projekt.pk)],
        5: [("core.llm_tasks.check_anlage5", file_obj.projekt.pk)],
    }

    tasks = task_map.get(file_obj.anlage_nr)
    if not tasks:
        return

    file_obj.processing_status = BVProjectFile.PROCESSING
    file_obj.save(update_fields=["processing_status"])

    for func, arg in tasks:
        try:
            async_task(func, arg)
        except Exception:
            logger.exception("Fehler beim Starten der Analyse")

