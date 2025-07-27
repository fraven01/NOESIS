from __future__ import annotations

import logging

from django_q.tasks import async_task, Chain
from django.db import transaction, connection

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
    Hintergrund-Tasks. Bei SQLite werden die Tasks sequenziell in einer
    ``Chain`` ausgef\xFChrt, um Sperrkonflikte zu vermeiden.
    Nicht vorhandene Anlagen werden ignoriert.
    """

    tasks = file_obj.get_analysis_tasks()
    if not tasks:
        return

    file_obj.processing_status = BVProjectFile.PROCESSING
    file_obj.save(update_fields=["processing_status"])

    try:
        if connection.vendor == "sqlite":
            chain = Chain()
            for func, arg in tasks:
                chain.append(func, arg)
            chain.run()
        else:
            for func, arg in tasks:
                async_task(func, arg)
    except Exception:
        logger.exception("Fehler beim Starten der Analyse")


@transaction.atomic
def update_file_status(file_id: int, status: str) -> None:
    """Aktualisiert den Verarbeitungsstatus einer Projektdatei."""

    pf = BVProjectFile.objects.get(pk=file_id)
    pf.processing_status = status
    pf.save(update_fields=["processing_status"])

