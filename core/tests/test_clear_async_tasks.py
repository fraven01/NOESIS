from django.core.management import call_command

from .base import NoesisTestCase


class ClearAsyncTasksCommandTests(NoesisTestCase):
    """Smoke-Tests für den clear_async_tasks-Command."""

    def test_command_runs_without_error(self) -> None:
        # Erwartet keinen Fehler auch ohne vorhandene Queue-/Task-Einträge
        call_command("clear_async_tasks")

    def test_command_flags(self) -> None:
        # Läuft auch mit Flags ohne Fehler
        call_command("clear_async_tasks", queued=True)
        call_command("clear_async_tasks", failed=True)

