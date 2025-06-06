from django.core.management.base import BaseCommand, CommandParser

from ...llm_tasks import check_anlage1


class Command(BaseCommand):
    help = "Prüft Anlage 1 für ein BVProject."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("project_id", type=int)

    def handle(self, *args, **options):
        project_id = options["project_id"]
        result = check_anlage1(project_id)
        self.stdout.write(self.style.SUCCESS(str(result)))
