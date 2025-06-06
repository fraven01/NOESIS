from django.core.management.base import BaseCommand
from core.llm_tasks import classify_system

class Command(BaseCommand):
    """Führt die Systemklassifizierung für ein BVProject aus."""

    def add_arguments(self, parser):
        parser.add_argument("projekt_id", type=int)

    def handle(self, projekt_id, **options):
        data = classify_system(projekt_id)
        self.stdout.write(self.style.SUCCESS(str(data)))
