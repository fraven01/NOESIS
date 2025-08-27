"""Kontextprozessoren für die Django-Templates."""

from __future__ import annotations

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
        _, tiles = get_user_tiles(request.user, area.slug)
        navigation.append({"area": area, "tiles": tiles})

    return {"user_navigation": navigation}


class AdminLink(TypedDict):
    """Repräsentiert einen einzelnen Link innerhalb der Admin-Navigation."""

    name: str
    url_name: str


class AdminGroup(TypedDict, total=False):
    """Untergruppe innerhalb der Admin-Navigation."""

    name: str
    tiles: list[AdminLink]
    groups: list["AdminGroup"]


class AdminSection(TypedDict, total=False):
    """Ein Abschnitt der Admin-Navigation."""

    name: str
    tiles: list[AdminLink]
    groups: list[AdminGroup]


def admin_navigation(request: HttpRequest) -> dict[str, list[AdminSection]]:
    """Stellt die Navigationshierarchie für Admin-Bereiche bereit."""

    if not request.user.is_authenticated:
        return {"admin_navigation": []}

    navigation: list[AdminSection] = []

    if request.user.is_staff or request.user.groups.filter(name__iexact="admin").exists():
        project_groups: list[AdminGroup] = [
            {
                "name": "Projekt-Konfiguration",
                "tiles": [
                    {"name": "Projekt-Liste", "url_name": "admin_projects"},
                    {"name": "Statusdefinitionen", "url_name": "admin_project_statuses"},
                ],
            },
            {
                "name": "Anlagen-Konfiguration",
                "groups": [
                    {
                        "name": "Anlage 1",
                        "tiles": [{"name": "Fragen", "url_name": "admin_anlage1"}],
                    },
                    {
                        "name": "Anlage 2",
                        "tiles": [
                            {"name": "Funktionen", "url_name": "anlage2_function_list"},
                            {"name": "Globale Phrasen", "url_name": "anlage2_config"},
                        ],
                    },
                    {
                        "name": "Anlage 3",
                        "tiles": [{"name": "Parser Regeln", "url_name": "anlage3_rule_list"}],
                    },
                    {
                        "name": "Anlage 4",
                        "tiles": [{"name": "Konfiguration", "url_name": "anlage4_config"}],
                    },
                    {
                        "name": "Allgemein",
                        "tiles": [
                            {"name": "Exakter Parser Regeln", "url_name": "parser_rule_list"},
                            {"name": "Zwecke verwalten", "url_name": "zweckkategoriea_list"},
                            {"name": "Supervision-Notizen", "url_name": "supervisionnote_list"},
                        ],
                    },
                ],
            },
            {
                "name": "KI-Konfiguration",
                "tiles": [
                    {"name": "LLM-Rollen", "url_name": "admin_llm_roles"},
                    {"name": "Prompts", "url_name": "admin_prompts"},
                    {"name": "LLM-Modelle", "url_name": "admin_models"},
                ],
            },
            {
                "name": "Systemverwaltung",
                "tiles": [
                    {"name": "Benutzer verwalten", "url_name": "admin_user_list"},
                    {"name": "Gruppen", "url_name": "admin:auth_group_changelist"},
                ],
            },
        ]

        navigation.append({"name": "Projekt-Admin", "groups": project_groups})

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


def breadcrumbs(request: HttpRequest) -> dict[str, list[dict[str, str]]]:
    """Erzeugt Breadcrumbs basierend auf dem Anfragepfad.

    Liefert eine Liste von ``{"url": str | None, "label": str}``.
    Diese dient als Fallback für alle Bereiche, in denen keine spezifischen
    Breadcrumbs gesetzt wurden, z.B. System- oder Projekt-Admin.
    """

    path = request.path.strip("/")
    if not path:
        return {"breadcrumbs": []}

    mappings = {
        "admin": "System-Admin",
        "projects-admin": "Projekt-Admin",
        "change": "Bearbeiten",
        "add": "Hinzufügen",
    }

    segments = [p for p in path.split("/") if p]
    crumbs: list[dict[str, str]] = []
    current = "/"

    for idx, segment in enumerate(segments):
        current += f"{segment}/"
        label = mappings.get(segment, segment.replace("-", " ").capitalize())
        url = current if idx < len(segments) - 1 else None
        crumbs.append({"url": url, "label": label})

    return {"breadcrumbs": crumbs}

