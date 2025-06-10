from django.core.management.base import BaseCommand
from core.llm_tasks import check_anlage2

class Command(BaseCommand):
    """Pr\u00fcft Anlage 2 eines BVProjects."""

    def add_arguments(self, parser):
        parser.add_argument("projekt_id", type=int)
        parser.add_argument("--model", dest="model", default=None)

    def handle(self, projekt_id, model=None, **options):
        data = check_anlage2(projekt_id, model_name=model)
        self.stdout.write(self.style.SUCCESS(str(data)))
