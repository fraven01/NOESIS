from __future__ import annotations

from .models import BVProject, BVProjectFile


def get_project_file(projekt: BVProject, nr: int, version: int | None = None) -> BVProjectFile | None:
    """Hilfsfunktion zum Abrufen einer Projektdatei.

    Gibt bei Angabe einer ``version`` die entsprechende Datei zurueck. Fehlt die
    Angabe, wird die aktive Datei mit der hoechsten Versionsnummer geliefert.
    """

    qs = projekt.anlagen.filter(anlage_nr=nr)
    if version is not None:
        return qs.filter(version=version).first()
    return qs.filter(is_active=True).order_by("-version").first()

