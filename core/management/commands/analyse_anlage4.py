from django.core.management.base import BaseCommand
from core.llm_tasks import analyse_anlage4_async
from core.cli_utils import print_markdown
from django_q.tasks import async_task
from django.db import connection
import json

class Command(BaseCommand):
    """Analysiert Anlage 4 eines BVProjects."""

    def add_arguments(self, parser):
        parser.add_argument("file_id", type=int)

    def handle(self, file_id, **options):
        if connection.vendor == "sqlite":
            data = analyse_anlage4_async(file_id)
            text = f"```json\n{json.dumps(data, indent=2, ensure_ascii=False)}\n```"
            print_markdown(text)
        else:
            async_task("core.llm_tasks.analyse_anlage4_async", file_id)
