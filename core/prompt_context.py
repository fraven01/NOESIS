"""Registry für Platzhalter in LLM-Prompts."""

from __future__ import annotations

from typing import Callable

from .models import BVProject


PLACEHOLDER_BUILDERS: dict[str, Callable[[BVProject], str]] = {
    "project_name": lambda p: p.title,
    "software_name": lambda p: p.software_string,
}


def build_prompt_context(project: BVProject | None = None, **extra: str) -> dict[str, str]:
    """Erzeuge ein Kontext-Dictionary für LLM-Prompts."""

    ctx = {key: fn(project) for key, fn in PLACEHOLDER_BUILDERS.items() if project}
    ctx.update(extra)
    return ctx


def available_placeholders() -> list[str]:
    """Liste der verfügbaren Platzhalter."""

    return sorted(PLACEHOLDER_BUILDERS.keys())

