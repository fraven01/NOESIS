from pathlib import Path
from django import template

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
