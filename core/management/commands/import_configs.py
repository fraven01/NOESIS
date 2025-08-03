from pathlib import Path

from django.core import serializers
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    """Importiert Konfigurationsdaten aus einer JSON-Datei."""

    help = "Importiert Konfigurationsmodelle aus einer JSON-Datei."  # noqa: A003

    def add_arguments(self, parser) -> None:  # noqa: ANN001
        parser.add_argument("json_file", type=str, help="Pfad zur JSON-Datei")

    def handle(self, *args, **options) -> None:  # noqa: ANN001
        """Deserialisiert und speichert die Konfigurationsmodelle."""
        json_path = Path(options["json_file"])
        data = json_path.read_text(encoding="utf-8")
        for deserialized in serializers.deserialize("json", data):
            obj = deserialized.object
            model = obj.__class__
            defaults = {}
            for field in model._meta.fields:
                if field.primary_key:
                    continue
                defaults[field.name] = getattr(obj, field.name)
            instance, _ = model.objects.update_or_create(pk=obj.pk, defaults=defaults)
            for field, value in deserialized.m2m_data.items():
                getattr(instance, field).set(value)
        self.stdout.write(self.style.SUCCESS("Konfigurationen importiert"))
