from pathlib import Path
from django import template

register = template.Library()


@register.filter
def basename(value):
    return Path(value).name
