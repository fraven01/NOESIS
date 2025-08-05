from django.core.management.base import BaseCommand
from django.core import serializers

from core.models import (
    Prompt,
    LLMRole,
    ProjectStatus,
    Area,
    Tile,
    Anlage2Config,
    Anlage2Function,
    SupervisionStandardNote,
)


class Command(BaseCommand):
    """Exportiert Konfigurationsdaten als JSON."""

    help = "Exportiert Konfigurationsmodelle als JSON."  # noqa: A003

    def handle(self, *args, **options) -> None:  # noqa: ANN001
        """Serialisiert alle wichtigen Konfigurationsmodelle."""
        objects = []
        for model in [
            Prompt,
            LLMRole,
            ProjectStatus,
            Area,
            Tile,
            Anlage2Config,
            Anlage2Function,
            SupervisionStandardNote,
        ]:
            objects.extend(model.objects.all())
        data = serializers.serialize("json", objects, ensure_ascii=False, indent=2)
        self.stdout.write(data)
