"""Kontextprozessoren für die Django-Templates."""

from django.http import HttpRequest

from .navigation import NAV_ITEMS, NavItem


def is_admin(request: HttpRequest) -> dict[str, bool]:
    """Gibt an, ob der aktuelle Benutzer zur Admin-Gruppe gehört."""

    if request.user.is_authenticated:
        return {"is_admin": request.user.groups.filter(name__iexact="admin").exists()}
    return {"is_admin": False}


def navigation_menu(request: HttpRequest) -> dict[str, list[NavItem]]:
    """Liefert erlaubte Navigationseinträge für den aktuellen Benutzer."""

    items: list[NavItem] = []
    if request.user.is_authenticated:
        items = [item for item in NAV_ITEMS if request.user.has_perm(item["perm"])]
    return {"navigation": items}

