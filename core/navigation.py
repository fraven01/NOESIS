"""Konfiguration der Navigationspunkte der Anwendung.

Diese Datei definiert die Konstante ``NAV_ITEMS``, welche die Einträge
für die Hauptnavigation enthält.
"""

from typing import List, TypedDict


class NavItem(TypedDict):
    """Struktur eines einzelnen Navigationseintrags."""

    title: str
    url: str
    perm: str


# Liste der Navigationseinträge, die im Hauptmenü erscheinen.
# "perm" steht für die Berechtigung, die für den Zugriff erforderlich ist.
NAV_ITEMS: List[NavItem] = [
    {
        "title": "Dashboard",
        "url": "home",
        "perm": "app.view_model",
    },
]
