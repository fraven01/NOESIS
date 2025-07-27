from django.core.management.base import BaseCommand
from core.llm_tasks import run_conditional_anlage2_check
from core.cli_utils import print_markdown
import json


class Command(BaseCommand):
    """Pr\u00fcft alle Anlage-2-Funktionen eines Projekts."""

    def add_arguments(self, parser):
        parser.add_argument("file_id", type=int)
        parser.add_argument("--model", dest="model", default=None)

    def handle(self, file_id, model=None, **options):
        run_conditional_anlage2_check(file_id, model_name=model)
        print_markdown("Prüfung abgeschlossen")
