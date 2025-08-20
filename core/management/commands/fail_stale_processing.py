from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import BVProjectFile


class Command(BaseCommand):
    """Setzt alte PROCESSING-Einträge auf FAILED."""

    help = "Markiert veraltete Prozess-Einträge als fehlgeschlagen."

    def add_arguments(self, parser) -> None:  # pragma: no cover - argparse trivial
        parser.add_argument(
            "--minutes",
            type=int,
            default=60,
            help="Timeout in Minuten",
        )

    def handle(self, minutes: int, **options) -> None:
        """Führt die Aktualisierung der veralteten Einträge durch."""

        cutoff = timezone.now() - timedelta(minutes=minutes)
        stale_qs = BVProjectFile.objects.filter(
            processing_status=BVProjectFile.PROCESSING,
            created_at__lt=cutoff,
        )
        updated = stale_qs.update(processing_status=BVProjectFile.FAILED)
        self.stdout.write(f"{updated} Einträge aktualisiert.")
