from .models import BVProject
from .llm_tasks import (
    check_anlage1,
    check_anlage2,
    check_anlage3,
    check_anlage4,
    check_anlage5,
    check_anlage6,
)


def run_all_checks(projekt: BVProject) -> None:
    """Prüft alle vorhandenen Anlagen eines Projekts."""
    funcs = [
        check_anlage1,
        check_anlage2,
        check_anlage3,
        check_anlage4,
        check_anlage5,
        check_anlage6,
    ]
    for func in funcs:
        try:
            func(projekt.pk)
        except ValueError:
            # Anlage fehlt
            continue


def set_project_status(projekt: BVProject, status: str) -> None:
    """Setzt den Status eines BVProject.

    :param projekt: Das zu aktualisierende Projekt
    :param status: Neuer Status aus ``BVProject.STATUS_CHOICES``
    :raises ValueError: Wenn der Status ungültig ist
    """
    valid = [s[0] for s in BVProject.STATUS_CHOICES]
    if status not in valid:
        raise ValueError("Ungültiger Status")
    projekt.status = status
    projekt.save(update_fields=["status"])
    if status == BVProject.STATUS_GUTACHTEN_OK:
        run_all_checks(projekt)
