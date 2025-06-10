from django.core.management.base import BaseCommand
from core.llm_tasks import check_anlage2_functions
from core.cli_utils import print_markdown
import json


class Command(BaseCommand):
    """Pr\u00fcft alle Anlage-2-Funktionen eines Projekts."""

    def add_arguments(self, parser):
        parser.add_argument("projekt_id", type=int)
        parser.add_argument("--model", dest="model", default=None)

    def handle(self, projekt_id, model=None, **options):
        data = check_anlage2_functions(projekt_id, model_name=model)
        text = f"```json\n{json.dumps(data, indent=2, ensure_ascii=False)}\n```"
        print_markdown(text)
