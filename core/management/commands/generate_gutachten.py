from django.core.management.base import BaseCommand, CommandParser

from ...llm_tasks import generate_gutachten


class Command(BaseCommand):
    help = "Erstellt ein Gutachten für ein BVProject."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("project_id", type=int)

    def handle(self, *args, **options):
        project_id = options["project_id"]
        pf = generate_gutachten(project_id)
        self.stdout.write(self.style.SUCCESS(pf.file.name))
