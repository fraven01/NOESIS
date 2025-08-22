"""Basis-Testklasse mit globalem Seed für Initialdaten."""

from django.core.management import call_command
from django.test import TestCase


class NoesisTestCase(TestCase):
    """Führt vor allen Tests das Seeding der Standarddaten aus."""

    @classmethod
    def setUpTestData(cls) -> None:  # noqa: D401 - Standard-Setup
        """Initialisiert die Testdatenbank mit Seed-Daten."""
        call_command("seed_initial_data", verbosity=0)
