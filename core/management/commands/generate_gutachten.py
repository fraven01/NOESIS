from django.core.management.base import BaseCommand
from core.llm_tasks import generate_gutachten
from core.cli_utils import print_markdown

class Command(BaseCommand):
    """Erzeugt ein Gutachten für ein BVProject."""

    def add_arguments(self, parser):
        parser.add_argument("projekt_id", type=int)
        parser.add_argument("--model", dest="model", default=None)

    def handle(self, projekt_id, model=None, **options):
        path = generate_gutachten(projekt_id, model_name=model)
        print_markdown(str(path))
