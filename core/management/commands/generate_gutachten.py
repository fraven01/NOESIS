from django.core.management.base import BaseCommand
from core.llm_tasks import generate_gutachten
from core.cli_utils import print_markdown

class Command(BaseCommand):
    """Erzeugt ein Gutachten für ein BVProject."""

    def add_arguments(self, parser):
        parser.add_argument("projekt_id", type=int)

    def handle(self, projekt_id, **options):
        path = generate_gutachten(projekt_id)
        print_markdown(str(path))
