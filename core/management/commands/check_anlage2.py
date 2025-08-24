from django.core.management.base import BaseCommand
from core.llm_tasks import check_anlage2
from core.cli_utils import print_markdown
import json

class Command(BaseCommand):
    """Pr\u00fcft Anlage 2 eines BVProjects."""

    def add_arguments(self, parser):
        parser.add_argument("projekt_id", type=int)

    def handle(self, projekt_id, **options):
        data = check_anlage2(projekt_id)
        text = f"```json\n{json.dumps(data, indent=2, ensure_ascii=False)}\n```"
        print_markdown(text)
