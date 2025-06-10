from django.core.management.base import BaseCommand
from core.llm_tasks import classify_system

class Command(BaseCommand):
    """Führt die Systemklassifizierung für ein BVProject aus."""

    def add_arguments(self, parser):
        parser.add_argument("projekt_id", type=int)
        parser.add_argument("--model", dest="model", default=None)

    def handle(self, projekt_id, model=None, **options):
        data = classify_system(projekt_id, model_name=model)
        self.stdout.write(self.style.SUCCESS(str(data)))
