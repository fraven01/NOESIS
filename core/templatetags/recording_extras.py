from pathlib import Path
from django import template
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter
def basename(value):
    return Path(value).name


@register.filter
def get_item(data, key):
    """Gibt ``data[key]`` zur\u00fcck, falls vorhanden."""
    if isinstance(data, dict):
        return data.get(key, "")
    return ""


@register.filter
def checkbox(value: object) -> str:
    """Rendert ein deaktiviertes Kontrollkästchen."""
    checked = " checked" if value is True else ""
    return mark_safe(f"<input type='checkbox' disabled{checked}>")
