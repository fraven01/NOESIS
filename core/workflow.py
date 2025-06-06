"""Hilfsfunktionen für Projekt-Workflows."""

from .models import BVProject


def change_project_status(project: BVProject, new_status: str) -> BVProject:
    """Setzt den Status eines Projekts.

    :param project: Das BVProject-Objekt
    :param new_status: Neuer Status
    :raises ValueError: Wenn der Status ungültig ist
    :return: Aktualisiertes Projekt
    """
    valid = {choice[0] for choice in BVProject.STATUS_CHOICES}
    if new_status not in valid:
        raise ValueError("Ungültiger Status")

    project.status = new_status
    project.save()
    return project
