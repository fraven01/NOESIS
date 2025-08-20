from __future__ import annotations

import logging

from django_q.tasks import async_task
from django.db import transaction
from django.db.models import Q

from .models import (
    BVProject,
    BVProjectFile,
    AnlagenFunktionsMetadaten,
    ZweckKategorieA,
    Anlage5Review,
)

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


def has_any_gap(projekt: BVProject) -> bool:
    """Prüft, ob für ein Projekt ein GAP vorliegt."""

    pf1 = get_project_file(projekt, 1)
    if pf1 and pf1.question_review:
        if any((d.get("vorschlag") or "").strip() for d in pf1.question_review.values()):
            return True

    pf2 = get_project_file(projekt, 2)
    if pf2 and AnlagenFunktionsMetadaten.objects.filter(anlage_datei=pf2).filter(
        Q(is_negotiable_manual_override=False)
        | (Q(supervisor_notes__isnull=False) & ~Q(supervisor_notes=""))
    ).exists():
        return True

    pf4 = get_project_file(projekt, 4)
    if pf4 and pf4.manual_comment.strip():
        return True

    pf5 = get_project_file(projekt, 5)
    if pf5:
        try:
            review = pf5.anlage5review
        except Anlage5Review.DoesNotExist:
            review = None
        if review and (
            review.found_purposes.count() < ZweckKategorieA.objects.count()
            or bool(review.sonstige_zwecke.strip())
        ):
            return True

    return False



def start_analysis_for_file(file_id: int) -> str | None:
    """Startet die Analyse f\xFCr die Projektdatei mit ``file_id``.

    Setzt den Status auf ``PROCESSING`` und plant die zugeh\xF6rigen
    Hintergrund-Tasks \u00fcber ``async_task`` ein. Die Tasks werden erst nach
    erfolgreichem Speichern des Status gestartet. Die ID des ersten geplanten
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

    def enqueue_tasks() -> None:
        nonlocal task_id
        try:
            for func, arg in tasks:
                tid = async_task(func, arg)
                if task_id is None:
                    task_id = tid
        except Exception:  # pragma: no cover - loggen genügt
            logger.exception("Fehler beim Starten der Analyse")
            update_file_status(file_id, BVProjectFile.FAILED)

    transaction.on_commit(enqueue_tasks)
    return task_id


@transaction.atomic
def update_file_status(file_id: int, status: str) -> None:
    """Aktualisiert den Verarbeitungsstatus einer Projektdatei."""

    pf = BVProjectFile.objects.get(pk=file_id)
    pf.processing_status = status
    pf.save(update_fields=["processing_status"])

