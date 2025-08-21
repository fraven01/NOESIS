"""Kontextprozessoren für die Django-Templates."""

from typing import TypedDict
from types import SimpleNamespace

from django.db.models import Q
from django.http import HttpRequest

from .models import Area, Tile


def is_admin(request: HttpRequest) -> dict[str, bool]:
    """Gibt an, ob der aktuelle Benutzer zur Admin-Gruppe gehört."""

    if request.user.is_authenticated:
        return {"is_admin": request.user.groups.filter(name__iexact="admin").exists()}
    return {"is_admin": False}


class NavSection(TypedDict):
    """Ein Abschnitt der Navigation bestehend aus Bereich und Kacheln."""

    area: Area
    tiles: list[Tile]


def user_navigation(request: HttpRequest) -> dict[str, list[NavSection]]:
    """Ermittelt die Navigation für den aktuellen Benutzer.

    Liefert für jeden zugänglichen Bereich eine Liste der sichtbaren Kacheln.
    Der Rückgabewert hat folgende Struktur:

    ``{"user_navigation": [{"area": Area, "tiles": [Tile, ...]}, ...]}``
    """

    from .views import get_user_tiles

    if not request.user.is_authenticated:
        return {"user_navigation": []}

    areas = Area.objects.filter(
        Q(userareaaccess__user=request.user)
        | Q(groupareaaccess__group__in=request.user.groups.all())
    ).distinct()

    navigation: list[NavSection] = []
    for area in areas:
        tiles = get_user_tiles(request.user, area.slug)
        navigation.append({"area": area, "tiles": tiles})

    # Admin-Bereiche integrieren
    if request.user.is_staff or request.user.groups.filter(name__iexact="admin").exists():
        project_admin_area = SimpleNamespace(name="Projekt-Admin", slug="projekt-admin")
        project_admin_tiles = [
            SimpleNamespace(name="Projekt-Liste", url_name="admin_projects"),
            SimpleNamespace(name="Status-Definitionen", url_name="admin_project_statuses"),
            SimpleNamespace(name="LLM-Rollen", url_name="admin_llm_roles"),
            SimpleNamespace(name="Benutzer verwalten", url_name="admin_user_list"),
            SimpleNamespace(name="Konfiguration", url_name="config_transfer"),
        ]
        navigation.append({"area": project_admin_area, "tiles": project_admin_tiles})

    if request.user.is_superuser:
        system_admin_area = SimpleNamespace(name="System-Admin", slug="system-admin")
        system_admin_tiles = [
            SimpleNamespace(name="Django Admin", url_name="admin:index"),
            SimpleNamespace(name="Benutzer verwalten", url_name="admin:auth_user_changelist"),
        ]
        navigation.append({"area": system_admin_area, "tiles": system_admin_tiles})

    return {"user_navigation": navigation}

