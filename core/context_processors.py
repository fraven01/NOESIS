"""Kontextprozessoren für die Django-Templates."""

from typing import TypedDict

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

    return {"user_navigation": navigation}


class AdminLink(TypedDict):
    """Repräsentiert einen einzelnen Link innerhalb der Admin-Navigation."""

    name: str
    url_name: str


class AdminSection(TypedDict):
    """Ein Abschnitt der Admin-Navigation mit Titel und Links."""

    name: str
    tiles: list[AdminLink]


def admin_navigation(request: HttpRequest) -> dict[str, list[AdminSection]]:
    """Stellt die Navigationshierarchie für Admin-Bereiche bereit."""

    if not request.user.is_authenticated:
        return {"admin_navigation": []}

    navigation: list[AdminSection] = []

    if request.user.is_staff or request.user.groups.filter(name__iexact="admin").exists():
        navigation.append(
            {
                "name": "Projekt-Admin",
                "tiles": [
                    {"name": "Projekt-Liste", "url_name": "admin_projects"},
                    {"name": "Statusdefinitionen", "url_name": "admin_project_statuses"},
                    {"name": "LLM-Rollen", "url_name": "admin_llm_roles"},
                    {"name": "Prompts", "url_name": "admin_prompts"},
                    {"name": "Modelle", "url_name": "admin_models"},
                    {"name": "Benutzer verwalten", "url_name": "admin_user_list"},
                ],
            }
        )

    if request.user.is_superuser:
        from django.contrib.admin import site as admin_site

        system_tiles: list[AdminLink] = []
        for app in admin_site.get_app_list(request):
            for model in app["models"]:
                system_tiles.append(
                    {
                        "name": model["name"],
                        "url_name": f"admin:{app['app_label']}_{model['object_name'].lower()}_changelist",
                    }
                )

        navigation.append({"name": "System-Admin", "tiles": system_tiles})

    return {"admin_navigation": navigation}

