
from django.urls import reverse
from .models import Area


def main_navigation(request):
    """Stellt die Navigationseinträge für das Grundlayout bereit."""
    nav = [
        {"label": "Startseite", "url": reverse("home")}
    ]
    user = request.user
    if user.is_authenticated:
        for area in Area.objects.all():
            if area.users.filter(pk=user.pk).exists():
                nav.append({"label": area.name, "url": reverse(area.slug)})
        nav.append({"label": "Mein Konto", "url": reverse("account")})
        nav.append({"label": "Abmelden", "url": reverse("logout"), "post": True})
    else:
        nav.append({"label": "Anmelden", "url": reverse("login")})
    return {"main_navigation": nav}

from __future__ import annotations

from django.contrib.auth.models import Permission
from django.http import HttpRequest

from .models import Tile


def _user_has_tile(user, slug: str) -> bool:
    """Prüft, ob der Benutzer Zugriff auf die angegebene Tile hat."""
    try:
        tile = Tile.objects.get(slug=slug)
    except Tile.DoesNotExist:
        return False
    if tile.permission:
        perm = f"{tile.permission.content_type.app_label}.{tile.permission.codename}"
        if user.has_perm(perm):
            return True
    return tile.users.filter(pk=user.pk).exists()


ADMIN_SECTIONS = [
    (
        "Projekt-Konfiguration",
        [
            {"label": "Projekt-Liste", "url_name": "admin_projects", "tile": "admin_projects"},
            {"label": "Projekt-Status", "url_name": "admin_project_statuses", "tile": "admin_projects"},
        ],
    ),
    (
        "Anlagen-Konfiguration",
        [
            {"label": "Anlage 1 Fragen", "url_name": "admin_anlage1", "tile": "admin_anlage1"},
            {
                "label": "Anlage 2 Funktionen",
                "url_name": "anlage2_function_list",
                "tile": "admin_anlage2",
            },
            {"label": "Anlage 2 Globale Phrasen", "url_name": "anlage2_config", "tile": "admin_anlage2"},
            {"label": "Zwecke verwalten", "url_name": "zweckkategoriea_list", "tile": "admin_anlage2"},
        ],
    ),
    (
        "KI-Konfiguration",
        [
            {"label": "LLM-Rollen", "url_name": "admin_llm_roles", "tile": "admin_llm"},
            {"label": "Prompts", "url_name": "admin_prompts", "tile": "admin_llm"},
            {"label": "LLM-Modelle", "url_name": "admin_models", "tile": "admin_llm"},
        ],
    ),
    (
        "Systemverwaltung",
        [
            {"label": "Benutzer verwalten", "url_name": "admin_user_list", "tile": "admin_system"},
            {"label": "Gruppen", "url_name": "auth_group_changelist", "tile": "admin_system"},
            {"label": "Rollen & Rechte", "url_name": "admin_role_editor", "tile": "admin_system"},
        ],
    ),
]


def admin_navigation(request: HttpRequest) -> dict[str, list[dict]]:
    """Stellt die verfügbaren Admin-Links für das Template bereit."""
    user = request.user
    if not user.is_authenticated:
        return {}

    sections: list[dict[str, list]] = []
    for title, items in ADMIN_SECTIONS:
        links = [
            {"label": item["label"], "url_name": item["url_name"]}
            for item in items
            if _user_has_tile(user, item["tile"]) or user.is_superuser
        ]
        if links:
            sections.append({"title": title, "links": links})
    return {"admin_links": sections}


