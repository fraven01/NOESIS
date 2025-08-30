"""Smoke-Tests für den ``clear_async_tasks``-Command."""

import pytest
from django.core.management import call_command


@pytest.mark.django_db
def test_command_runs_without_error() -> None:
    """Erwartet keinen Fehler auch ohne vorhandene Queue-/Task-Einträge."""

    call_command("clear_async_tasks")


@pytest.mark.django_db
def test_command_flags() -> None:
    """Läuft auch mit Flags ohne Fehler."""

    call_command("clear_async_tasks", queued=True)
    call_command("clear_async_tasks", failed=True)

