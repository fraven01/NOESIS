from django.core.management.base import BaseCommand
from core.llm_tasks import check_anlage1
from core.cli_utils import print_markdown
import json

class Command(BaseCommand):
    """Prüft Anlage 1 eines BVProjects."""

    def add_arguments(self, parser):
        parser.add_argument("file_id", type=int)
        parser.add_argument("--model", dest="model", default=None)

    def handle(self, file_id, model=None, **options):
        data = check_anlage1(file_id, model_name=model)
        text = f"```json\n{json.dumps(data, indent=2, ensure_ascii=False)}\n```"
        print_markdown(text)
