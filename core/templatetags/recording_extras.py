from pathlib import Path

import markdown
from django import template
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter
def basename(value):
    return Path(value).name


@register.filter
def get_item(data, key):
    """Gibt ``data[key]`` zur\u00fcck und entpackt ``{"value": x}``-Strukturen."""
    if isinstance(data, dict):
        value = data.get(key, "")
        if isinstance(value, dict) and "value" in value:
            return value["value"]
        return value
    return ""


@register.filter
def checkbox(value: object) -> str:
    """Rendert ein deaktiviertes Kontrollkästchen."""
    checked = " checked" if value is True else ""
    return mark_safe(f"<input type='checkbox' disabled{checked}>")


@register.filter
def raw_item(data, key):
    """Gibt ``data[key]`` zurück ohne weitere Verarbeitung."""
    if isinstance(data, dict):
        return data.get(key)
    return None


@register.filter(name="markdownify")
def markdownify(text: str) -> str:
    """Wandelt Markdown-Text in sicheres HTML um."""
    if not text:
        return ""

    # Aktivierte Markdown-Erweiterungen
    extensions = [
        "extra",      # Tabellen, Code-Blöcke und mehr
        "admonition", # Hinweis-Boxen mit !!! note
        "toc",        # Inhaltsverzeichnis per [TOC]
    ]

    html = markdown.markdown(text, extensions=extensions)
    return mark_safe(html)
