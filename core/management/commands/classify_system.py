from django.core.management.base import BaseCommand, CommandParser

from ...llm_tasks import classify_system


class Command(BaseCommand):
    help = "Führt die Klassifizierung für ein BVProject aus."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("project_id", type=int)

    def handle(self, *args, **options):
        project_id = options["project_id"]
        data = classify_system(project_id)
        self.stdout.write(self.style.SUCCESS(str(data)))
