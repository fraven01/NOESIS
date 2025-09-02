from __future__ import annotations

import logging
import copy

from django_q.tasks import async_task
from django.db import transaction
from django.db.models import Q
import hashlib
import json

from .models import (
    BVProject,
    BVProjectFile,
    AnlagenFunktionsMetadaten,
    ZweckKategorieA,
    Anlage5Review,
)

logger = logging.getLogger(__name__)


def get_project_file(
    projekt: BVProject, nr: int, version: int | None = None
) -> BVProjectFile | None:
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
        if any(
            (d.get("vorschlag") or "").strip() for d in pf1.question_review.values()
        ):
            return True

    pf2 = get_project_file(projekt, 2)
    if (
        pf2
        and AnlagenFunktionsMetadaten.objects.filter(anlage_datei=pf2)
        .filter(
            Q(is_negotiable_manual_override=False)
            | (Q(supervisor_notes__isnull=False) & ~Q(supervisor_notes=""))
        )
        .exists()
    ):
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
    """Startet die Analyse f\xfcr die Projektdatei mit ``file_id``.

    Setzt den Status auf ``PROCESSING`` und plant die zugeh\xf6rigen
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
    pf = BVProjectFile.objects.select_for_update().get(pk=file_id)
    pf.processing_status = status
    pf.save(update_fields=["processing_status"])


def compute_gap_source_hash(pf: BVProjectFile) -> str:
    """Erzeugt einen stabilen Fingerprint der relevanten GAP-Eingaben.

    - Anlage 1: basiert auf den manuell gesetzten Review-Feldern (hinweis,
      vorschlag, ok) je Frage.
    - Anlage 2: basiert auf vorhandenen externen GAP-Anmerkungen je Funktion/
      Unterfrage.

    Gibt einen Hex-SHA256-Hash zurück oder einen leeren String, wenn für die
    Anlage kein Fingerprint definiert ist.
    """
    try:
        if pf.anlage_nr == 1:
            review = pf.question_review or {}
            entries: list[dict] = []
            for num, data in sorted(review.items(), key=lambda x: str(x[0])):
                if not isinstance(data, dict):
                    continue
                hinweis = (data.get("hinweis") or "").strip()
                vorschlag = (data.get("vorschlag") or "").strip()
                ok_flag = bool(data.get("ok", False))
                # Nur relevante Einträge berücksichtigen (wie bei der Zusammenfassung)
                if hinweis or vorschlag or (str(num) in review and not ok_flag):
                    entries.append(
                        {
                            "num": str(num),
                            "hinweis": hinweis,
                            "vorschlag": vorschlag,
                            "ok": ok_flag,
                        }
                    )
            payload = {"anlage": 1, "entries": entries}
        elif pf.anlage_nr == 2:
            qs = (
                AnlagenFunktionsMetadaten.objects.filter(anlage_datei=pf)
                .filter(Q(gap_summary__isnull=False) & ~Q(gap_summary=""))
                .values("funktion_id", "subquestion_id", "gap_summary")
            )
            entries = [
                {
                    "funktion": r["funktion_id"],
                    "subq": r["subquestion_id"],
                    "extern": (r["gap_summary"] or "").strip(),
                }
                for r in qs
            ]
            entries.sort(
                key=lambda d: (
                    d.get("funktion") or 0,
                    d.get("subq") or 0,
                    d.get("extern"),
                )
            )
            payload = {"anlage": 2, "entries": entries}
        else:
            return ""

        data = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        return hashlib.sha256(data).hexdigest()
    except Exception:  # pragma: no cover - Fingerprint darf App nicht blockieren
        logger.exception("Fehler beim Berechnen des GAP-Fingerprints")
        return ""


def is_gap_summary_outdated(pf: BVProjectFile) -> bool:
    """Prüft, ob die gespeicherte GAP-Zusammenfassung veraltet ist.

    Die Prüfung erfolgt nur, wenn bereits ein Hash gespeichert ist. Dadurch
    bleiben bestehende Projekte ohne Hash rückwärtskompatibel und zeigen weiter
    den Bearbeiten-Button.
    """
    if not pf or not pf.gap_summary:
        return False
    if not pf.gap_source_hash:
        return False
    current = compute_gap_source_hash(pf)
    return bool(current and current != pf.gap_source_hash)


def update_anlage1_verhandlungsfaehig(anlage: BVProjectFile) -> None:
    """Aktualisiert das Verhandlungsflag anhand des Frage-Reviews."""

    if anlage.anlage_nr != 1:
        return

    questions = (
        anlage.analysis_json.get("questions", {})
        if isinstance(anlage.analysis_json, dict)
        else {}
    )
    review = anlage.question_review or {}
    all_ok = questions and all(
        review.get(str(num), {}).get("ok") for num in questions
    )
    new_val = bool(all_ok)
    if anlage.verhandlungsfaehig != new_val:
        anlage.verhandlungsfaehig = new_val
        anlage.save(update_fields=["verhandlungsfaehig"])


def propagate_question_review(
    parent: BVProjectFile,
    obj: BVProjectFile,
    current_answers: dict[str, dict] | None = None,
) -> None:
    """Übernimmt Fragenbewertungen aus der Vorgängerversion.

    Das ``ok``-Flag bleibt nur gesetzt, wenn die Antwort unverändert ist."""

    if not parent or obj.anlage_nr != 1:
        return

    parent_review = parent.question_review or {}
    if not parent_review:
        return

    parent_answers = (
        parent.analysis_json.get("questions", {})
        if isinstance(parent.analysis_json, dict)
        else {}
    )
    if current_answers is None:
        current_answers = (
            obj.analysis_json.get("questions", {})
            if isinstance(obj.analysis_json, dict)
            else {}
        )
    if not current_answers:
        return

    new_review: dict[str, dict] = {}
    for num, entry in parent_review.items():
        new_entry = copy.deepcopy(entry)
        if parent_answers.get(num) == current_answers.get(num) and entry.get("ok"):
            new_entry["ok"] = True
        else:
            new_entry["ok"] = False
        new_review[str(num)] = new_entry

    if new_review:
        obj.question_review = new_review
        obj.save(update_fields=["question_review"])
        update_anlage1_verhandlungsfaehig(obj)
