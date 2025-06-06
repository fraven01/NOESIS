from django.core.management.base import BaseCommand
from core.llm_tasks import check_anlage5

class Command(BaseCommand):
    """Pr\u00fcft Anlage 5 eines BVProjects."""

    def add_arguments(self, parser):
        parser.add_argument("projekt_id", type=int)

    def handle(self, projekt_id, **options):
        data = check_anlage5(projekt_id)
        self.stdout.write(self.style.SUCCESS(str(data)))
