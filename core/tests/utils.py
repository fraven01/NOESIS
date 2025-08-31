"""Gemeinsame Hilfsfunktionen und Fixtures für Tests."""

from __future__ import annotations

import pytest
from django.apps import apps

from ..initial_data_constants import INITIAL_PROJECT_STATUSES
from ..llm_tasks import ANLAGE1_QUESTIONS
from ..management.commands.seed_initial_data import create_initial_data
from ..models import (
    BVProject,
    BVSoftware,
    ProjectStatus,
    Prompt,
    LLMConfig,
    Anlage4Config,
    Anlage4ParserConfig,
)


DEFAULT_STATUS_KEY = next(
    s["key"] for s in INITIAL_PROJECT_STATUSES if s.get("is_default")
)


def create_statuses() -> None:
    """Legt Basis-Status für Projekte an."""
    data = [
        (DEFAULT_STATUS_KEY, "Neu"),
        ("CLASSIFIED", "Klassifiziert"),
        ("GUTACHTEN_FREIGEGEBEN", "Gutachten freigegeben"),
        ("IN_PRUEFUNG_ANLAGE_X", "In Prüfung Anlage X"),
        ("FB_IN_PRUEFUNG", "FB in Prüfung"),
        ("DONE", "Endgeprüft"),
    ]
    for idx, (key, name) in enumerate(data, start=1):
        ProjectStatus.objects.update_or_create(
            key=key,
            defaults={
                "name": name,
                "ordering": idx,
                "is_default": key == DEFAULT_STATUS_KEY,
                "is_done_status": key == "DONE",
            },
        )


@pytest.fixture(autouse=True)
def _extra_statuses(db) -> None:  # pragma: no cover - Fixture
    """Stellt zusätzliche Projekt-Status für Tests bereit."""
    create_statuses()


def create_project(software: list[str] | None = None, **kwargs) -> BVProject:
    """Erzeugt ein Projekt mit optionaler Softwareliste."""
    projekt = BVProject.objects.create(**kwargs)
    for name in software or []:
        BVSoftware.objects.create(project=projekt, name=name)
    return projekt


def seed_test_data(*, skip_prompts: bool = False) -> None:
    """Befüllt die Test-Datenbank mit Initialdaten.

    Bestehende Einträge werden bei Bedarf überschrieben. Optional können die
    Prompt-Definitionen übersprungen werden.
    """
    try:
        create_initial_data(apps)
    except LookupError:
        # Falls die Migrationsfunktion wegen entfernter Modelle fehlschlägt,
        # legen wir die benötigten Objekte manuell an.
        Anlage1QuestionModel = apps.get_model("core", "Anlage1Question")
        Anlage1QuestionVariant = apps.get_model("core", "Anlage1QuestionVariant")
        for idx, text in enumerate(ANLAGE1_QUESTIONS, start=1):
            question, _ = Anlage1QuestionModel.objects.update_or_create(
                num=idx,
                defaults={
                    "text": text,
                    "enabled": True,
                    "parser_enabled": True,
                    "llm_enabled": True,
                },
            )
            Anlage1QuestionVariant.objects.get_or_create(question=question, text=text)
    create_statuses()

    # Erforderliche Konfigurationen bereitstellen
    LLMConfig.objects.all().delete()
    LLMConfig.objects.create()
    Anlage4Config.objects.get_or_create()
    Anlage4ParserConfig.objects.get_or_create()

    # Anlage1 Fragen aktualisieren
    Anlage1QuestionModel = apps.get_model("core", "Anlage1Question")
    Anlage1QuestionVariant = apps.get_model("core", "Anlage1QuestionVariant")
    for idx, text in enumerate(ANLAGE1_QUESTIONS, start=1):
        try:
            question = Anlage1QuestionModel.objects.get(num=idx)
            question.text = text
            question.parser_enabled = True
            question.llm_enabled = True
            question.save()
        except Anlage1QuestionModel.DoesNotExist:
            question = Anlage1QuestionModel.objects.create(
                num=idx,
                text=text,
                parser_enabled=True,
                llm_enabled=True,
            )
        Anlage1QuestionVariant.objects.get_or_create(question=question, text=text)

    if skip_prompts:
        return

    for idx, text in enumerate(ANLAGE1_QUESTIONS, start=1):
        Prompt.objects.update_or_create(name=f"anlage1_q{idx}", defaults={"text": text})
