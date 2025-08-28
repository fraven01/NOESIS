from django.core.management.base import BaseCommand

try:  # django-q2 / django-q ORM-Backend
    from django_q.models import Task, OrmQ
except Exception:  # pragma: no cover - falls Backend anders konfiguriert ist
    Task = None  # type: ignore
    OrmQ = None  # type: ignore


class Command(BaseCommand):
    """Löscht Django‑Q Queue-Einträge und fehlgeschlagene Tasks.

    Standard: löscht beides (queued und failed). Mit Flags kann man einschränken.
    """

    help = (
        "Entfernt alle Django‑Q Queue‑Einträge (queued) und/oder fehlgeschlagene "
        "Task‑Resultate (failed)."
    )

    def add_arguments(self, parser) -> None:  # noqa: ANN001 - Argparser ist trivial
        parser.add_argument(
            "--queued",
            action="store_true",
            help="Nur Queue‑Einträge (OrmQ) löschen",
        )
        parser.add_argument(
            "--failed",
            action="store_true",
            help="Nur fehlgeschlagene Task‑Einträge löschen",
        )

    def handle(self, *args, **options) -> None:  # noqa: ANN001
        if Task is None or OrmQ is None:
            self.stdout.write(
                self.style.ERROR(
                    "Django‑Q ORM‑Modelle nicht verfügbar. Prüfe Q_CLUSTER Backend."
                )
            )
            return

        do_queued = bool(options.get("queued"))
        do_failed = bool(options.get("failed"))

        # Wenn keine Flags gesetzt sind, beide Typen bereinigen
        if not (do_queued or do_failed):
            do_queued = True
            do_failed = True

        deleted_queued = 0
        deleted_failed = 0

        if do_queued:
            deleted_queued = OrmQ.objects.count()
            OrmQ.objects.all().delete()

        if do_failed:
            failed_qs = Task.objects.filter(success=False)
            deleted_failed = failed_qs.count()
            failed_qs.delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"Bereinigt: queued={deleted_queued}, failed={deleted_failed}"
            )
        )

