from .models import BVProject, BVProjectStatusHistory, ProjectStatus


def set_project_status(projekt: BVProject, status: str) -> None:
    """Setzt den Status eines BVProject.

    :param projekt: Das zu aktualisierende Projekt
    :param status: Schlüssel des neuen Status
    :raises ValueError: Wenn der Status ungültig ist
    """
    try:
        status_obj = ProjectStatus.objects.get(key=status)
    except ProjectStatus.DoesNotExist as exc:
        raise ValueError("Ungültiger Status") from exc
    projekt.status = status_obj
    projekt.save(update_fields=["status"])
    BVProjectStatusHistory.objects.create(projekt=projekt, status=status_obj)
