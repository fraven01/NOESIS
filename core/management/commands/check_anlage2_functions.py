from django.core.management.base import BaseCommand
from core.llm_tasks import run_conditional_anlage2_check
from core.cli_utils import print_markdown
import json


class Command(BaseCommand):
    """Pr\u00fcft alle Anlage-2-Funktionen eines Projekts."""

    def add_arguments(self, parser):
        parser.add_argument("file_id", type=int)

    def handle(self, file_id, **options):
        run_conditional_anlage2_check(file_id)
        print_markdown("Prüfung abgeschlossen")
