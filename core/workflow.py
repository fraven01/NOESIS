from .models import BVProject


def set_project_status(projekt: BVProject, status: str) -> None:
    """Setzt den Status eines BVProject.

    :param projekt: Das zu aktualisierende Projekt
    :param status: Neuer Status
    :raises ValueError: Wenn der Status ungültig ist
    """
    valid = [s[0] for s in BVProject.STATUS_CHOICES]
    if status not in valid:
        raise ValueError("Ungültiger Status")
    projekt.status = status
    projekt.save(update_fields=["status"])
