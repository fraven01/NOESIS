from django.core.management.base import BaseCommand
from django.apps import apps
from importlib import import_module


def create_initial_data(apps=apps, schema_editor=None) -> None:
    """Wrapper ruft die Migrationsfunktion zur Erstellung der Initialdaten auf."""
    mod = import_module("core.migrations.0002_seed_initial_data")
    mod.create_initial_data(apps, schema_editor)


class Command(BaseCommand):
    """Befüllt die Datenbank mit den benötigten Anfangsdaten."""

    def handle(self, *args, **options):
        create_initial_data()
